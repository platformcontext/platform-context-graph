// Package graph schema.go provides Neo4j schema initialization.
//
// EnsureSchema creates all node constraints, performance indexes, and
// full-text indexes required by the platform context graph. The constraint
// and index definitions are the checked-in Go-owned schema contract for the
// rewritten platform.
package graph

import (
	"context"
	"fmt"
	"log/slog"
)

// schemaConstraints lists uniqueness and node-key constraints that must exist
// before any graph writes occur. The order stays stable so schema diffs remain
// easy to audit across releases.
var schemaConstraints = []string{
	// Repository identity
	"CREATE CONSTRAINT repository_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
	"CREATE CONSTRAINT repository_path IF NOT EXISTS FOR (r:Repository) REQUIRE r.path IS UNIQUE",

	// File identity
	"CREATE CONSTRAINT path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",

	// Directory identity
	"CREATE CONSTRAINT directory_path IF NOT EXISTS FOR (d:Directory) REQUIRE d.path IS UNIQUE",

	// Code entity node-key constraints
	"CREATE CONSTRAINT function_unique IF NOT EXISTS FOR (f:Function) REQUIRE (f.name, f.path, f.line_number) IS UNIQUE",
	"CREATE CONSTRAINT class_unique IF NOT EXISTS FOR (c:Class) REQUIRE (c.name, c.path, c.line_number) IS UNIQUE",
	"CREATE CONSTRAINT trait_unique IF NOT EXISTS FOR (t:Trait) REQUIRE (t.name, t.path, t.line_number) IS UNIQUE",
	"CREATE CONSTRAINT interface_unique IF NOT EXISTS FOR (i:Interface) REQUIRE (i.name, i.path, i.line_number) IS UNIQUE",
	"CREATE CONSTRAINT macro_unique IF NOT EXISTS FOR (m:Macro) REQUIRE (m.name, m.path, m.line_number) IS UNIQUE",
	"CREATE CONSTRAINT variable_unique IF NOT EXISTS FOR (v:Variable) REQUIRE (v.name, v.path, v.line_number) IS UNIQUE",
	"CREATE CONSTRAINT module_name IF NOT EXISTS FOR (m:Module) REQUIRE m.name IS UNIQUE",
	"CREATE CONSTRAINT struct_cpp IF NOT EXISTS FOR (cstruct: Struct) REQUIRE (cstruct.name, cstruct.path, cstruct.line_number) IS UNIQUE",
	"CREATE CONSTRAINT enum_cpp IF NOT EXISTS FOR (cenum: Enum) REQUIRE (cenum.name, cenum.path, cenum.line_number) IS UNIQUE",
	"CREATE CONSTRAINT union_cpp IF NOT EXISTS FOR (cunion: Union) REQUIRE (cunion.name, cunion.path, cunion.line_number) IS UNIQUE",
	"CREATE CONSTRAINT annotation_unique IF NOT EXISTS FOR (a:Annotation) REQUIRE (a.name, a.path, a.line_number) IS UNIQUE",
	"CREATE CONSTRAINT record_unique IF NOT EXISTS FOR (r:Record) REQUIRE (r.name, r.path, r.line_number) IS UNIQUE",
	"CREATE CONSTRAINT property_unique IF NOT EXISTS FOR (p:Property) REQUIRE (p.name, p.path, p.line_number) IS UNIQUE",

	// Infrastructure entity constraints
	"CREATE CONSTRAINT k8s_resource_unique IF NOT EXISTS FOR (k:K8sResource) REQUIRE (k.name, k.kind, k.path, k.line_number) IS UNIQUE",
	"CREATE CONSTRAINT argocd_app_unique IF NOT EXISTS FOR (a:ArgoCDApplication) REQUIRE (a.name, a.path, a.line_number) IS UNIQUE",
	"CREATE CONSTRAINT argocd_appset_unique IF NOT EXISTS FOR (a:ArgoCDApplicationSet) REQUIRE (a.name, a.path, a.line_number) IS UNIQUE",
	"CREATE CONSTRAINT xrd_unique IF NOT EXISTS FOR (x:CrossplaneXRD) REQUIRE (x.name, x.path, x.line_number) IS UNIQUE",
	"CREATE CONSTRAINT composition_unique IF NOT EXISTS FOR (c:CrossplaneComposition) REQUIRE (c.name, c.path, c.line_number) IS UNIQUE",
	"CREATE CONSTRAINT claim_unique IF NOT EXISTS FOR (cl:CrossplaneClaim) REQUIRE (cl.name, cl.kind, cl.path, cl.line_number) IS UNIQUE",
	"CREATE CONSTRAINT kustomize_unique IF NOT EXISTS FOR (ko:KustomizeOverlay) REQUIRE ko.path IS UNIQUE",
	"CREATE CONSTRAINT helm_chart_unique IF NOT EXISTS FOR (h:HelmChart) REQUIRE (h.name, h.path) IS UNIQUE",
	"CREATE CONSTRAINT helm_values_unique IF NOT EXISTS FOR (hv:HelmValues) REQUIRE hv.path IS UNIQUE",

	// Terraform entity constraints
	"CREATE CONSTRAINT tf_resource_unique IF NOT EXISTS FOR (r:TerraformResource) REQUIRE (r.name, r.path, r.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tf_variable_unique IF NOT EXISTS FOR (v:TerraformVariable) REQUIRE (v.name, v.path, v.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tf_output_unique IF NOT EXISTS FOR (o:TerraformOutput) REQUIRE (o.name, o.path, o.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tf_module_unique IF NOT EXISTS FOR (m:TerraformModule) REQUIRE (m.name, m.path) IS UNIQUE",
	"CREATE CONSTRAINT tf_datasource_unique IF NOT EXISTS FOR (ds:TerraformDataSource) REQUIRE (ds.name, ds.path, ds.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tf_provider_unique IF NOT EXISTS FOR (p:TerraformProvider) REQUIRE (p.name, p.path, p.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tf_local_unique IF NOT EXISTS FOR (l:TerraformLocal) REQUIRE (l.name, l.path, l.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tg_config_unique IF NOT EXISTS FOR (tg:TerragruntConfig) REQUIRE tg.path IS UNIQUE",
	"CREATE CONSTRAINT tg_dependency_unique IF NOT EXISTS FOR (td:TerragruntDependency) REQUIRE (td.name, td.path, td.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tg_input_unique IF NOT EXISTS FOR (ti:TerragruntInput) REQUIRE (ti.name, ti.path, ti.line_number) IS UNIQUE",
	"CREATE CONSTRAINT tg_local_unique IF NOT EXISTS FOR (tl:TerragruntLocal) REQUIRE (tl.name, tl.path, tl.line_number) IS UNIQUE",

	// Type annotation constraint
	"CREATE CONSTRAINT type_annotation_unique IF NOT EXISTS FOR (ta:TypeAnnotation) REQUIRE (ta.name, ta.path, ta.line_number) IS UNIQUE",

	// CloudFormation entity constraints
	"CREATE CONSTRAINT cf_resource_unique IF NOT EXISTS FOR (r:CloudFormationResource) REQUIRE (r.name, r.path, r.line_number) IS UNIQUE",
	"CREATE CONSTRAINT cf_parameter_unique IF NOT EXISTS FOR (p:CloudFormationParameter) REQUIRE (p.name, p.path, p.line_number) IS UNIQUE",
	"CREATE CONSTRAINT cf_output_unique IF NOT EXISTS FOR (o:CloudFormationOutput) REQUIRE (o.name, o.path, o.line_number) IS UNIQUE",

	// Ecosystem / workload constraints
	"CREATE CONSTRAINT ecosystem_name IF NOT EXISTS FOR (e:Ecosystem) REQUIRE e.name IS UNIQUE",
	"CREATE CONSTRAINT tier_name IF NOT EXISTS FOR (t:Tier) REQUIRE t.name IS UNIQUE",
	"CREATE CONSTRAINT workload_id IF NOT EXISTS FOR (w:Workload) REQUIRE w.id IS UNIQUE",
	"CREATE CONSTRAINT workload_instance_id IF NOT EXISTS FOR (i:WorkloadInstance) REQUIRE i.id IS UNIQUE",

	// Platform identity
	"CREATE CONSTRAINT platform_id IF NOT EXISTS FOR (p:Platform) REQUIRE p.id IS UNIQUE",

	// Source-local projection record identity — required for MERGE performance.
	// Without this constraint, MERGE on SourceLocalRecord does a full label scan
	// per row, turning large-repo projection into O(n²).
	"CREATE CONSTRAINT source_local_record_unique IF NOT EXISTS FOR (n:SourceLocalRecord) REQUIRE (n.scope_id, n.generation_id, n.record_id) IS UNIQUE",

	// Parameter constraint
	"CREATE CONSTRAINT parameter_unique IF NOT EXISTS FOR (p:Parameter) REQUIRE (p.name, p.path, p.function_line_number) IS UNIQUE",
}

// uidConstraintLabels lists entity labels that receive a uid uniqueness
// constraint. The set is maintained here as part of the Go-owned graph schema.
var uidConstraintLabels = []string{
	"AnalyticsModel",
	"Annotation",
	"ArgoCDApplication",
	"ArgoCDApplicationSet",
	"Class",
	"CloudFormationOutput",
	"CloudFormationParameter",
	"CloudFormationResource",
	"CrossplaneClaim",
	"CrossplaneComposition",
	"CrossplaneXRD",
	"DashboardAsset",
	"DataAsset",
	"DataColumn",
	"DataContract",
	"DataOwner",
	"DataQualityCheck",
	"Enum",
	"Function",
	"HelmChart",
	"HelmValues",
	"Interface",
	"KustomizeOverlay",
	"Macro",
	"Property",
	"QueryExecution",
	"Record",
	"SqlColumn",
	"SqlFunction",
	"SqlIndex",
	"SqlTable",
	"SqlTrigger",
	"SqlView",
	"Struct",
	"TerraformDataSource",
	"TerraformLocal",
	"TerraformModule",
	"TerraformOutput",
	"TerraformProvider",
	"TerraformResource",
	"TerraformVariable",
	"TerragruntConfig",
	"TerragruntDependency",
	"TerragruntInput",
	"TerragruntLocal",
	"TypeAlias",
	"TypeAnnotation",
	"Typedef",
	"Trait",
	"Union",
	"Variable",
	"Component",
}

// schemaPerformanceIndexes lists secondary indexes that improve query
// performance for common access patterns.
var schemaPerformanceIndexes = []string{
	"CREATE INDEX function_lang IF NOT EXISTS FOR (f:Function) ON (f.lang)",
	"CREATE INDEX class_lang IF NOT EXISTS FOR (c:Class) ON (c.lang)",
	"CREATE INDEX annotation_lang IF NOT EXISTS FOR (a:Annotation) ON (a.lang)",
	"CREATE INDEX k8s_kind IF NOT EXISTS FOR (k:K8sResource) ON (k.kind)",
	"CREATE INDEX k8s_namespace IF NOT EXISTS FOR (k:K8sResource) ON (k.namespace)",
	"CREATE INDEX tf_resource_type IF NOT EXISTS FOR (r:TerraformResource) ON (r.resource_type)",
	"CREATE INDEX workload_name IF NOT EXISTS FOR (w:Workload) ON (w.name)",
	"CREATE INDEX workload_repo_id IF NOT EXISTS FOR (w:Workload) ON (w.repo_id)",
	"CREATE INDEX workload_instance_environment IF NOT EXISTS FOR (i:WorkloadInstance) ON (i.environment)",
	"CREATE INDEX function_name IF NOT EXISTS FOR (f:Function) ON (f.name)",
	"CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
}

// schemaFulltextIndexes lists Neo4j full-text index creation statements.
// The primary form uses the procedure-based API; the fallback uses modern
// CREATE FULLTEXT INDEX syntax for newer Neo4j versions.
var schemaFulltextIndexes = []fulltextIndex{
	{
		primary: "CALL db.index.fulltext.createNodeIndex('code_search_index', " +
			"['Function', 'Class', 'Variable'], ['name', 'source', 'docstring'])",
		fallback: "CREATE FULLTEXT INDEX code_search_index IF NOT EXISTS " +
			"FOR (n:Function|Class|Variable) ON EACH [n.name, n.source, n.docstring]",
	},
	{
		primary: "CALL db.index.fulltext.createNodeIndex('infra_search_index', " +
			"['K8sResource', 'TerraformResource', 'ArgoCDApplication', " +
			"'ArgoCDApplicationSet', 'CrossplaneXRD', 'CrossplaneComposition', " +
			"'CrossplaneClaim', 'KustomizeOverlay', 'HelmChart', 'HelmValues', " +
			"'TerraformVariable', 'TerraformOutput', 'TerraformModule', " +
			"'TerraformDataSource', 'TerraformProvider', 'TerraformLocal', " +
			"'TerragruntConfig', 'CloudFormationResource', " +
			"'CloudFormationParameter', 'CloudFormationOutput'], " +
			"['name', 'kind', 'resource_type'])",
		fallback: "CREATE FULLTEXT INDEX infra_search_index IF NOT EXISTS " +
			"FOR (n:K8sResource|TerraformResource|ArgoCDApplication|" +
			"ArgoCDApplicationSet|CrossplaneXRD|CrossplaneComposition|" +
			"CrossplaneClaim|KustomizeOverlay|HelmChart|HelmValues|" +
			"TerraformVariable|TerraformOutput|TerraformModule|" +
			"TerraformDataSource|TerraformProvider|TerraformLocal|" +
			"TerragruntConfig|CloudFormationResource|" +
			"CloudFormationParameter|CloudFormationOutput) " +
			"ON EACH [n.name, n.kind, n.resource_type]",
	},
}

// fulltextIndex pairs a primary procedure-based fulltext statement with
// its modern CREATE FULLTEXT INDEX fallback.
type fulltextIndex struct {
	primary  string
	fallback string
}

// SchemaStatements returns the complete ordered list of Cypher statements
// that EnsureSchema would execute. Useful for inspection and testing.
func SchemaStatements() []string {
	stmts := make([]string, 0,
		len(schemaConstraints)+
			len(uidConstraintLabels)+
			len(schemaPerformanceIndexes)+
			len(schemaFulltextIndexes))
	stmts = append(stmts, schemaConstraints...)
	stmts = append(stmts, schemaPerformanceIndexes...)
	for _, label := range uidConstraintLabels {
		stmts = append(stmts, fmt.Sprintf(
			"CREATE CONSTRAINT %s_uid_unique IF NOT EXISTS FOR (n:%s) REQUIRE n.uid IS UNIQUE",
			labelToSnake(label), label,
		))
	}
	for _, ft := range schemaFulltextIndexes {
		stmts = append(stmts, ft.primary)
	}
	return stmts
}

// EnsureSchema creates all constraints and indexes required by the platform
// context graph. Each statement is executed individually; failures are logged
// as warnings but do not abort the remaining statements. Full-text index
// creation automatically falls back to modern syntax when the procedure-based
// API is unavailable.
func EnsureSchema(ctx context.Context, executor CypherExecutor, logger *slog.Logger) error {
	if executor == nil {
		return fmt.Errorf("schema executor is required")
	}
	if logger == nil {
		logger = slog.Default()
	}

	var failed int

	// Constraints
	for _, cypher := range schemaConstraints {
		if err := executeSchemaStatement(ctx, executor, cypher); err != nil {
			failed++
			logger.Warn("schema statement warning", "error", err, "cypher", cypher)
		}
	}

	// Performance indexes
	for _, cypher := range schemaPerformanceIndexes {
		if err := executeSchemaStatement(ctx, executor, cypher); err != nil {
			failed++
			logger.Warn("schema statement warning", "error", err, "cypher", cypher)
		}
	}

	// UID uniqueness constraints for content entity labels
	for _, label := range uidConstraintLabels {
		cypher := fmt.Sprintf(
			"CREATE CONSTRAINT %s_uid_unique IF NOT EXISTS FOR (n:%s) REQUIRE n.uid IS UNIQUE",
			labelToSnake(label), label,
		)
		if err := executeSchemaStatement(ctx, executor, cypher); err != nil {
			failed++
			logger.Warn("schema statement warning", "error", err, "cypher", cypher)
		}
	}

	// Full-text indexes with fallback
	for _, ft := range schemaFulltextIndexes {
		if err := executeSchemaStatement(ctx, executor, ft.primary); err != nil {
			if err2 := executeSchemaStatement(ctx, executor, ft.fallback); err2 != nil {
				failed++
				logger.Warn("fulltext index warning",
					"primary_error", err, "fallback_error", err2,
					"primary", ft.primary, "fallback", ft.fallback)
			}
		}
	}

	if failed > 0 {
		logger.Warn("schema creation completed with warnings", "failed", failed)
	} else {
		logger.Info("database schema verified/created successfully")
	}

	return nil
}

// executeSchemaStatement runs one DDL statement through the executor.
func executeSchemaStatement(ctx context.Context, executor CypherExecutor, cypher string) error {
	return executor.ExecuteCypher(ctx, CypherStatement{
		Cypher:     cypher,
		Parameters: map[string]any{},
	})
}

// labelToSnake converts a PascalCase label to lower_snake_case for use in
// constraint names (e.g., "CrossplaneXRD" -> "crossplanexrd").
func labelToSnake(label string) string {
	result := make([]byte, 0, len(label)+4)
	for i, b := range []byte(label) {
		if b >= 'A' && b <= 'Z' {
			lower := b + ('a' - 'A')
			if i > 0 {
				result = append(result, '_')
			}
			result = append(result, lower)
		} else {
			result = append(result, b)
		}
	}
	return string(result)
}
