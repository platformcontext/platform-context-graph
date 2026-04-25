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
	executor                          Executor
	batchSize                         int
	entityBatchSize                   int
	entityLabelBatchSizes             map[string]int
	entityContainmentInEntityUpsert   bool
	entityContainmentBatchAcrossFiles bool
	instruments                       *telemetry.Instruments
}

type canonicalWritePhase struct {
	name       string
	statements []Statement
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

// WithEntityBatchSize overrides the per-statement row batch size used only for
// canonical entity upserts. Other canonical phases keep the writer's default
// batch size.
func (w *CanonicalNodeWriter) WithEntityBatchSize(batchSize int) *CanonicalNodeWriter {
	if w == nil {
		return nil
	}
	if batchSize > 0 {
		w.entityBatchSize = batchSize
	}
	return w
}

// WithEntityLabelBatchSize overrides the per-statement row batch size for one
// canonical entity label while leaving other entity labels on the default
// entity batch size.
func (w *CanonicalNodeWriter) WithEntityLabelBatchSize(label string, batchSize int) *CanonicalNodeWriter {
	if w == nil {
		return nil
	}
	if label == "" || batchSize <= 0 {
		return w
	}
	if w.entityLabelBatchSizes == nil {
		w.entityLabelBatchSizes = make(map[string]int)
	}
	w.entityLabelBatchSizes[label] = batchSize
	return w
}

// WithEntityContainmentInEntityUpsert keeps entity node and file containment
// writes in the same statement. Use only for backends whose batch MERGE support
// requires the file MATCH context to preserve row-bound entity identity.
func (w *CanonicalNodeWriter) WithEntityContainmentInEntityUpsert() *CanonicalNodeWriter {
	if w == nil {
		return nil
	}
	w.entityContainmentInEntityUpsert = true
	w.entityContainmentBatchAcrossFiles = false
	return w
}

// WithBatchedEntityContainmentInEntityUpsert keeps entity node and containment
// writes in one MERGE-first batch whose rows carry file_path. Use only with
// backends that have proven row-safe `SET += row.props` support in the
// generalized UNWIND/MERGE hot path.
func (w *CanonicalNodeWriter) WithBatchedEntityContainmentInEntityUpsert() *CanonicalNodeWriter {
	if w == nil {
		return nil
	}
	w.entityContainmentInEntityUpsert = true
	w.entityContainmentBatchAcrossFiles = true
	return w
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

	phases := w.buildPhases(mat)
	allStatements := flattenCanonicalWritePhases(phases)
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

	// Phase-group path: preserve phase ordering, but use bounded grouped
	// execution within each phase when the executor provides a narrower
	// non-atomic grouping surface.
	if pge, ok := w.executor.(PhaseGroupExecutor); ok {
		w.recordAtomicFallback(ctx)
		start := time.Now()
		for _, phase := range phases {
			if len(phase.statements) == 0 {
				continue
			}
			phaseStart := time.Now()
			if err := pge.ExecutePhaseGroup(ctx, phase.statements); err != nil {
				return fmt.Errorf("canonical phase-group write (%s): %w", phase.name, err)
			}
			phaseSeconds := time.Since(phaseStart).Seconds()
			slog.Info(
				"canonical phase group completed",
				"scope_id", mat.ScopeID,
				"phase", phase.name,
				"statements", len(phase.statements),
				"duration_s", phaseSeconds,
			)
			w.recordAtomicWrite(ctx, "phase_group_"+phase.name, phaseSeconds, mat)
		}
		dur := time.Since(start).Seconds()
		slog.Info("canonical phase-group write completed",
			"scope_id", mat.ScopeID, "statements", len(allStatements), "duration_s", dur)
		w.recordAtomicWrite(ctx, "phase_group", dur, mat)
		return nil
	}

	// Fallback: sequential execution (existing behavior).
	w.recordAtomicFallback(ctx)
	start := time.Now()
	for _, phase := range phases {
		if len(phase.statements) == 0 {
			continue
		}
		phaseStart := time.Now()
		for _, stmt := range phase.statements {
			if err := w.executor.Execute(ctx, stmt); err != nil {
				return fmt.Errorf("canonical sequential write (%s): %w", phase.name, err)
			}
		}
		phaseSeconds := time.Since(phaseStart).Seconds()
		slog.Info(
			"canonical phase completed",
			"scope_id", mat.ScopeID,
			"phase", phase.name,
			"statements", len(phase.statements),
			"duration_s", phaseSeconds,
		)
		w.recordAtomicWrite(ctx, "phase_"+phase.name, phaseSeconds, mat)
	}
	dur := time.Since(start).Seconds()
	slog.Info("canonical sequential write completed",
		"scope_id", mat.ScopeID, "statements", len(allStatements), "duration_s", dur)
	w.recordAtomicWrite(ctx, "sequential_group", dur, mat)
	return nil
}

func (w *CanonicalNodeWriter) buildPhases(mat projector.CanonicalMaterialization) []canonicalWritePhase {
	return []canonicalWritePhase{
		{name: "retract", statements: w.buildRetractStatements(mat)},
		{name: "repository", statements: w.buildRepositoryStatements(mat)},
		{name: "directories", statements: w.buildDirectoryStatements(mat)},
		{name: "files", statements: w.buildFileStatements(mat)},
		{name: "entities", statements: w.buildEntityStatements(mat)},
		{name: "entity_containment", statements: w.buildEntityContainmentStatements(mat)},
		{name: "modules", statements: w.buildModuleStatements(mat)},
		{name: "structural_edges", statements: w.buildStructuralEdgeStatements(mat)},
	}
}

func flattenCanonicalWritePhases(phases []canonicalWritePhase) []Statement {
	var allStatements []Statement
	for _, phase := range phases {
		allStatements = append(allStatements, phase.statements...)
	}
	return allStatements
}

// --- Phase A: Retract stale nodes ---

const canonicalNodeRefreshFilePathBatchSize = 100
const canonicalNodeRefreshEntityContainmentBatchSize = 50

var canonicalNodeRetractCodeEntityLabels = map[string]struct{}{
	"Function":               {},
	"Class":                  {},
	"Variable":               {},
	"Interface":              {},
	"Trait":                  {},
	"Struct":                 {},
	"Enum":                   {},
	"Macro":                  {},
	"Union":                  {},
	"Record":                 {},
	"Property":               {},
	"Annotation":             {},
	"Typedef":                {},
	"TypeAlias":              {},
	"TypeAnnotation":         {},
	"Component":              {},
	"ImplBlock":              {},
	"Protocol":               {},
	"ProtocolImplementation": {},
}

var canonicalNodeRetractInfraEntityLabels = map[string]struct{}{
	"K8sResource":           {},
	"ArgoCDApplication":     {},
	"ArgoCDApplicationSet":  {},
	"CrossplaneXRD":         {},
	"CrossplaneComposition": {},
	"CrossplaneClaim":       {},
	"KustomizeOverlay":      {},
	"HelmChart":             {},
	"HelmValues":            {},
}

var canonicalNodeRetractTerraformEntityLabels = map[string]struct{}{
	"TerraformResource":    {},
	"TerraformModule":      {},
	"TerraformVariable":    {},
	"TerraformOutput":      {},
	"TerraformDataSource":  {},
	"TerraformProvider":    {},
	"TerraformLocal":       {},
	"TerragruntConfig":     {},
	"TerragruntDependency": {},
	"TerragruntInput":      {},
	"TerragruntLocal":      {},
}

var canonicalNodeRetractCloudFormationEntityLabels = map[string]struct{}{
	"CloudFormationResource":  {},
	"CloudFormationParameter": {},
	"CloudFormationOutput":    {},
}

var canonicalNodeRetractSQLEntityLabels = map[string]struct{}{
	"SqlTable":    {},
	"SqlView":     {},
	"SqlFunction": {},
	"SqlTrigger":  {},
	"SqlIndex":    {},
	"SqlColumn":   {},
}

var canonicalNodeRetractDataEntityLabels = map[string]struct{}{
	"DataAsset":        {},
	"DataColumn":       {},
	"AnalyticsModel":   {},
	"DashboardAsset":   {},
	"DataQualityCheck": {},
	"QueryExecution":   {},
	"DataContract":     {},
	"DataOwner":        {},
}

func (w *CanonicalNodeWriter) buildRetractStatements(mat projector.CanonicalMaterialization) []Statement {
	retractParams := map[string]any{
		"repo_id":       mat.RepoID,
		"generation_id": mat.GenerationID,
	}

	filePaths := make([]string, len(mat.Files))
	for i, f := range mat.Files {
		filePaths[i] = f.Path
	}
	entityIDsByFamily := map[string][]string{
		canonicalNodeRetractCodeEntitiesCypher:           canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractCodeEntityLabels),
		canonicalNodeRetractInfraEntitiesCypher:          canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractInfraEntityLabels),
		canonicalNodeRetractTerraformEntitiesCypher:      canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractTerraformEntityLabels),
		canonicalNodeRetractCloudFormationEntitiesCypher: canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractCloudFormationEntityLabels),
		canonicalNodeRetractSQLEntitiesCypher:            canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractSQLEntityLabels),
		canonicalNodeRetractDataEntitiesCypher:           canonicalEntityIDsForLabels(mat.Entities, canonicalNodeRetractDataEntityLabels),
	}
	directoryPaths := make([]string, len(mat.Directories))
	for i, directory := range mat.Directories {
		directoryPaths[i] = directory.Path
	}

	retractions := []string{
		canonicalNodeRetractCodeEntitiesCypher,
		canonicalNodeRetractInfraEntitiesCypher,
		canonicalNodeRetractTerraformEntitiesCypher,
		canonicalNodeRetractCloudFormationEntitiesCypher,
		canonicalNodeRetractSQLEntitiesCypher,
		canonicalNodeRetractDataEntitiesCypher,
		canonicalNodeRetractDirectoriesCypher,
	}

	stmts := make([]Statement, 0, len(retractions)+2)
	fileRetractCypher := canonicalNodeRetractFilesCypher
	fileRetractParams := retractParams
	if len(filePaths) > 0 {
		fileRetractCypher = canonicalNodeRetractRemovedFilesCypher
		fileRetractParams = map[string]any{
			"repo_id":       mat.RepoID,
			"generation_id": mat.GenerationID,
			"file_paths":    filePaths,
		}
	}
	stmts = append(stmts, Statement{
		Operation:  OperationCanonicalRetract,
		Cypher:     fileRetractCypher,
		Parameters: fileRetractParams,
	})

	if len(filePaths) > 0 {
		for _, cypher := range []string{
			canonicalNodeRefreshCurrentFileImportEdgesCypher,
			canonicalNodeRefreshCurrentDirectoryFileEdgesCypher,
		} {
			stmts = append(stmts, buildStringSliceRetractStatements(
				cypher,
				"file_paths",
				filePaths,
				canonicalNodeRefreshFilePathBatchSize,
			)...)
		}
		stmts = append(stmts, buildFileEntityRefreshStatements(mat.Files, mat.Entities)...)
	}
	stmts = append(stmts, buildEntityContainmentRefreshStatements(mat.Entities, mat.ClassMembers, mat.NestedFuncs)...)

	for _, cypher := range retractions {
		params := map[string]any{
			"repo_id":       mat.RepoID,
			"generation_id": mat.GenerationID,
			"entity_ids":    entityIDsByFamily[cypher],
		}
		if cypher == canonicalNodeRetractDirectoriesCypher {
			params = map[string]any{
				"repo_id":         mat.RepoID,
				"generation_id":   mat.GenerationID,
				"directory_paths": directoryPaths,
			}
		}
		stmts = append(stmts, Statement{
			Operation:  OperationCanonicalRetract,
			Cypher:     cypher,
			Parameters: params,
		})
	}

	// Parameter retraction uses file_paths
	if len(filePaths) > 0 {
		stmts = append(stmts, Statement{
			Operation: OperationCanonicalRetract,
			Cypher:    canonicalNodeRetractParametersCypher,
			Parameters: map[string]any{
				"file_paths":    filePaths,
				"generation_id": mat.GenerationID,
			},
		})
	}

	return stmts
}

func canonicalEntityIDsForLabels(entities []projector.EntityRow, labels map[string]struct{}) []string {
	entityIDs := make([]string, 0, len(entities))
	for _, entity := range entities {
		if _, ok := labels[entity.Label]; ok {
			entityIDs = append(entityIDs, entity.EntityID)
		}
	}
	return entityIDs
}

func buildStringSliceRetractStatements(cypher string, paramName string, values []string, batchSize int) []Statement {
	if len(values) == 0 {
		return nil
	}
	if batchSize <= 0 {
		batchSize = len(values)
	}
	stmts := make([]Statement, 0, (len(values)+batchSize-1)/batchSize)
	for start := 0; start < len(values); start += batchSize {
		end := start + batchSize
		if end > len(values) {
			end = len(values)
		}
		stmts = append(stmts, Statement{
			Operation: OperationCanonicalRetract,
			Cypher:    cypher,
			Parameters: map[string]any{
				paramName: append([]string(nil), values[start:end]...),
			},
		})
	}
	return stmts
}

func buildFileEntityRefreshStatements(files []projector.FileRow, entities []projector.EntityRow) []Statement {
	if len(files) == 0 {
		return nil
	}
	entityIDsByFile := make(map[string][]string, len(files))
	seenByFile := make(map[string]map[string]struct{}, len(files))
	for _, entity := range entities {
		if entity.FilePath == "" || entity.EntityID == "" {
			continue
		}
		seen := seenByFile[entity.FilePath]
		if seen == nil {
			seen = make(map[string]struct{})
			seenByFile[entity.FilePath] = seen
		}
		if _, ok := seen[entity.EntityID]; ok {
			continue
		}
		seen[entity.EntityID] = struct{}{}
		entityIDsByFile[entity.FilePath] = append(entityIDsByFile[entity.FilePath], entity.EntityID)
	}

	stmts := make([]Statement, 0, len(files))
	seenFiles := make(map[string]struct{}, len(files))
	for _, file := range files {
		if file.Path == "" {
			continue
		}
		if _, ok := seenFiles[file.Path]; ok {
			continue
		}
		seenFiles[file.Path] = struct{}{}
		stmts = append(stmts, Statement{
			Operation: OperationCanonicalRetract,
			Cypher:    canonicalNodeRefreshCurrentFileEntityEdgesCypher,
			Parameters: map[string]any{
				"file_path":  file.Path,
				"entity_ids": append([]string(nil), entityIDsByFile[file.Path]...),
			},
		})
	}
	return stmts
}

func buildEntityContainmentRefreshStatements(
	entities []projector.EntityRow,
	classMembers []projector.ClassMemberRow,
	nestedFuncs []projector.NestedFunctionRow,
) []Statement {
	parentChildIDs := make(map[string]map[string]struct{})
	classIDsByFileName := make(map[string][]string)
	functionIDsByFileName := make(map[string][]string)
	functionIDsByFileNameLine := make(map[string][]string)

	for _, entity := range entities {
		if entity.EntityID == "" {
			continue
		}
		switch entity.Label {
		case "Class":
			parentChildIDs[entity.EntityID] = make(map[string]struct{})
			classIDsByFileName[fileNameKey(entity.FilePath, entity.EntityName)] = append(
				classIDsByFileName[fileNameKey(entity.FilePath, entity.EntityName)],
				entity.EntityID,
			)
		case "Function":
			parentChildIDs[entity.EntityID] = make(map[string]struct{})
			functionIDsByFileName[fileNameKey(entity.FilePath, entity.EntityName)] = append(
				functionIDsByFileName[fileNameKey(entity.FilePath, entity.EntityName)],
				entity.EntityID,
			)
			functionIDsByFileNameLine[fileNameLineKey(entity.FilePath, entity.EntityName, entity.StartLine)] = append(
				functionIDsByFileNameLine[fileNameLineKey(entity.FilePath, entity.EntityName, entity.StartLine)],
				entity.EntityID,
			)
		}
	}

	for _, classMember := range classMembers {
		childIDs := functionIDsByFileNameLine[fileNameLineKey(classMember.FilePath, classMember.FunctionName, classMember.FunctionLine)]
		if len(childIDs) == 0 {
			continue
		}
		for _, parentID := range classIDsByFileName[fileNameKey(classMember.FilePath, classMember.ClassName)] {
			for _, childID := range childIDs {
				parentChildIDs[parentID][childID] = struct{}{}
			}
		}
	}

	for _, nestedFunc := range nestedFuncs {
		childIDs := functionIDsByFileNameLine[fileNameLineKey(nestedFunc.FilePath, nestedFunc.InnerName, nestedFunc.InnerLine)]
		if len(childIDs) == 0 {
			continue
		}
		for _, parentID := range functionIDsByFileName[fileNameKey(nestedFunc.FilePath, nestedFunc.OuterName)] {
			for _, childID := range childIDs {
				parentChildIDs[parentID][childID] = struct{}{}
			}
		}
	}

	if len(parentChildIDs) == 0 {
		return nil
	}
	parentIDs := make([]string, 0, len(parentChildIDs))
	for parentID := range parentChildIDs {
		parentIDs = append(parentIDs, parentID)
	}
	sort.Strings(parentIDs)

	rows := make([]map[string]any, 0, len(parentIDs))
	for _, parentID := range parentIDs {
		childIDs := make([]string, 0, len(parentChildIDs[parentID]))
		for childID := range parentChildIDs[parentID] {
			childIDs = append(childIDs, childID)
		}
		sort.Strings(childIDs)
		rows = append(rows, map[string]any{
			"parent_entity_id": parentID,
			"child_entity_ids": childIDs,
		})
	}
	return buildBatchedRetractStatements(canonicalNodeRefreshCurrentEntityContainmentEdgesCypher, rows, canonicalNodeRefreshEntityContainmentBatchSize)
}

func fileNameKey(filePath, name string) string {
	return filePath + "\x00" + name
}

func fileNameLineKey(filePath, name string, line int) string {
	return fmt.Sprintf("%s\x00%s\x00%d", filePath, name, line)
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
				"generation_id": mat.GenerationID,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeImportEdgeCypher, rows, w.batchSize)...)
	}

	// HAS_PARAMETER edges
	if len(mat.Parameters) > 0 {
		rows := make([]map[string]any, len(mat.Parameters))
		for i, p := range mat.Parameters {
			rows[i] = map[string]any{
				"func_name":     p.FunctionName,
				"file_path":     p.FilePath,
				"func_line":     p.FunctionLine,
				"param_name":    p.ParamName,
				"generation_id": mat.GenerationID,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeHasParameterEdgeCypher, rows, w.batchSize)...)
	}

	// Class CONTAINS Function edges
	if len(mat.ClassMembers) > 0 {
		rows := make([]map[string]any, len(mat.ClassMembers))
		for i, cm := range mat.ClassMembers {
			rows[i] = map[string]any{
				"class_name":    cm.ClassName,
				"func_name":     cm.FunctionName,
				"file_path":     cm.FilePath,
				"func_line":     cm.FunctionLine,
				"generation_id": mat.GenerationID,
			}
		}
		stmts = append(stmts, buildBatchedStatements(canonicalNodeClassContainsFuncEdgeCypher, rows, w.batchSize)...)
	}

	// Nested Function CONTAINS edges
	if len(mat.NestedFuncs) > 0 {
		rows := make([]map[string]any, len(mat.NestedFuncs))
		for i, nf := range mat.NestedFuncs {
			rows[i] = map[string]any{
				"outer_name":    nf.OuterName,
				"inner_name":    nf.InnerName,
				"file_path":     nf.FilePath,
				"inner_line":    nf.InnerLine,
				"generation_id": mat.GenerationID,
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

func buildBatchedRetractStatements(cypher string, rows []map[string]any, batchSize int) []Statement {
	if len(rows) == 0 {
		return nil
	}
	if batchSize <= 0 {
		batchSize = len(rows)
	}
	stmts := make([]Statement, 0, (len(rows)+batchSize-1)/batchSize)
	for start := 0; start < len(rows); start += batchSize {
		end := start + batchSize
		if end > len(rows) {
			end = len(rows)
		}
		stmts = append(stmts, Statement{
			Operation:  OperationCanonicalRetract,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": rows[start:end]},
		})
	}
	return stmts
}

// --- Telemetry helpers ---

func (w *CanonicalNodeWriter) recordAtomicWrite(ctx context.Context, mode string, seconds float64, _ projector.CanonicalMaterialization) {
	if w.instruments == nil {
		return
	}
	attrs := metric.WithAttributes(telemetry.AttrWritePhase(mode))
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
