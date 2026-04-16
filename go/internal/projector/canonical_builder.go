package projector

import (
	"path"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

// buildCanonicalMaterialization extracts canonical graph materialization data
// from a set of fact envelopes. The returned CanonicalMaterialization carries
// all node and edge writes needed to project one repository generation into
// the canonical Neo4j graph.
func buildCanonicalMaterialization(
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
	inputFacts []facts.Envelope,
) CanonicalMaterialization {
	mat := CanonicalMaterialization{
		ScopeID:      scopeValue.ScopeID,
		GenerationID: generation.GenerationID,
		RepoID:       scopeValue.Metadata["repo_id"],
		RepoPath:     scopeValue.Metadata["repo_path"],
	}

	if len(inputFacts) == 0 {
		return mat
	}

	// Extract repository.
	mat.Repository = extractRepository(inputFacts)
	if mat.Repository != nil {
		if mat.Repository.RepoID != "" {
			mat.RepoID = mat.Repository.RepoID
		}
		if mat.Repository.Path != "" {
			mat.RepoPath = mat.Repository.Path
		}
	}

	repoID := mat.RepoID
	repoPath := mat.RepoPath

	// Extract files.
	mat.Files = extractFiles(inputFacts, repoID)

	// Build directory chain from file paths.
	mat.Directories = buildDirectoryChain(mat.Files, repoPath, repoID)

	// Extract entities.
	mat.Entities = extractEntities(inputFacts, repoID)

	// Extract modules, imports, parameters, class members, nested functions
	// from all non-tombstoned facts.
	extractRelationships(inputFacts, &mat)

	return mat
}

// extractRepository builds a RepositoryRow from the first RepositoryObserved
// fact envelope.
func extractRepository(envelopes []facts.Envelope) *RepositoryRow {
	repoFacts := FilterRepositoryFacts(envelopes)
	if len(repoFacts) == 0 {
		return nil
	}

	p := repoFacts[0].Payload
	repoID, _ := payloadString(p, "repo_id")
	name, _ := payloadString(p, "name")
	repoPath, _ := payloadString(p, "path")
	localPath, _ := payloadString(p, "local_path")
	remoteURL, _ := payloadString(p, "remote_url")
	repoSlug, _ := payloadString(p, "repo_slug")

	hasRemote := false
	if ptr := payloadBoolPtr(p, "has_remote"); ptr != nil {
		hasRemote = *ptr
	}

	return &RepositoryRow{
		RepoID:    repoID,
		Name:      name,
		Path:      repoPath,
		LocalPath: localPath,
		RemoteURL: remoteURL,
		RepoSlug:  repoSlug,
		HasRemote: hasRemote,
	}
}

// extractFiles builds FileRow entries from file fact envelopes, skipping
// tombstones. The canonical path (used as the Neo4j MERGE key) is the
// relative_path so it matches entity file_path references in the graph.
func extractFiles(envelopes []facts.Envelope, repoID string) []FileRow {
	fileFacts := FilterFileFacts(envelopes)
	var rows []FileRow

	for i := range fileFacts {
		if fileFacts[i].IsTombstone {
			continue
		}

		p := fileFacts[i].Payload
		relativePath, _ := payloadString(p, "relative_path")
		if relativePath == "" {
			continue
		}

		name := path.Base(relativePath)
		language, _ := payloadString(p, "language")
		dirPath := path.Dir(relativePath)

		rows = append(rows, FileRow{
			Path:         relativePath,
			RelativePath: relativePath,
			Name:         name,
			Language:     language,
			RepoID:       repoID,
			DirPath:      dirPath,
		})
	}

	return rows
}

// buildDirectoryChain walks file paths to produce a deduped, depth-sorted
// list of DirectoryRow entries. Directories are computed relative to the
// repository root path.
func buildDirectoryChain(files []FileRow, repoPath string, repoID string) []DirectoryRow {
	if len(files) == 0 {
		return nil
	}

	seen := make(map[string]struct{})
	var dirs []DirectoryRow

	for _, f := range files {
		dirPath := f.DirPath
		// Walk from the file's parent directory up to (but not including)
		// the repository root.
		for dirPath != "" && dirPath != repoPath && dirPath != "." && dirPath != "/" {
			if _, ok := seen[dirPath]; ok {
				break // already recorded this dir and all its ancestors
			}
			seen[dirPath] = struct{}{}

			parentPath := path.Dir(dirPath)
			dirName := path.Base(dirPath)

			// Compute depth: number of path segments between repoPath and
			// dirPath (0-indexed from the first level under repo).
			rel := strings.TrimPrefix(dirPath, repoPath+"/")
			depth := strings.Count(rel, "/")

			dirs = append(dirs, DirectoryRow{
				Path:       dirPath,
				Name:       dirName,
				ParentPath: parentPath,
				RepoID:     repoID,
				Depth:      depth,
			})

			dirPath = parentPath
		}
	}

	sort.Slice(dirs, func(i, j int) bool {
		if dirs[i].Depth != dirs[j].Depth {
			return dirs[i].Depth < dirs[j].Depth
		}
		return dirs[i].Path < dirs[j].Path
	})

	return dirs
}

// extractEntities builds EntityRow entries from ParsedEntityObserved fact
// envelopes. Entities with unmapped types or tombstoned facts are skipped.
func extractEntities(envelopes []facts.Envelope, repoID string) []EntityRow {
	entityFacts := FilterEntityFacts(envelopes)
	var rows []EntityRow

	for i := range entityFacts {
		if entityFacts[i].IsTombstone {
			continue
		}

		p := entityFacts[i].Payload

		entityType, _ := payloadString(p, "entity_type")
		if entityType == "" {
			continue
		}

		label, ok := EntityTypeLabel(entityType)
		if !ok {
			continue
		}

		entityName, _ := payloadString(p, "entity_name")
		relativePath, _ := payloadString(p, "relative_path")
		startLine, _ := payloadInt(p, "start_line")
		endLine, _ := payloadInt(p, "end_line")
		language, _ := payloadString(p, "language")

		entityRepoID, ok := payloadString(p, "repo_id")
		if !ok {
			entityRepoID = repoID
		}

		entityID, _ := payloadString(p, "entity_id")
		if entityID == "" {
			entityID = content.CanonicalEntityID(entityRepoID, relativePath, entityType, entityName, startLine)
		}

		metadata := extractEntityMetadata(p)

		rows = append(rows, EntityRow{
			EntityID:     entityID,
			Label:        label,
			EntityName:   entityName,
			FilePath:     relativePath,
			RelativePath: relativePath,
			StartLine:    startLine,
			EndLine:      endLine,
			Language:     language,
			RepoID:       entityRepoID,
			Metadata:     metadata,
		})
	}

	return rows
}

// extractEntityMetadata pulls the entity_metadata sub-map from a fact
// payload and converts it to map[string]string.
func extractEntityMetadata(payload map[string]any) map[string]string {
	raw, ok := payload["entity_metadata"]
	if !ok {
		return nil
	}

	typed, ok := raw.(map[string]any)
	if !ok || len(typed) == 0 {
		return nil
	}

	result := make(map[string]string, len(typed))
	for key, value := range typed {
		if text, ok := value.(string); ok {
			trimmed := strings.TrimSpace(text)
			if trimmed != "" {
				result[key] = trimmed
			}
		}
	}

	if len(result) == 0 {
		return nil
	}
	return result
}

// extractRelationships scans all non-tombstoned facts for module, import,
// parameter, class member, and nested function payload patterns.
func extractRelationships(envelopes []facts.Envelope, mat *CanonicalMaterialization) {
	moduleSeen := make(map[string]struct{})

	for i := range envelopes {
		if envelopes[i].IsTombstone {
			continue
		}

		p := envelopes[i].Payload

		// Imports: facts with imported_module or module_name payload.
		moduleName, hasModule := payloadString(p, "module_name")
		importedModule, hasImported := payloadString(p, "imported_module")

		if hasModule || hasImported {
			modName := moduleName
			if modName == "" {
				modName = importedModule
			}

			// Track modules (deduped by name).
			if modName != "" {
				if _, ok := moduleSeen[modName]; !ok {
					moduleSeen[modName] = struct{}{}
					language, _ := payloadString(p, "language")
					mat.Modules = append(mat.Modules, ModuleRow{
						Name:     modName,
						Language: language,
					})
				}
			}

			// Import row.
			filePath, _ := payloadString(p, "relative_path")
			if filePath == "" {
				filePath = envelopes[i].SourceRef.SourceURI
			}
			importedName, _ := payloadString(p, "imported_name")
			alias, _ := payloadString(p, "alias")
			lineNumber, _ := payloadInt(p, "line_number")

			importModule := importedModule
			if importModule == "" {
				importModule = moduleName
			}

			mat.Imports = append(mat.Imports, ImportRow{
				FilePath:     filePath,
				ModuleName:   importModule,
				ImportedName: importedName,
				Alias:        alias,
				LineNumber:   lineNumber,
			})
		}

		// Parameters: facts with param_name payload key.
		paramName, hasParam := payloadString(p, "param_name")
		if hasParam {
			funcName, _ := payloadString(p, "function_name")
			filePath, _ := payloadString(p, "relative_path")
			funcLine, _ := payloadInt(p, "function_line")

			mat.Parameters = append(mat.Parameters, ParameterRow{
				ParamName:    paramName,
				FilePath:     filePath,
				FunctionName: funcName,
				FunctionLine: funcLine,
			})
		}

		// Class members: facts with class_name AND function_name.
		className, hasClass := payloadString(p, "class_name")
		funcName, hasFunc := payloadString(p, "function_name")
		if hasClass && hasFunc && !hasParam {
			filePath, _ := payloadString(p, "relative_path")
			funcLine, _ := payloadInt(p, "function_line")

			mat.ClassMembers = append(mat.ClassMembers, ClassMemberRow{
				ClassName:    className,
				FunctionName: funcName,
				FilePath:     filePath,
				FunctionLine: funcLine,
			})
		}

		// Nested functions: facts with outer_name AND inner_name.
		outerName, hasOuter := payloadString(p, "outer_name")
		innerName, hasInner := payloadString(p, "inner_name")
		if hasOuter && hasInner {
			filePath, _ := payloadString(p, "relative_path")
			innerLine, _ := payloadInt(p, "inner_line")

			mat.NestedFuncs = append(mat.NestedFuncs, NestedFunctionRow{
				OuterName: outerName,
				InnerName: innerName,
				FilePath:  filePath,
				InnerLine: innerLine,
			})
		}
	}
}
