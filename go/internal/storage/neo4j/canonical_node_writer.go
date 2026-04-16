package neo4j

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"time"

	"go.opentelemetry.io/otel/metric"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// CanonicalNodeWriter writes canonical graph nodes from a CanonicalMaterialization
// in strict phase order. Each phase creates nodes that subsequent phases MATCH.
type CanonicalNodeWriter struct {
	executor    Executor
	batchSize   int
	instruments *telemetry.Instruments
}

// NewCanonicalNodeWriter constructs a writer backed by the given Executor.
// batchSize defaults to DefaultBatchSize (500) if <= 0. instruments may be nil.
func NewCanonicalNodeWriter(executor Executor, batchSize int, instruments *telemetry.Instruments) *CanonicalNodeWriter {
	if batchSize <= 0 {
		batchSize = DefaultBatchSize
	}
	return &CanonicalNodeWriter{
		executor:    executor,
		batchSize:   batchSize,
		instruments: instruments,
	}
}

// Write executes all canonical writes in strict phase order:
//
//	A: retract stale nodes
//	B: repository
//	C: directories (depth-ordered)
//	D: files
//	E: entities (per-label)
//	F: modules
//	G: structural edges
//
// When the executor implements GroupExecutor, all statements are dispatched as
// a single atomic transaction. Otherwise, statements execute sequentially.
func (w *CanonicalNodeWriter) Write(ctx context.Context, mat projector.CanonicalMaterialization) error {
	if mat.IsEmpty() {
		return nil
	}

	builders := []struct {
		name string
		fn   func(projector.CanonicalMaterialization) []Statement
	}{
		{"retract", w.buildRetractStatements},
		{"repository", w.buildRepositoryStatements},
		{"directories", w.buildDirectoryStatements},
		{"files", w.buildFileStatements},
		{"entities", w.buildEntityStatements},
		{"modules", w.buildModuleStatements},
		{"structural_edges", w.buildStructuralEdgeStatements},
	}

	var allStatements []Statement
	for _, b := range builders {
		allStatements = append(allStatements, b.fn(mat)...)
	}

	if len(allStatements) == 0 {
		return nil
	}

	// Atomic path: single transaction for all phases.
	if ge, ok := w.executor.(GroupExecutor); ok {
		start := time.Now()
		if err := ge.ExecuteGroup(ctx, allStatements); err != nil {
			return fmt.Errorf("canonical atomic write: %w", err)
		}
		dur := time.Since(start).Seconds()
		slog.Info("canonical atomic write completed",
			"scope_id", mat.ScopeID, "statements", len(allStatements), "duration_s", dur)
		w.recordAtomicWrite(ctx, "atomic_group", dur, mat)
		return nil
	}

	// Fallback: sequential execution (existing behavior).
	w.recordAtomicFallback(ctx)
	start := time.Now()
	for _, stmt := range allStatements {
		if err := w.executor.Execute(ctx, stmt); err != nil {
			return fmt.Errorf("canonical sequential write: %w", err)
		}
	}
	dur := time.Since(start).Seconds()
	slog.Info("canonical sequential write completed",
		"scope_id", mat.ScopeID, "statements", len(allStatements), "duration_s", dur)
	w.recordAtomicWrite(ctx, "sequential_group", dur, mat)
	return nil
}

// --- Phase A: Retract stale nodes ---

func (w *CanonicalNodeWriter) buildRetractStatements(mat projector.CanonicalMaterialization) []Statement {
	retractParams := map[string]any{
		"repo_id":       mat.RepoID,
		"generation_id": mat.GenerationID,
	}

	retractions := []string{
		canonicalNodeRetractFilesCypher,
		canonicalNodeRetractCodeEntitiesCypher,
		canonicalNodeRetractInfraEntitiesCypher,
		canonicalNodeRetractTerraformEntitiesCypher,
		canonicalNodeRetractCloudFormationEntitiesCypher,
		canonicalNodeRetractSQLEntitiesCypher,
		canonicalNodeRetractDataEntitiesCypher,
		canonicalNodeRetractDirectoriesCypher,
	}

	stmts := make([]Statement, 0, len(retractions)+1)
	for _, cypher := range retractions {
		stmts = append(stmts, Statement{
			Operation:  OperationCanonicalRetract,
			Cypher:     cypher,
			Parameters: retractParams,
		})
	}

	// Parameter retraction uses file_paths
	filePaths := make([]string, len(mat.Files))
	for i, f := range mat.Files {
		filePaths[i] = f.Path
	}
	if len(filePaths) > 0 {
		stmts = append(stmts, Statement{
			Operation: OperationCanonicalRetract,
			Cypher:    canonicalNodeRetractParametersCypher,
			Parameters: map[string]any{
				"file_paths": filePaths,
			},
		})
	}

	return stmts
}

// --- Phase B: Repository ---

func (w *CanonicalNodeWriter) buildRepositoryStatements(mat projector.CanonicalMaterialization) []Statement {
	if mat.Repository == nil {
		return nil
	}
	r := mat.Repository
	return []Statement{{
		Operation: OperationCanonicalUpsert,
		Cypher:    canonicalNodeRepositoryUpsertCypher,
		Parameters: map[string]any{
			"repo_id":       r.RepoID,
			"name":          r.Name,
			"path":          r.Path,
			"local_path":    r.LocalPath,
			"remote_url":    r.RemoteURL,
			"repo_slug":     r.RepoSlug,
			"has_remote":    r.HasRemote,
			"scope_id":      mat.ScopeID,
			"generation_id": mat.GenerationID,
		},
	}}
}

// --- Phase C: Directories (depth-ordered) ---

func (w *CanonicalNodeWriter) buildDirectoryStatements(mat projector.CanonicalMaterialization) []Statement {
	if len(mat.Directories) == 0 {
		return nil
	}

	// Group by depth, sorted ascending.
	byDepth := map[int][]projector.DirectoryRow{}
	for _, d := range mat.Directories {
		byDepth[d.Depth] = append(byDepth[d.Depth], d)
	}

	depths := make([]int, 0, len(byDepth))
	for d := range byDepth {
		depths = append(depths, d)
	}
	sort.Ints(depths)

	var stmts []Statement
	for _, depth := range depths {
		dirs := byDepth[depth]
		rows := make([]map[string]any, len(dirs))
		for i, d := range dirs {
			rows[i] = map[string]any{
				"path":          d.Path,
				"name":          d.Name,
				"parent_path":   d.ParentPath,
				"repo_id":       d.RepoID,
				"scope_id":      mat.ScopeID,
				"generation_id": mat.GenerationID,
			}
		}

		cypher := canonicalNodeDirectoryDepthNCypher
		if depth == 0 {
			cypher = canonicalNodeDirectoryDepth0Cypher
		}

		stmts = append(stmts, buildBatchedStatements(cypher, rows, w.batchSize)...)
	}
	return stmts
}

// --- Phase D: Files ---

func (w *CanonicalNodeWriter) buildFileStatements(mat projector.CanonicalMaterialization) []Statement {
	if len(mat.Files) == 0 {
		return nil
	}

	rows := make([]map[string]any, len(mat.Files))
	for i, f := range mat.Files {
		rows[i] = map[string]any{
			"path":          f.Path,
			"name":          f.Name,
			"relative_path": f.RelativePath,
			"language":      f.Language,
			"repo_id":       f.RepoID,
			"dir_path":      f.DirPath,
			"scope_id":      mat.ScopeID,
			"generation_id": mat.GenerationID,
		}
	}

	return buildBatchedStatements(canonicalNodeFileUpsertCypher, rows, w.batchSize)
}

// --- Phase E: Entities (per-label UNWIND) ---

func (w *CanonicalNodeWriter) buildEntityStatements(mat projector.CanonicalMaterialization) []Statement {
	if len(mat.Entities) == 0 {
		return nil
	}

	// Group by label for per-label UNWIND batches.
	byLabel := map[string][]map[string]any{}
	for _, e := range mat.Entities {
		row := map[string]any{
			"entity_id":       e.EntityID,
			"entity_name":     e.EntityName,
			"label":           e.Label,
			"file_path":       e.FilePath,
			"relative_path":   e.RelativePath,
			"start_line":      e.StartLine,
			"end_line":        e.EndLine,
			"language":        e.Language,
			"repo_id":         e.RepoID,
			"entity_metadata": e.Metadata,
			"scope_id":        mat.ScopeID,
			"generation_id":   mat.GenerationID,
		}
		byLabel[e.Label] = append(byLabel[e.Label], row)
	}

	// Sort labels for deterministic ordering.
	labels := make([]string, 0, len(byLabel))
	for l := range byLabel {
		labels = append(labels, l)
	}
	sort.Strings(labels)

	var stmts []Statement
	for _, label := range labels {
		rows := byLabel[label]
		for i := range rows {
			if metadata := canonicalTypeScriptClassFamilyMetadata(rows[i]); len(metadata) > 0 {
				for key, value := range metadata {
					rows[i][key] = value
				}
			}
			delete(rows[i], "entity_metadata")
		}
		cypher := fmt.Sprintf(canonicalNodeEntityUpsertTemplate, label)
		stmts = append(stmts, buildBatchedStatements(cypher, rows, w.batchSize)...)
	}
	return stmts
}

// --- Phase F: Modules ---

func (w *CanonicalNodeWriter) buildModuleStatements(mat projector.CanonicalMaterialization) []Statement {
	if len(mat.Modules) == 0 {
		return nil
	}

	rows := make([]map[string]any, len(mat.Modules))
	for i, m := range mat.Modules {
		rows[i] = map[string]any{
			"name":     m.Name,
			"language": m.Language,
		}
	}

	return buildBatchedStatements(canonicalNodeModuleUpsertCypher, rows, w.batchSize)
}

// --- Phase G: Structural edges ---

func (w *CanonicalNodeWriter) buildStructuralEdgeStatements(mat projector.CanonicalMaterialization) []Statement {
	var stmts []Statement

	// IMPORTS edges
	if len(mat.Imports) > 0 {
		rows := make([]map[string]any, len(mat.Imports))
		for i, imp := range mat.Imports {
			rows[i] = map[string]any{
				"file_path":     imp.FilePath,
				"module_name":   imp.ModuleName,
				"imported_name": imp.ImportedName,
				"alias":         imp.Alias,
				"line_number":   imp.LineNumber,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeImportEdgeCypher, rows, w.batchSize)...)
	}

	// HAS_PARAMETER edges
	if len(mat.Parameters) > 0 {
		rows := make([]map[string]any, len(mat.Parameters))
		for i, p := range mat.Parameters {
			rows[i] = map[string]any{
				"func_name":  p.FunctionName,
				"file_path":  p.FilePath,
				"func_line":  p.FunctionLine,
				"param_name": p.ParamName,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeHasParameterEdgeCypher, rows, w.batchSize)...)
	}

	// Class CONTAINS Function edges
	if len(mat.ClassMembers) > 0 {
		rows := make([]map[string]any, len(mat.ClassMembers))
		for i, cm := range mat.ClassMembers {
			rows[i] = map[string]any{
				"class_name": cm.ClassName,
				"func_name":  cm.FunctionName,
				"file_path":  cm.FilePath,
				"func_line":  cm.FunctionLine,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeClassContainsFuncEdgeCypher, rows, w.batchSize)...)
	}

	// Nested Function CONTAINS edges
	if len(mat.NestedFuncs) > 0 {
		rows := make([]map[string]any, len(mat.NestedFuncs))
		for i, nf := range mat.NestedFuncs {
			rows[i] = map[string]any{
				"outer_name": nf.OuterName,
				"inner_name": nf.InnerName,
				"file_path":  nf.FilePath,
				"inner_line": nf.InnerLine,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeNestedFuncEdgeCypher, rows, w.batchSize)...)
	}

	return stmts
}

// --- Batch statement building ---

// buildBatchedStatements splits rows into batches and returns one Statement per batch.
func buildBatchedStatements(cypher string, rows []map[string]any, batchSize int) []Statement {
	if len(rows) == 0 {
		return nil
	}
	var stmts []Statement
	for start := 0; start < len(rows); start += batchSize {
		end := start + batchSize
		if end > len(rows) {
			end = len(rows)
		}
		stmts = append(stmts, Statement{
			Operation:  OperationCanonicalUpsert,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": rows[start:end]},
		})
	}
	return stmts
}

// --- Telemetry helpers ---

func (w *CanonicalNodeWriter) recordAtomicWrite(ctx context.Context, mode string, seconds float64, mat projector.CanonicalMaterialization) {
	if w.instruments == nil {
		return
	}
	attrs := metric.WithAttributes(
		telemetry.AttrWritePhase(mode),
		telemetry.AttrScopeID(mat.ScopeID),
	)
	if w.instruments.CanonicalAtomicWrites != nil {
		w.instruments.CanonicalAtomicWrites.Add(ctx, 1, attrs)
	}
	if w.instruments.CanonicalWriteDuration != nil {
		w.instruments.CanonicalWriteDuration.Record(ctx, seconds, attrs)
	}
}

func (w *CanonicalNodeWriter) recordAtomicFallback(ctx context.Context) {
	if w.instruments == nil || w.instruments.CanonicalAtomicFallbacks == nil {
		return
	}
	w.instruments.CanonicalAtomicFallbacks.Add(ctx, 1)
}
