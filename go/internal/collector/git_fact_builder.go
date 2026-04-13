package collector

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/repositoryidentity"
)

func buildCollectedGeneration(
	repoPath string,
	repo repositoryidentity.Metadata,
	sourceRunID string,
	observedAt time.Time,
	snapshot RepositorySnapshot,
) CollectedGeneration {
	scopeValue := buildScope(repo)
	generation := buildGeneration(
		scopeValue.ScopeID,
		sourceRunID,
		repoPath,
		observedAt,
		snapshotFreshnessHint(snapshot),
	)
	factEnvelopes := make([]facts.Envelope, 0, 1+len(snapshot.FileData)+len(snapshot.ContentFiles)+len(snapshot.ContentEntities)+1)
	factEnvelopes = append(
		factEnvelopes,
		repositoryFactEnvelope(repoPath, repo, scopeValue.ScopeID, generation.GenerationID, observedAt, snapshot.FileCount),
	)
	for _, fileData := range snapshot.FileData {
		factEnvelopes = append(
			factEnvelopes,
			fileFactEnvelope(repoPath, repo.ID, scopeValue.ScopeID, generation.GenerationID, observedAt, fileData),
		)
	}
	for _, fileSnapshot := range snapshot.ContentFiles {
		factEnvelopes = append(
			factEnvelopes,
			contentFactEnvelope(repoPath, repo.ID, scopeValue.ScopeID, generation.GenerationID, observedAt, fileSnapshot),
		)
	}
	for _, entitySnapshot := range snapshot.ContentEntities {
		factEnvelopes = append(
			factEnvelopes,
			contentEntityFactEnvelope(repoPath, repo.ID, scopeValue.ScopeID, generation.GenerationID, observedAt, entitySnapshot),
		)
	}
	factEnvelopes = append(
		factEnvelopes,
		workloadIdentityFactEnvelope(repoPath, repo.ID, scopeValue.ScopeID, generation.GenerationID, observedAt),
	)

	return CollectedGeneration{
		Scope:      scopeValue,
		Generation: generation,
		Facts:      factEnvelopes,
	}
}

func snapshotFreshnessHint(snapshot RepositorySnapshot) string {
	canonicalSnapshot := map[string]any{
		"file_count":       snapshot.FileCount,
		"file_data":        normalizeFingerprintValue(snapshot.FileData),
		"content_files":    normalizeFingerprintValue(snapshot.ContentFiles),
		"content_entities": normalizeFingerprintValue(snapshot.ContentEntities),
	}

	fingerprintInput, err := json.Marshal(canonicalSnapshot)
	if err != nil {
		return fmt.Sprintf("snapshot:marshal-error:%x", sha256.Sum256([]byte(err.Error())))
	}

	sum := sha256.Sum256(fingerprintInput)
	return fmt.Sprintf("snapshot:%x", sum[:])
}

func normalizeFingerprintValue(value any) any {
	if value == nil {
		return nil
	}

	switch typed := value.(type) {
	case string, bool, int, int8, int16, int32, int64:
		return typed
	case uint, uint8, uint16, uint32, uint64:
		return typed
	case float32, float64:
		return typed
	case json.Number:
		return typed.String()
	case time.Time:
		return typed.UTC().Format(time.RFC3339Nano)
	case map[string]any:
		return normalizeStringMap(typed)
	case map[string]string:
		cloned := make(map[string]any, len(typed))
		for key, value := range typed {
			cloned[key] = normalizeFingerprintValue(value)
		}
		return normalizeStringMap(cloned)
	}

	if stringer, ok := value.(fmt.Stringer); ok {
		return stringer.String()
	}

	reflectValue := reflect.ValueOf(value)
	switch reflectValue.Kind() {
	case reflect.Slice, reflect.Array:
		if reflectValue.Kind() == reflect.Slice && reflectValue.IsNil() {
			return []any{}
		}

		items := make([]any, 0, reflectValue.Len())
		for i := 0; i < reflectValue.Len(); i++ {
			items = append(items, normalizeFingerprintValue(reflectValue.Index(i).Interface()))
		}
		sort.Slice(items, func(i, j int) bool {
			return canonicalFingerprintJSON(items[i]) < canonicalFingerprintJSON(items[j])
		})
		return items
	case reflect.Map:
		if reflectValue.Type().Key().Kind() != reflect.String {
			return fmt.Sprint(value)
		}

		cloned := make(map[string]any, reflectValue.Len())
		for _, key := range reflectValue.MapKeys() {
			cloned[key.String()] = normalizeFingerprintValue(reflectValue.MapIndex(key).Interface())
		}
		return normalizeStringMap(cloned)
	default:
		return fmt.Sprint(value)
	}
}

func normalizeStringMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}

	keys := make([]string, 0, len(input))
	for key := range input {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	cloned := make(map[string]any, len(input))
	for _, key := range keys {
		cloned[key] = normalizeFingerprintValue(input[key])
	}
	return cloned
}

func canonicalFingerprintJSON(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprintf("marshal-error:%v", err)
	}
	return string(payload)
}

func repositoryFactEnvelope(
	repoPath string,
	repo repositoryidentity.Metadata,
	scopeID string,
	generationID string,
	observedAt time.Time,
	parsedFileCount int,
) facts.Envelope {
	payload := map[string]any{
		"graph_id":          repo.ID,
		"graph_kind":        "repository",
		"name":              repo.Name,
		"repo_id":           repo.ID,
		"parsed_file_count": fmt.Sprintf("%d", parsedFileCount),
	}
	if repo.RepoSlug != "" {
		payload["repo_slug"] = repo.RepoSlug
	}
	if repo.RemoteURL != "" {
		payload["remote_url"] = repo.RemoteURL
	}
	if repo.LocalPath != "" {
		payload["local_path"] = repo.LocalPath
	}

	return factEnvelope("repository", scopeID, generationID, observedAt, "repository:"+repo.ID, payload, repoPath)
}

func fileFactEnvelope(
	repoPath string,
	repoID string,
	scopeID string,
	generationID string,
	observedAt time.Time,
	fileData map[string]any,
) facts.Envelope {
	filePath := payloadPath(fileData, "path")
	relativePath := repositoryRelativePath(repoPath, filePath)
	payload := map[string]any{
		"graph_id":         repoID + ":" + relativePath,
		"graph_kind":       "file",
		"repo_id":          repoID,
		"relative_path":    relativePath,
		"parsed_file_data": fileData,
	}
	if language := payloadString(fileData, "language", "lang"); language != "" {
		payload["language"] = language
	}

	return factEnvelope("file", scopeID, generationID, observedAt, "file:"+repoID+":"+relativePath, payload, filePath)
}

func contentFactEnvelope(
	repoPath string,
	repoID string,
	scopeID string,
	generationID string,
	observedAt time.Time,
	fileSnapshot ContentFileSnapshot,
) facts.Envelope {
	payload := map[string]any{
		"content_path":   fileSnapshot.RelativePath,
		"content_body":   fileSnapshot.Body,
		"content_digest": fileSnapshot.Digest,
		"repo_id":        repoID,
	}
	if fileSnapshot.Language != "" {
		payload["language"] = fileSnapshot.Language
	}
	if fileSnapshot.CommitSHA != "" {
		payload["commit_sha"] = fileSnapshot.CommitSHA
	}
	if fileSnapshot.ArtifactType != "" {
		payload["artifact_type"] = fileSnapshot.ArtifactType
	}
	if fileSnapshot.TemplateDialect != "" {
		payload["template_dialect"] = fileSnapshot.TemplateDialect
	}
	if fileSnapshot.IACRelevant != nil {
		payload["iac_relevant"] = strings.ToLower(fmt.Sprintf("%t", *fileSnapshot.IACRelevant))
	}

	return factEnvelope(
		"content",
		scopeID,
		generationID,
		observedAt,
		"content:"+repoID+":"+fileSnapshot.RelativePath,
		payload,
		filepath.Join(repoPath, filepath.FromSlash(fileSnapshot.RelativePath)),
	)
}

func contentEntityFactEnvelope(
	repoPath string,
	repoID string,
	scopeID string,
	generationID string,
	observedAt time.Time,
	entitySnapshot ContentEntitySnapshot,
) facts.Envelope {
	payload := map[string]any{
		"graph_id":      entitySnapshot.EntityID,
		"graph_kind":    "content_entity",
		"entity_id":     entitySnapshot.EntityID,
		"repo_id":       repoID,
		"relative_path": entitySnapshot.RelativePath,
		"entity_type":   entitySnapshot.EntityType,
		"entity_name":   entitySnapshot.EntityName,
		"start_line":    entitySnapshot.StartLine,
		"end_line":      entitySnapshot.EndLine,
		"language":      entitySnapshot.Language,
		"source_cache":  entitySnapshot.SourceCache,
		"indexed_at":    entitySnapshot.IndexedAt.UTC().Format(time.RFC3339Nano),
	}
	if entitySnapshot.StartByte != nil {
		payload["start_byte"] = *entitySnapshot.StartByte
	}
	if entitySnapshot.EndByte != nil {
		payload["end_byte"] = *entitySnapshot.EndByte
	}
	if entitySnapshot.ArtifactType != "" {
		payload["artifact_type"] = entitySnapshot.ArtifactType
	}
	if entitySnapshot.TemplateDialect != "" {
		payload["template_dialect"] = entitySnapshot.TemplateDialect
	}
	if entitySnapshot.IACRelevant != nil {
		payload["iac_relevant"] = *entitySnapshot.IACRelevant
	}

	return factEnvelope(
		"content_entity",
		scopeID,
		generationID,
		observedAt,
		"content_entity:"+entitySnapshot.EntityID,
		payload,
		filepath.Join(repoPath, filepath.FromSlash(entitySnapshot.RelativePath)),
	)
}

func workloadIdentityFactEnvelope(
	repoPath string,
	repoID string,
	scopeID string,
	generationID string,
	observedAt time.Time,
) facts.Envelope {
	payload := map[string]any{
		"reducer_domain": "workload_identity",
		"entity_key":     "workload:" + filepath.Base(repoPath),
		"reason":         "repository snapshot emitted shared workload identity follow-up",
		"repo_id":        repoID,
	}

	return factEnvelope(
		"shared_followup",
		scopeID,
		generationID,
		observedAt,
		"shared_followup:"+repoID+":workload_identity",
		payload,
		repoPath,
	)
}

func factEnvelope(
	factKind string,
	scopeID string,
	generationID string,
	observedAt time.Time,
	factKey string,
	payload map[string]any,
	sourceURI string,
) facts.Envelope {
	return facts.Envelope{
		FactID: facts.StableID(
			"GoGitCollectorFact",
			map[string]any{
				"fact_key":      factKey,
				"fact_kind":     factKind,
				"generation_id": generationID,
				"scope_id":      scopeID,
			},
		),
		ScopeID:       scopeID,
		GenerationID:  generationID,
		FactKind:      factKind,
		StableFactKey: factKey,
		ObservedAt:    observedAt,
		Payload:       payload,
		SourceRef: facts.Ref{
			SourceSystem:   "git",
			ScopeID:        scopeID,
			GenerationID:   generationID,
			FactKey:        factKey,
			SourceURI:      sourceURI,
			SourceRecordID: factKey,
		},
	}
}

func repositoryRelativePath(repoPath string, filePath string) string {
	relativePath, err := filepath.Rel(repoPath, filePath)
	if err != nil {
		return filepath.Base(filePath)
	}
	return filepath.ToSlash(relativePath)
}

func payloadString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		value, ok := payload[key]
		if !ok {
			continue
		}
		text, ok := value.(string)
		if !ok {
			continue
		}
		if strings.TrimSpace(text) == "" {
			continue
		}
		return text
	}
	return ""
}

func payloadPath(payload map[string]any, key string) string {
	value := payloadString(payload, key)
	if value == "" {
		return ""
	}
	resolved, err := filepath.Abs(value)
	if err != nil {
		return value
	}
	return resolved
}
