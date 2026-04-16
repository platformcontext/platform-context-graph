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
func (w *CanonicalNodeWriter) Write(ctx context.Context, mat projector.CanonicalMaterialization) error {
	if mat.IsEmpty() {
		return nil
	}

	phases := []struct {
		name string
		fn   func(context.Context, projector.CanonicalMaterialization) error
	}{
		{"retract", w.phaseRetract},
		{"repository", w.phaseRepository},
		{"directories", w.phaseDirectories},
		{"files", w.phaseFiles},
		{"entities", w.phaseEntities},
		{"modules", w.phaseModules},
		{"structural_edges", w.phaseStructuralEdges},
	}

	for _, p := range phases {
		start := time.Now()
		if err := p.fn(ctx, mat); err != nil {
			return fmt.Errorf("canonical write phase %s: %w", p.name, err)
		}
		dur := time.Since(start).Seconds()
		slog.Info("canonical phase completed", "phase", p.name, "scope_id", mat.ScopeID, "duration_s", dur)
		w.recordPhaseDuration(ctx, p.name, dur)
	}

	return nil
}

// --- Phase A: Retract stale nodes ---

func (w *CanonicalNodeWriter) phaseRetract(ctx context.Context, mat projector.CanonicalMaterialization) error {
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

	for _, cypher := range retractions {
		if err := w.executor.Execute(ctx, Statement{
			Operation:  OperationCanonicalRetract,
			Cypher:     cypher,
			Parameters: retractParams,
		}); err != nil {
			return err
		}
	}

	// Parameter retraction uses file_paths
	filePaths := make([]string, len(mat.Files))
	for i, f := range mat.Files {
		filePaths[i] = f.Path
	}
	if len(filePaths) > 0 {
		if err := w.executor.Execute(ctx, Statement{
			Operation: OperationCanonicalRetract,
			Cypher:    canonicalNodeRetractParametersCypher,
			Parameters: map[string]any{
				"file_paths": filePaths,
			},
		}); err != nil {
			return err
		}
	}

	return nil
}

// --- Phase B: Repository ---

func (w *CanonicalNodeWriter) phaseRepository(ctx context.Context, mat projector.CanonicalMaterialization) error {
	if mat.Repository == nil {
		return nil
	}
	r := mat.Repository
	if err := w.executor.Execute(ctx, Statement{
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
	}); err != nil {
		return err
	}
	w.recordNodesWritten(ctx, "Repository", 1)
	return nil
}

// --- Phase C: Directories (depth-ordered) ---

func (w *CanonicalNodeWriter) phaseDirectories(ctx context.Context, mat projector.CanonicalMaterialization) error {
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

	for _, depth := range depths {
		dirs := byDepth[depth]
		rows := make([]map[string]any, len(dirs))
		for i, d := range dirs {
			rows[i] = map[string]any{
				"path":        d.Path,
				"name":        d.Name,
				"parent_path": d.ParentPath,
				"repo_id":     d.RepoID,
			}
		}

		cypher := canonicalNodeDirectoryDepthNCypher
		if depth == 0 {
			cypher = canonicalNodeDirectoryDepth0Cypher
		}

		if err := w.executeBatched(ctx, cypher, rows); err != nil {
			return err
		}
		w.recordNodesWritten(ctx, "Directory", int64(len(dirs)))
	}
	return nil
}

// --- Phase D: Files ---

func (w *CanonicalNodeWriter) phaseFiles(ctx context.Context, mat projector.CanonicalMaterialization) error {
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

	if err := w.executeBatched(ctx, canonicalNodeFileUpsertCypher, rows); err != nil {
		return err
	}
	w.recordNodesWritten(ctx, "File", int64(len(mat.Files)))
	w.recordEdgesWritten(ctx, "REPO_CONTAINS", int64(len(mat.Files)))
	w.recordEdgesWritten(ctx, "CONTAINS", int64(len(mat.Files)))
	return nil
}

// --- Phase E: Entities (per-label UNWIND) ---

func (w *CanonicalNodeWriter) phaseEntities(ctx context.Context, mat projector.CanonicalMaterialization) error {
	if len(mat.Entities) == 0 {
		return nil
	}

	// Group by label for per-label UNWIND batches.
	byLabel := map[string][]map[string]any{}
	for _, e := range mat.Entities {
		row := map[string]any{
			"entity_id":     e.EntityID,
			"entity_name":   e.EntityName,
			"file_path":     e.FilePath,
			"relative_path": e.RelativePath,
			"start_line":    e.StartLine,
			"end_line":      e.EndLine,
			"language":      e.Language,
			"repo_id":       e.RepoID,
			"scope_id":      mat.ScopeID,
			"generation_id": mat.GenerationID,
		}
		byLabel[e.Label] = append(byLabel[e.Label], row)
	}

	// Sort labels for deterministic ordering.
	labels := make([]string, 0, len(byLabel))
	for l := range byLabel {
		labels = append(labels, l)
	}
	sort.Strings(labels)

	for _, label := range labels {
		rows := byLabel[label]
		cypher := fmt.Sprintf(canonicalNodeEntityUpsertTemplate, label)
		if err := w.executeBatched(ctx, cypher, rows); err != nil {
			return err
		}
		w.recordNodesWritten(ctx, label, int64(len(rows)))
		w.recordEdgesWritten(ctx, "CONTAINS", int64(len(rows)))
	}
	return nil
}

// --- Phase F: Modules ---

func (w *CanonicalNodeWriter) phaseModules(ctx context.Context, mat projector.CanonicalMaterialization) error {
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

	if err := w.executeBatched(ctx, canonicalNodeModuleUpsertCypher, rows); err != nil {
		return err
	}
	w.recordNodesWritten(ctx, "Module", int64(len(mat.Modules)))
	return nil
}

// --- Phase G: Structural edges ---

func (w *CanonicalNodeWriter) phaseStructuralEdges(ctx context.Context, mat projector.CanonicalMaterialization) error {
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
		if err := w.executeBatched(ctx, canonicalNodeImportEdgeCypher, rows); err != nil {
			return err
		}
		w.recordEdgesWritten(ctx, "IMPORTS", int64(len(mat.Imports)))
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
		if err := w.executeBatched(ctx, canonicalNodeHasParameterEdgeCypher, rows); err != nil {
			return err
		}
		w.recordEdgesWritten(ctx, "HAS_PARAMETER", int64(len(mat.Parameters)))
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
		if err := w.executeBatched(ctx, canonicalNodeClassContainsFuncEdgeCypher, rows); err != nil {
			return err
		}
		w.recordEdgesWritten(ctx, "CONTAINS", int64(len(mat.ClassMembers)))
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
		if err := w.executeBatched(ctx, canonicalNodeNestedFuncEdgeCypher, rows); err != nil {
			return err
		}
		w.recordEdgesWritten(ctx, "CONTAINS", int64(len(mat.NestedFuncs)))
	}

	return nil
}

// --- Batch execution ---

func (w *CanonicalNodeWriter) executeBatched(ctx context.Context, cypher string, rows []map[string]any) error {
	if len(rows) == 0 {
		return nil
	}
	for start := 0; start < len(rows); start += w.batchSize {
		end := start + w.batchSize
		if end > len(rows) {
			end = len(rows)
		}
		batch := rows[start:end]
		if err := w.executor.Execute(ctx, Statement{
			Operation:  OperationCanonicalUpsert,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": batch},
		}); err != nil {
			return err
		}
		w.recordBatchSize(ctx, float64(len(batch)))
	}
	return nil
}

// --- Telemetry helpers ---

func (w *CanonicalNodeWriter) recordPhaseDuration(ctx context.Context, phase string, seconds float64) {
	if w.instruments == nil || w.instruments.CanonicalPhaseDuration == nil {
		return
	}
	w.instruments.CanonicalPhaseDuration.Record(ctx, seconds,
		metric.WithAttributes(telemetry.AttrWritePhase(phase)))
}

func (w *CanonicalNodeWriter) recordNodesWritten(ctx context.Context, nodeType string, count int64) {
	if w.instruments == nil || w.instruments.CanonicalNodesWritten == nil {
		return
	}
	w.instruments.CanonicalNodesWritten.Add(ctx, count,
		metric.WithAttributes(telemetry.AttrNodeType(nodeType)))
}

func (w *CanonicalNodeWriter) recordEdgesWritten(ctx context.Context, edgeType string, count int64) {
	if w.instruments == nil || w.instruments.CanonicalEdgesWritten == nil {
		return
	}
	w.instruments.CanonicalEdgesWritten.Add(ctx, count,
		metric.WithAttributes(telemetry.AttrEdgeType(edgeType)))
}

func (w *CanonicalNodeWriter) recordBatchSize(ctx context.Context, size float64) {
	if w.instruments == nil || w.instruments.CanonicalBatchSize == nil {
		return
	}
	w.instruments.CanonicalBatchSize.Record(ctx, size)
}
