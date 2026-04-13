package shape

import (
	"fmt"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
)

// Input captures one normalized parser payload batch for content shaping.
type Input struct {
	RepoID       string
	SourceSystem string
	Files        []File
}

// File captures one parser-shaped file payload and its nested entity buckets.
type File struct {
	Path            string
	Body            string
	Digest          string
	Language        string
	ArtifactType    string
	TemplateDialect string
	IACRelevant     *bool
	CommitSHA       string
	Metadata        map[string]string
	Deleted         bool
	EntityBuckets   map[string][]Entity
}

// Entity captures one parser-shaped entity payload.
type Entity struct {
	Name            string
	LineNumber      int
	EndLine         int
	StartByte       *int
	EndByte         *int
	Language        string
	ArtifactType    string
	TemplateDialect string
	IACRelevant     *bool
	Source          string
	Deleted         bool
}

type entityBucketMapping struct {
	bucket string
	label  string
}

var contentEntityBuckets = []entityBucketMapping{
	{bucket: "functions", label: "Function"},
	{bucket: "classes", label: "Class"},
	{bucket: "variables", label: "Variable"},
	{bucket: "traits", label: "Trait"},
	{bucket: "interfaces", label: "Interface"},
	{bucket: "macros", label: "Macro"},
	{bucket: "structs", label: "Struct"},
	{bucket: "enums", label: "Enum"},
	{bucket: "unions", label: "Union"},
	{bucket: "annotations", label: "Annotation"},
	{bucket: "records", label: "Record"},
	{bucket: "properties", label: "Property"},
	{bucket: "k8s_resources", label: "K8sResource"},
	{bucket: "argocd_applications", label: "ArgoCDApplication"},
	{bucket: "argocd_applicationsets", label: "ArgoCDApplicationSet"},
	{bucket: "crossplane_xrds", label: "CrossplaneXRD"},
	{bucket: "crossplane_compositions", label: "CrossplaneComposition"},
	{bucket: "crossplane_claims", label: "CrossplaneClaim"},
	{bucket: "kustomize_overlays", label: "KustomizeOverlay"},
	{bucket: "helm_charts", label: "HelmChart"},
	{bucket: "helm_values", label: "HelmValues"},
	{bucket: "terraform_resources", label: "TerraformResource"},
	{bucket: "terraform_variables", label: "TerraformVariable"},
	{bucket: "terraform_outputs", label: "TerraformOutput"},
	{bucket: "terraform_modules", label: "TerraformModule"},
	{bucket: "terraform_data_sources", label: "TerraformDataSource"},
	{bucket: "terraform_providers", label: "TerraformProvider"},
	{bucket: "terraform_locals", label: "TerraformLocal"},
	{bucket: "terragrunt_configs", label: "TerragruntConfig"},
	{bucket: "cloudformation_resources", label: "CloudFormationResource"},
	{bucket: "cloudformation_parameters", label: "CloudFormationParameter"},
	{bucket: "cloudformation_outputs", label: "CloudFormationOutput"},
	{bucket: "sql_tables", label: "SqlTable"},
	{bucket: "sql_columns", label: "SqlColumn"},
	{bucket: "sql_views", label: "SqlView"},
	{bucket: "sql_functions", label: "SqlFunction"},
	{bucket: "sql_triggers", label: "SqlTrigger"},
	{bucket: "sql_indexes", label: "SqlIndex"},
	{bucket: "analytics_models", label: "AnalyticsModel"},
	{bucket: "data_assets", label: "DataAsset"},
	{bucket: "data_columns", label: "DataColumn"},
	{bucket: "query_executions", label: "QueryExecution"},
	{bucket: "dashboard_assets", label: "DashboardAsset"},
	{bucket: "data_quality_checks", label: "DataQualityCheck"},
	{bucket: "data_owners", label: "DataOwner"},
	{bucket: "data_contracts", label: "DataContract"},
}

var sourceFieldContainsCode = map[string]struct{}{
	"Annotation": {},
	"Class":      {},
	"Enum":       {},
	"Function":   {},
	"Interface":  {},
	"Macro":      {},
	"Property":   {},
	"Record":     {},
	"Struct":     {},
	"Trait":      {},
	"Union":      {},
	"Variable":   {},
}

var trailingNewlineLabels = map[string]struct{}{
	"Annotation":              {},
	"ArgoCDApplication":       {},
	"ArgoCDApplicationSet":    {},
	"Class":                   {},
	"CloudFormationOutput":    {},
	"CloudFormationParameter": {},
	"CloudFormationResource":  {},
	"CrossplaneClaim":         {},
	"CrossplaneComposition":   {},
	"CrossplaneXRD":           {},
	"Enum":                    {},
	"Function":                {},
	"HelmChart":               {},
	"HelmValues":              {},
	"Interface":               {},
	"K8sResource":             {},
	"KustomizeOverlay":        {},
	"Macro":                   {},
	"Property":                {},
	"Record":                  {},
	"SqlColumn":               {},
	"SqlFunction":             {},
	"SqlIndex":                {},
	"SqlTable":                {},
	"SqlTrigger":              {},
	"SqlView":                 {},
	"Struct":                  {},
	"TerragruntConfig":        {},
	"TerraformDataSource":     {},
	"TerraformLocal":          {},
	"TerraformModule":         {},
	"TerraformOutput":         {},
	"TerraformProvider":       {},
	"TerraformResource":       {},
	"TerraformVariable":       {},
	"Trait":                   {},
	"Union":                   {},
	"Variable":                {},
}

// Materialize converts parser-shaped payloads into canonical content rows.
func Materialize(input Input) (content.Materialization, error) {
	repoID := strings.TrimSpace(input.RepoID)
	if repoID == "" {
		return content.Materialization{}, fmt.Errorf("repo_id is required")
	}

	materialization := content.Materialization{
		RepoID:       repoID,
		SourceSystem: strings.TrimSpace(input.SourceSystem),
	}

	for _, file := range input.Files {
		record, entities, err := materializeFile(repoID, file)
		if err != nil {
			return content.Materialization{}, err
		}
		materialization.Records = append(materialization.Records, record)
		materialization.Entities = append(materialization.Entities, entities...)
	}

	return materialization, nil
}

func materializeFile(repoID string, file File) (content.Record, []content.EntityRecord, error) {
	path := strings.TrimSpace(file.Path)
	if path == "" {
		return content.Record{}, nil, fmt.Errorf("content file path is required")
	}

	record := content.Record{
		Path:     path,
		Body:     file.Body,
		Digest:   strings.TrimSpace(file.Digest),
		Deleted:  file.Deleted,
		Metadata: normalizeFileMetadata(file),
	}

	entities, err := materializeEntities(repoID, path, file)
	if err != nil {
		return content.Record{}, nil, err
	}

	return record, entities, nil
}

func normalizeFileMetadata(file File) map[string]string {
	metadata := cloneStringMap(file.Metadata)
	if metadata == nil {
		metadata = make(map[string]string)
	}
	setString(metadata, "language", file.Language)
	setString(metadata, "artifact_type", file.ArtifactType)
	setString(metadata, "template_dialect", file.TemplateDialect)
	if file.IACRelevant != nil {
		setString(metadata, "iac_relevant", strings.ToLower(fmt.Sprintf("%t", *file.IACRelevant)))
	}
	setString(metadata, "commit_sha", file.CommitSHA)

	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func materializeEntities(repoID string, path string, file File) ([]content.EntityRecord, error) {
	indexedItems := make([]indexedEntity, 0)
	for _, bucket := range contentEntityBuckets {
		items := file.EntityBuckets[bucket.bucket]
		for _, item := range items {
			indexedItems = append(indexedItems, indexedEntity{
				label: bucket.label,
				item:  item,
			})
		}
	}

	sort.SliceStable(indexedItems, func(i, j int) bool {
		left := indexedItems[i]
		right := indexedItems[j]
		if left.lineNumber() != right.lineNumber() {
			return left.lineNumber() < right.lineNumber()
		}
		if left.label != right.label {
			return left.label < right.label
		}
		return left.item.Name < right.item.Name
	})

	entities := make([]content.EntityRecord, 0, len(indexedItems))
	for index, indexed := range indexedItems {
		startLine := indexed.lineNumber()
		endLine := entityEndLine(indexedItems, index, file.Body, startLine)
		sourceCache := entitySourceCache(indexed.label, indexed.item, file.Body, startLine, endLine)
		entities = append(entities, content.EntityRecord{
			EntityID:        content.CanonicalEntityID(repoID, path, indexed.label, indexed.item.Name, startLine),
			Path:            path,
			EntityType:      indexed.label,
			EntityName:      indexed.item.Name,
			StartLine:       startLine,
			EndLine:         endLine,
			StartByte:       indexed.item.StartByte,
			EndByte:         indexed.item.EndByte,
			Language:        firstNonEmpty(indexed.item.Language, file.Language),
			ArtifactType:    firstNonEmpty(indexed.item.ArtifactType, file.ArtifactType),
			TemplateDialect: firstNonEmpty(indexed.item.TemplateDialect, file.TemplateDialect),
			IACRelevant:     cloneBoolPtr(firstBool(indexed.item.IACRelevant, file.IACRelevant)),
			SourceCache:     sourceCache,
			Deleted:         indexed.item.Deleted,
		})
	}

	return entities, nil
}

type indexedEntity struct {
	label string
	item  Entity
}

func (e indexedEntity) lineNumber() int {
	if e.item.LineNumber >= 1 {
		return e.item.LineNumber
	}
	return 1
}

func entityEndLine(items []indexedEntity, index int, body string, startLine int) int {
	item := items[index].item
	if item.EndLine >= startLine {
		return item.EndLine
	}
	if nextLine := nextLineNumber(items, index, startLine); nextLine != nil {
		if candidate := *nextLine - 1; candidate >= startLine {
			return candidate
		}
	}
	if totalLines := lineCount(body); totalLines > 0 {
		candidate := startLine + 24
		if totalLines < candidate {
			candidate = totalLines
		}
		if candidate < startLine {
			return startLine
		}
		return candidate
	}
	return startLine
}

func nextLineNumber(items []indexedEntity, index int, startLine int) *int {
	for _, candidate := range items[index+1:] {
		line := candidate.lineNumber()
		if line >= startLine {
			cloned := line
			return &cloned
		}
	}
	return nil
}

func entitySourceCache(label string, item Entity, body string, startLine int, endLine int) string {
	if isCodeSourceLabel(label) && strings.TrimSpace(item.Source) != "" {
		return withTrailingNewline(item.Source, label)
	}

	lines := splitLines(body)
	if len(lines) > 0 && startLine >= 1 {
		startIndex := startLine - 1
		if startIndex < len(lines) {
			endIndex := endLine
			if endIndex > len(lines) {
				endIndex = len(lines)
			}
			if endIndex > startIndex {
				selected := strings.Join(lines[startIndex:endIndex], "\n")
				return withTrailingNewline(selected, label)
			}
		}
	}

	if strings.TrimSpace(item.Source) != "" {
		return item.Source
	}
	return ""
}

func splitLines(body string) []string {
	if body == "" {
		return nil
	}

	normalized := strings.ReplaceAll(body, "\r\n", "\n")
	lines := strings.Split(normalized, "\n")
	if strings.HasSuffix(normalized, "\n") && len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	return lines
}

func lineCount(body string) int {
	if body == "" {
		return 0
	}
	return len(splitLines(body))
}

func withTrailingNewline(contentText string, label string) string {
	if _, ok := trailingNewlineLabels[label]; !ok {
		return contentText
	}
	if contentText == "" || strings.HasSuffix(contentText, "\n") {
		return contentText
	}
	return contentText + "\n"
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func firstBool(values ...*bool) *bool {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func cloneBoolPtr(value *bool) *bool {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

func cloneStringMap(input map[string]string) map[string]string {
	if input == nil {
		return nil
	}
	cloned := make(map[string]string, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}

func setString(target map[string]string, key string, value string) {
	if strings.TrimSpace(value) == "" {
		return
	}
	target[key] = value
}

func isCodeSourceLabel(label string) bool {
	_, ok := sourceFieldContainsCode[label]
	return ok
}
