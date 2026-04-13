package collector

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector/discovery"
	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/content/shape"
	"github.com/platformcontext/platform-context-graph/go/internal/parser"
	"github.com/platformcontext/platform-context-graph/go/internal/repositoryidentity"
)

var snapshotEntityBuckets = []struct {
	bucket string
	label  string
}{
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
}

// NativeRepositorySnapshotter builds repository snapshots without Python bridge code.
type NativeRepositorySnapshotter struct {
	Engine           *parser.Engine
	Registry         parser.Registry
	DiscoveryOptions discovery.Options
	SCIP             SnapshotSCIPConfig
	Now              func() time.Time
}

// SnapshotRepository builds one native repository snapshot for the selected repo.
func (s NativeRepositorySnapshotter) SnapshotRepository(
	ctx context.Context,
	repository SelectedRepository,
) (RepositorySnapshot, error) {
	repoPath, err := filepath.Abs(repository.RepoPath)
	if err != nil {
		return RepositorySnapshot{}, fmt.Errorf("resolve repository path %q: %w", repository.RepoPath, err)
	}
	if resolvedPath, resolveErr := filepath.EvalSymlinks(repoPath); resolveErr == nil {
		repoPath = resolvedPath
	}

	engine, err := s.engine()
	if err != nil {
		return RepositorySnapshot{}, err
	}
	registry := s.registry()
	fileSet, err := resolveNativeSnapshotFileSet(repoPath, registry, s.discoveryOptions())
	if len(repository.FileTargets) > 0 {
		fileSet, err = resolveNativeSnapshotFileSetForTargets(repoPath, repository.FileTargets, registry)
	}
	if err != nil {
		return RepositorySnapshot{}, err
	}

	snapshot := RepositorySnapshot{
		RepoPath:        repoPath,
		RemoteURL:       repository.RemoteURL,
		FileCount:       len(fileSet.Files),
		ImportsMap:      map[string][]string{},
		FileData:        []map[string]any{},
		ContentFiles:    []ContentFileSnapshot{},
		ContentEntities: []ContentEntitySnapshot{},
	}
	if len(fileSet.Files) == 0 {
		return snapshot, nil
	}

	importsMap, err := engine.PreScanPaths(fileSet.Files)
	if err != nil {
		return RepositorySnapshot{}, fmt.Errorf("pre-scan repository imports for %q: %w", repoPath, err)
	}
	snapshot.ImportsMap = importsMap

	repoMetadata, err := repositoryidentity.MetadataFor(
		filepath.Base(repoPath),
		repoPath,
		repository.RemoteURL,
	)
	if err != nil {
		return RepositorySnapshot{}, fmt.Errorf("repository metadata for %q: %w", repoPath, err)
	}
	commitSHA := gitCommitSHA(ctx, repoPath)
	shapeFiles, parsedFiles, err := s.buildParsedRepositoryFiles(
		ctx,
		repoPath,
		fileSet,
		engine,
		commitSHA,
		repository.IsDependency,
	)
	if err != nil {
		return RepositorySnapshot{}, fmt.Errorf("build parsed repository files for %q: %w", repoPath, err)
	}

	materialization, err := shape.Materialize(shape.Input{
		RepoID:       repoMetadata.ID,
		SourceSystem: "git",
		Files:        shapeFiles,
	})
	if err != nil {
		return RepositorySnapshot{}, fmt.Errorf("materialize repository content: %w", err)
	}

	annotateParsedFilesWithEntityIDs(repoPath, parsedFiles, materialization.Entities)
	snapshot.FileData = parsedFiles
	snapshot.ContentFiles = materializationRecordsToSnapshots(materialization.Records)
	snapshot.ContentEntities = materializationEntitiesToSnapshots(materialization.Entities, s.now())
	return snapshot, nil
}

func (s NativeRepositorySnapshotter) engine() (*parser.Engine, error) {
	if s.Engine != nil {
		return s.Engine, nil
	}
	return parser.DefaultEngine()
}

func (s NativeRepositorySnapshotter) registry() parser.Registry {
	if len(s.Registry.ParserKeys()) > 0 {
		return s.Registry
	}
	return parser.DefaultRegistry()
}

func (s NativeRepositorySnapshotter) discoveryOptions() discovery.Options {
	if len(s.DiscoveryOptions.IgnoredDirs) > 0 ||
		s.DiscoveryOptions.IgnoreHidden ||
		len(s.DiscoveryOptions.PreservedHiddenPrefixes) > 0 ||
		s.DiscoveryOptions.HonorGitignore {
		return s.DiscoveryOptions
	}
	return discovery.Options{
		IgnoredDirs:    []string{".git"},
		HonorGitignore: true,
	}
}

func (s NativeRepositorySnapshotter) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}
	return time.Now().UTC()
}

func resolveNativeSnapshotFileSet(
	repoPath string,
	registry parser.Registry,
	opts discovery.Options,
) (discovery.RepoFileSet, error) {
	fileSets, err := discovery.ResolveRepositoryFileSets(
		repoPath,
		func(path string) bool {
			_, ok := registry.LookupByPath(path)
			return ok
		},
		opts,
	)
	if err != nil {
		return discovery.RepoFileSet{}, fmt.Errorf("resolve repository file sets: %w", err)
	}
	for _, fileSet := range fileSets {
		if fileSet.RepoRoot == repoPath {
			return fileSet, nil
		}
	}
	return discovery.RepoFileSet{RepoRoot: repoPath}, nil
}

func resolveNativeSnapshotFileSetForTargets(
	repoPath string,
	fileTargets []string,
	registry parser.Registry,
) (discovery.RepoFileSet, error) {
	files := make([]string, 0, len(fileTargets))
	for _, target := range fileTargets {
		absoluteTarget, err := filepath.Abs(target)
		if err != nil {
			return discovery.RepoFileSet{}, fmt.Errorf("resolve file target %q: %w", target, err)
		}
		if resolvedTarget, resolveErr := filepath.EvalSymlinks(absoluteTarget); resolveErr == nil {
			absoluteTarget = resolvedTarget
		}
		relativePath, err := filepath.Rel(repoPath, absoluteTarget)
		if err != nil {
			return discovery.RepoFileSet{}, fmt.Errorf("relativize file target %q: %w", absoluteTarget, err)
		}
		if relativePath == "." || strings.HasPrefix(relativePath, "..") {
			return discovery.RepoFileSet{}, fmt.Errorf(
				"file target %q is outside repository root %q",
				absoluteTarget,
				repoPath,
			)
		}
		if _, ok := registry.LookupByPath(absoluteTarget); !ok {
			continue
		}
		files = append(files, absoluteTarget)
	}
	return discovery.RepoFileSet{
		RepoRoot: repoPath,
		Files:    files,
	}, nil
}

func entityBucketsFromParsed(payload map[string]any) map[string][]shape.Entity {
	buckets := make(map[string][]shape.Entity)
	for _, mapping := range snapshotEntityBuckets {
		items, _ := payload[mapping.bucket].([]map[string]any)
		if len(items) == 0 {
			continue
		}

		entities := make([]shape.Entity, 0, len(items))
		for _, item := range items {
			entities = append(entities, shape.Entity{
				Name:            snapshotPayloadString(item, "name"),
				LineNumber:      snapshotPayloadInt(item, "line_number"),
				EndLine:         snapshotPayloadInt(item, "end_line"),
				StartByte:       snapshotPayloadIntPtr(item, "start_byte"),
				EndByte:         snapshotPayloadIntPtr(item, "end_byte"),
				Language:        snapshotPayloadString(item, "lang", "language"),
				ArtifactType:    snapshotPayloadString(item, "artifact_type"),
				TemplateDialect: snapshotPayloadString(item, "template_dialect"),
				IACRelevant:     snapshotPayloadBoolPtr(item, "iac_relevant"),
				Source:          snapshotPayloadString(item, "source"),
			})
		}
		buckets[mapping.bucket] = entities
	}
	return buckets
}

func annotateParsedFilesWithEntityIDs(
	repoPath string,
	parsedFiles []map[string]any,
	entities []content.EntityRecord,
) {
	lookup := make(map[string]string, len(entities))
	for _, entity := range entities {
		key := entityLookupKey(entity.Path, entity.EntityType, entity.EntityName, entity.StartLine)
		lookup[key] = entity.EntityID
	}

	for _, parsedFile := range parsedFiles {
		absolutePath := snapshotPayloadString(parsedFile, "path")
		relativePath, err := filepath.Rel(repoPath, absolutePath)
		if err != nil {
			continue
		}
		relativePath = filepath.ToSlash(filepath.Clean(relativePath))

		for _, mapping := range snapshotEntityBuckets {
			items, _ := parsedFile[mapping.bucket].([]map[string]any)
			for i := range items {
				name := snapshotPayloadString(items[i], "name")
				lineNumber := snapshotPayloadInt(items[i], "line_number")
				key := entityLookupKey(relativePath, mapping.label, name, lineNumber)
				if entityID, ok := lookup[key]; ok {
					items[i]["uid"] = entityID
				}
			}
			parsedFile[mapping.bucket] = items
		}
	}
}

func materializationRecordsToSnapshots(records []content.Record) []ContentFileSnapshot {
	snapshots := make([]ContentFileSnapshot, 0, len(records))
	for _, record := range records {
		snapshots = append(snapshots, ContentFileSnapshot{
			RelativePath:    record.Path,
			Body:            record.Body,
			Digest:          record.Digest,
			Language:        record.Metadata["language"],
			ArtifactType:    record.Metadata["artifact_type"],
			TemplateDialect: record.Metadata["template_dialect"],
			IACRelevant:     snapshotMetadataBoolPtr(record.Metadata, "iac_relevant"),
			CommitSHA:       record.Metadata["commit_sha"],
		})
	}
	return snapshots
}

func materializationEntitiesToSnapshots(
	entities []content.EntityRecord,
	indexedAt time.Time,
) []ContentEntitySnapshot {
	snapshots := make([]ContentEntitySnapshot, 0, len(entities))
	for _, entity := range entities {
		snapshots = append(snapshots, ContentEntitySnapshot{
			EntityID:        entity.EntityID,
			RelativePath:    entity.Path,
			EntityType:      entity.EntityType,
			EntityName:      entity.EntityName,
			StartLine:       entity.StartLine,
			EndLine:         entity.EndLine,
			StartByte:       entity.StartByte,
			EndByte:         entity.EndByte,
			Language:        entity.Language,
			ArtifactType:    entity.ArtifactType,
			TemplateDialect: entity.TemplateDialect,
			IACRelevant:     entity.IACRelevant,
			SourceCache:     entity.SourceCache,
			IndexedAt:       indexedAt,
		})
	}
	return snapshots
}

func gitCommitSHA(ctx context.Context, repoPath string) string {
	command := exec.CommandContext(ctx, "git", "-C", repoPath, "rev-parse", "HEAD")
	output, err := command.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(output))
}

func digestForBody(body string) string {
	sum := sha1.Sum([]byte(body))
	return hex.EncodeToString(sum[:])
}

func entityLookupKey(path, entityType, entityName string, lineNumber int) string {
	return strings.Join(
		[]string{
			filepath.ToSlash(strings.TrimSpace(path)),
			strings.TrimSpace(entityType),
			strings.TrimSpace(entityName),
			strconv.Itoa(lineNumber),
		},
		"|",
	)
}

func snapshotPayloadString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		value, ok := payload[key]
		if !ok {
			continue
		}
		text, ok := value.(string)
		if ok {
			return strings.TrimSpace(text)
		}
	}
	return ""
}

func snapshotPayloadInt(payload map[string]any, key string) int {
	value, ok := payload[key]
	if !ok {
		return 0
	}
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func snapshotPayloadIntPtr(payload map[string]any, key string) *int {
	value, ok := payload[key]
	if !ok || value == nil {
		return nil
	}
	parsed := snapshotPayloadInt(payload, key)
	return &parsed
}

func snapshotPayloadBoolPtr(payload map[string]any, key string) *bool {
	value, ok := payload[key]
	if !ok || value == nil {
		return nil
	}
	switch typed := value.(type) {
	case bool:
		return &typed
	case string:
		normalized := strings.TrimSpace(strings.ToLower(typed))
		if normalized == "true" {
			value := true
			return &value
		}
		if normalized == "false" {
			value := false
			return &value
		}
	}
	return nil
}

func snapshotMetadataBoolPtr(metadata map[string]string, key string) *bool {
	if metadata == nil {
		return nil
	}
	value, ok := metadata[key]
	if !ok {
		return nil
	}
	normalized := strings.TrimSpace(strings.ToLower(value))
	if normalized == "true" {
		parsed := true
		return &parsed
	}
	if normalized == "false" {
		parsed := false
		return &parsed
	}
	return nil
}
