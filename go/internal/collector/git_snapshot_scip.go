package collector

import (
	"context"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/collector/discovery"
	"github.com/platformcontext/platform-context-graph/go/internal/content/shape"
	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

// SnapshotSCIPConfig captures the optional SCIP runtime contract for the Go collector.
type SnapshotSCIPConfig struct {
	Enabled   bool
	Languages []string
	Indexer   scipProjectIndexer
	Parser    scipResultParser
}

type scipProjectIndexer interface {
	IsAvailable(string) bool
	Run(context.Context, string, string, string) (string, error)
}

type scipResultParser interface {
	Parse(string, string) (parser.SCIPParseResult, error)
}

// LoadSnapshotSCIPConfig parses the SCIP environment contract for the Go collector.
func LoadSnapshotSCIPConfig(getenv func(string) string) SnapshotSCIPConfig {
	languages := []string{"python", "typescript", "go", "rust", "java"}
	if raw := strings.TrimSpace(getenv("SCIP_LANGUAGES")); raw != "" {
		languages = languages[:0]
		for _, item := range strings.Split(raw, ",") {
			item = strings.TrimSpace(strings.ToLower(item))
			if item != "" {
				languages = append(languages, item)
			}
		}
	}
	return SnapshotSCIPConfig{
		Enabled:   boolFromEnv(getenv("SCIP_INDEXER")),
		Languages: languages,
	}
}

func (s NativeRepositorySnapshotter) scipConfig() SnapshotSCIPConfig {
	return s.SCIP
}

func (s NativeRepositorySnapshotter) scipIndexer(config SnapshotSCIPConfig) scipProjectIndexer {
	if config.Indexer != nil {
		return config.Indexer
	}
	return parser.SCIPIndexer{}
}

func (s NativeRepositorySnapshotter) scipParser(config SnapshotSCIPConfig) scipResultParser {
	if config.Parser != nil {
		return config.Parser
	}
	return parser.SCIPIndexParser{}
}

func (s NativeRepositorySnapshotter) buildParsedRepositoryFiles(
	ctx context.Context,
	repoPath string,
	fileSet discovery.RepoFileSet,
	engine *parser.Engine,
	commitSHA string,
) ([]shape.File, []map[string]any, error) {
	if shapeFiles, parsedFiles, used, err := s.trySCIPSnapshot(ctx, repoPath, fileSet, engine, commitSHA); err != nil {
		return nil, nil, err
	} else if used {
		return shapeFiles, parsedFiles, nil
	}

	shapeFiles := make([]shape.File, 0, len(fileSet.Files))
	parsedFiles := make([]map[string]any, 0, len(fileSet.Files))
	for _, filePath := range fileSet.Files {
		if err := ctx.Err(); err != nil {
			return nil, nil, err
		}

		parsed, err := engine.ParsePath(repoPath, filePath, false, parser.Options{
			IndexSource:   true,
			VariableScope: "all",
		})
		if err != nil {
			return nil, nil, err
		}
		body, err := os.ReadFile(filePath)
		if err != nil {
			return nil, nil, err
		}

		relativePath, err := filepath.Rel(repoPath, filePath)
		if err != nil {
			return nil, nil, err
		}
		relativePath = filepath.ToSlash(filepath.Clean(relativePath))
		shapeFiles = append(shapeFiles, shapeFileFromParsed(parsed, relativePath, string(body), commitSHA))
		parsedFiles = append(parsedFiles, parsed)
	}
	return shapeFiles, parsedFiles, nil
}

func (s NativeRepositorySnapshotter) trySCIPSnapshot(
	ctx context.Context,
	repoPath string,
	fileSet discovery.RepoFileSet,
	engine *parser.Engine,
	commitSHA string,
) ([]shape.File, []map[string]any, bool, error) {
	config := s.scipConfig()
	if !config.Enabled {
		return nil, nil, false, nil
	}

	language := parser.DetectSCIPProjectLanguage(fileSet.Files, config.Languages)
	if language == "" {
		return nil, nil, false, nil
	}
	indexer := s.scipIndexer(config)
	if !indexer.IsAvailable(language) {
		return nil, nil, false, nil
	}

	outputDir, err := os.MkdirTemp("", "pcg-scip-*")
	if err != nil {
		return nil, nil, false, err
	}
	defer os.RemoveAll(outputDir)

	indexPath, err := indexer.Run(ctx, repoPath, language, outputDir)
	if err != nil {
		return nil, nil, false, nil
	}
	result, err := s.scipParser(config).Parse(indexPath, repoPath)
	if err != nil {
		return nil, nil, false, nil
	}

	selectedFiles := make(map[string]struct{}, len(fileSet.Files))
	for _, path := range fileSet.Files {
		selectedFiles[path] = struct{}{}
	}
	orderedFiles := make([]string, 0, len(result.Files))
	for path := range result.Files {
		if _, ok := selectedFiles[path]; ok {
			orderedFiles = append(orderedFiles, path)
		}
	}
	slices.Sort(orderedFiles)

	shapeFiles := make([]shape.File, 0, len(orderedFiles))
	parsedFiles := make([]map[string]any, 0, len(orderedFiles))
	for _, filePath := range orderedFiles {
		if err := ctx.Err(); err != nil {
			return nil, nil, false, err
		}

		parsed := clonePayload(result.Files[filePath])
		supplement, err := engine.ParsePath(repoPath, filePath, false, parser.Options{
			IndexSource:   true,
			VariableScope: "all",
		})
		if err != nil {
			return nil, nil, false, nil
		}
		mergeSCIPSupplement(parsed, supplement)
		parsed["repo_path"] = repoPath

		body, err := os.ReadFile(filePath)
		if err != nil {
			return nil, nil, false, nil
		}
		relativePath, err := filepath.Rel(repoPath, filePath)
		if err != nil {
			return nil, nil, false, err
		}
		relativePath = filepath.ToSlash(filepath.Clean(relativePath))
		shapeFiles = append(shapeFiles, shapeFileFromParsed(parsed, relativePath, string(body), commitSHA))
		parsedFiles = append(parsedFiles, parsed)
	}

	if len(parsedFiles) == 0 {
		return nil, nil, false, nil
	}
	return shapeFiles, parsedFiles, true, nil
}

func mergeSCIPSupplement(parsed map[string]any, supplement map[string]any) {
	parsed["imports"] = supplement["imports"]
	parsed["variables"] = supplement["variables"]
	parsed["functions"] = mergeNamedEntities(
		parsed["functions"],
		supplement["functions"],
		[]string{"source", "cyclomatic_complexity", "decorators", "context", "class_context", "start_byte", "end_byte", "end_line"},
	)
	parsed["classes"] = mergeNamedEntities(
		parsed["classes"],
		supplement["classes"],
		[]string{"bases", "context", "source", "start_byte", "end_byte", "end_line"},
	)
}

func mergeNamedEntities(current any, supplement any, keys []string) []map[string]any {
	currentItems, _ := current.([]map[string]any)
	supplementItems, _ := supplement.([]map[string]any)
	byName := make(map[string]map[string]any, len(supplementItems))
	for _, item := range supplementItems {
		name := snapshotPayloadString(item, "name")
		if name != "" {
			byName[name] = item
		}
	}
	for i := range currentItems {
		name := snapshotPayloadString(currentItems[i], "name")
		supplementItem, ok := byName[name]
		if !ok {
			continue
		}
		for _, key := range keys {
			if value, ok := supplementItem[key]; ok {
				currentItems[i][key] = value
			}
		}
	}
	return currentItems
}

func shapeFileFromParsed(parsed map[string]any, relativePath string, body string, commitSHA string) shape.File {
	return shape.File{
		Path:            relativePath,
		Body:            body,
		Digest:          digestForBody(body),
		Language:        snapshotPayloadString(parsed, "language", "lang"),
		ArtifactType:    snapshotPayloadString(parsed, "artifact_type"),
		TemplateDialect: snapshotPayloadString(parsed, "template_dialect"),
		IACRelevant:     snapshotPayloadBoolPtr(parsed, "iac_relevant"),
		CommitSHA:       commitSHA,
		EntityBuckets:   entityBucketsFromParsed(parsed),
	}
}

func clonePayload(values map[string]any) map[string]any {
	cloned := make(map[string]any, len(values))
	for key, value := range values {
		cloned[key] = value
	}
	return cloned
}
