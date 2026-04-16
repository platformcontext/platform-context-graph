package relationships

func discoverDockerComposeEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact
	for _, document := range parseYAMLDocuments(content) {
		for _, candidate := range dockerComposeBuildContexts(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindDockerComposeBuildContext, RelDeploysFrom, 0.91,
				"Docker Compose build context deploys from the target repository",
				"docker_compose", catalog, seen, map[string]any{
					"build_context": candidate,
				},
			)...)
		}
		for _, candidate := range dockerComposeImageRefs(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindDockerComposeImage, RelDeploysFrom, 0.88,
				"Docker Compose image reference deploys from artifacts owned by the target repository",
				"docker_compose", catalog, seen, map[string]any{
					"image_ref": candidate,
				},
			)...)
		}
	}
	return evidence
}

func dockerComposeBuildContexts(document map[string]any) []string {
	services, ok := nestedMap(document, "services")
	if !ok {
		return nil
	}

	contexts := make([]string, 0, len(services))
	for _, rawService := range services {
		service, ok := rawService.(map[string]any)
		if !ok {
			continue
		}
		buildMap, _ := nestedMap(service, "build")
		if buildMap == nil {
			continue
		}
		if context := stringValue(buildMap["context"]); context != "" {
			contexts = append(contexts, context)
		}
	}

	return uniqueStrings(contexts)
}

func dockerComposeImageRefs(document map[string]any) []string {
	services, ok := nestedMap(document, "services")
	if !ok {
		return nil
	}

	images := make([]string, 0, len(services))
	for _, rawService := range services {
		service, ok := rawService.(map[string]any)
		if !ok {
			continue
		}
		if image := stringValue(service["image"]); image != "" {
			images = append(images, image)
		}
	}

	return uniqueStrings(images)
}
