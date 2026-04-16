package neo4j

// Cypher templates for canonical node projection phases.
// These are used by CanonicalNodeWriter in strict phase order.

// --- Phase A: Retraction Cypher ---

const canonicalNodeRetractFilesCypher = `MATCH (f:File)
WHERE f.repo_id = $repo_id AND f.evidence_source = 'projector/canonical' AND f.generation_id <> $generation_id
DETACH DELETE f`

const canonicalNodeRetractCodeEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:Function OR n:Class OR n:Variable OR n:Interface OR n:Trait OR n:Struct OR n:Enum OR n:Macro OR n:Union OR n:Record OR n:Property)
DETACH DELETE n`

const canonicalNodeRetractInfraEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:K8sResource OR n:ArgoCDApplication OR n:ArgoCDApplicationSet OR n:CrossplaneXRD OR n:CrossplaneComposition OR n:CrossplaneClaim OR n:KustomizeOverlay OR n:HelmChart OR n:HelmValues)
DETACH DELETE n`

const canonicalNodeRetractTerraformEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:TerraformResource OR n:TerraformModule OR n:TerraformVariable OR n:TerraformOutput OR n:TerraformDataSource OR n:TerraformProvider OR n:TerraformLocal OR n:TerragruntConfig)
DETACH DELETE n`

const canonicalNodeRetractCloudFormationEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:CloudFormationResource OR n:CloudFormationParameter OR n:CloudFormationOutput)
DETACH DELETE n`

const canonicalNodeRetractSQLEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:SqlTable OR n:SqlView OR n:SqlFunction OR n:SqlTrigger OR n:SqlIndex OR n:SqlColumn)
DETACH DELETE n`

const canonicalNodeRetractDataEntitiesCypher = `MATCH (n)
WHERE n.repo_id = $repo_id AND n.evidence_source = 'projector/canonical' AND n.generation_id <> $generation_id
  AND (n:DataAsset OR n:DataColumn OR n:AnalyticsModel OR n:DashboardAsset OR n:DataQualityCheck OR n:QueryExecution OR n:DataContract OR n:DataOwner)
DETACH DELETE n`

const canonicalNodeRetractDirectoriesCypher = `MATCH (d:Directory)
WHERE d.repo_id = $repo_id AND d.generation_id <> $generation_id
DETACH DELETE d`

const canonicalNodeRetractParametersCypher = `MATCH (p:Parameter)
WHERE p.path IN $file_paths AND p.evidence_source = 'projector/canonical'
DETACH DELETE p`

// --- Phase B: Repository Cypher ---

const canonicalNodeRepositoryUpsertCypher = `MERGE (r:Repository {id: $repo_id})
SET r.name = $name, r.path = $path, r.local_path = $local_path,
    r.remote_url = $remote_url, r.repo_slug = $repo_slug,
    r.has_remote = $has_remote, r.scope_id = $scope_id,
    r.generation_id = $generation_id,
    r.evidence_source = 'projector/canonical'`

// --- Phase C: Directory Cypher ---

const canonicalNodeDirectoryDepth0Cypher = `UNWIND $rows AS row
MATCH (r:Repository {id: row.repo_id})
MERGE (d:Directory {path: row.path})
SET d.name = row.name, d.repo_id = row.repo_id,
    d.scope_id = row.scope_id, d.generation_id = row.generation_id
MERGE (r)-[:CONTAINS]->(d)`

const canonicalNodeDirectoryDepthNCypher = `UNWIND $rows AS row
MATCH (p:Directory {path: row.parent_path})
MERGE (d:Directory {path: row.path})
SET d.name = row.name, d.repo_id = row.repo_id,
    d.scope_id = row.scope_id, d.generation_id = row.generation_id
MERGE (p)-[:CONTAINS]->(d)`

// --- Phase D: File Cypher ---

const canonicalNodeFileUpsertCypher = `UNWIND $rows AS row
MERGE (f:File {path: row.path})
SET f.name = row.name, f.relative_path = row.relative_path,
    f.language = row.language, f.lang = row.language,
    f.repo_id = row.repo_id,
    f.scope_id = row.scope_id, f.generation_id = row.generation_id,
    f.evidence_source = 'projector/canonical'
WITH f, row
MATCH (r:Repository {id: row.repo_id})
MERGE (r)-[:REPO_CONTAINS]->(f)
WITH f, row
MATCH (d:Directory {path: row.dir_path})
MERGE (d)-[:CONTAINS]->(f)`

// --- Phase E: Entity Cypher (template — label inserted via fmt.Sprintf) ---

// canonicalNodeEntityUpsertTemplate is formatted with the Neo4j label at write time.
// Use fmt.Sprintf(canonicalNodeEntityUpsertTemplate, label).
const canonicalNodeEntityUpsertTemplate = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:%s {uid: row.entity_id})
SET n.id = row.entity_id, n.name = row.entity_name,
    n.path = row.file_path, n.relative_path = row.relative_path,
    n.line_number = row.start_line, n.start_line = row.start_line,
    n.end_line = row.end_line, n.repo_id = row.repo_id,
    n.language = row.language, n.lang = row.language,
    n.decorators = row.decorators,
    n.type_parameters = row.type_parameters,
    n.declaration_merge_group = row.declaration_merge_group,
    n.declaration_merge_count = row.declaration_merge_count,
    n.declaration_merge_kinds = row.declaration_merge_kinds,
    n.scope_id = row.scope_id, n.generation_id = row.generation_id,
    n.evidence_source = 'projector/canonical'
MERGE (f)-[:CONTAINS]->(n)`

// --- Phase F: Module Cypher ---

const canonicalNodeModuleUpsertCypher = `UNWIND $rows AS row
MERGE (m:Module {name: row.name})
ON CREATE SET m.lang = row.language
ON MATCH SET m.lang = coalesce(m.lang, row.language)`

// --- Phase G: Structural edge Cypher ---

const canonicalNodeImportEdgeCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MATCH (m:Module {name: row.module_name})
MERGE (f)-[r:IMPORTS]->(m)
SET r.imported_name = row.imported_name, r.alias = row.alias, r.line_number = row.line_number`

const canonicalNodeHasParameterEdgeCypher = `UNWIND $rows AS row
MATCH (fn:Function {name: row.func_name, path: row.file_path, line_number: row.func_line})
MERGE (p:Parameter {name: row.param_name, path: row.file_path, function_line_number: row.func_line})
MERGE (fn)-[:HAS_PARAMETER]->(p)
SET p.evidence_source = 'projector/canonical'`

const canonicalNodeClassContainsFuncEdgeCypher = `UNWIND $rows AS row
MATCH (c:Class {name: row.class_name, path: row.file_path})
MATCH (fn:Function {name: row.func_name, path: row.file_path, line_number: row.func_line})
MERGE (c)-[:CONTAINS]->(fn)`

const canonicalNodeNestedFuncEdgeCypher = `UNWIND $rows AS row
MATCH (outer:Function {name: row.outer_name, path: row.file_path})
MATCH (inner:Function {name: row.inner_name, path: row.file_path, line_number: row.inner_line})
MERGE (outer)-[:CONTAINS]->(inner)`
