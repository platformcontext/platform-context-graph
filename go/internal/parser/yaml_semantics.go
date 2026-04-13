package parser

import (
	"fmt"
	"sort"
	"strings"
)

func isKustomization(apiVersion string, kind string, filename string) bool {
	if strings.HasPrefix(apiVersion, "kustomize.config.k8s.io/") {
		return true
	}
	if kind == "Kustomization" && strings.HasPrefix(apiVersion, "kustomize") {
		return true
	}
	lower := strings.ToLower(filename)
	return lower == "kustomization.yaml" || lower == "kustomization.yml"
}

func parseKustomization(document map[string]any, path string, lineNumber int) map[string]any {
	return map[string]any{
		"name":        "kustomization",
		"line_number": lineNumber,
		"namespace":   strings.TrimSpace(fmt.Sprint(document["namespace"])),
		"resources":   document["resources"],
		"patches":     collectPatchPaths(document["patches"]),
		"path":        path,
		"lang":        "yaml",
	}
}

func collectPatchPaths(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	paths := make([]string, 0, len(items))
	for _, item := range items {
		object, ok := item.(map[string]any)
		if !ok {
			continue
		}
		pathValue := strings.TrimSpace(fmt.Sprint(object["path"]))
		if pathValue != "" && pathValue != "<nil>" {
			paths = append(paths, pathValue)
		}
	}
	sort.Strings(paths)
	return paths
}

func isArgoCDApplication(apiVersion string, kind string) bool {
	return strings.HasPrefix(apiVersion, "argoproj.io/") && kind == "Application"
}

func parseArgoCDApplication(document map[string]any, metadata map[string]any, path string, lineNumber int) map[string]any {
	spec, _ := document["spec"].(map[string]any)
	source, _ := spec["source"].(map[string]any)
	destination, _ := spec["destination"].(map[string]any)
	return map[string]any{
		"name":            strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number":     lineNumber,
		"namespace":       strings.TrimSpace(fmt.Sprint(metadata["namespace"])),
		"project":         strings.TrimSpace(fmt.Sprint(spec["project"])),
		"source_repo":     strings.TrimSpace(fmt.Sprint(source["repoURL"])),
		"source_path":     strings.TrimSpace(fmt.Sprint(source["path"])),
		"source_revision": strings.TrimSpace(fmt.Sprint(source["targetRevision"])),
		"dest_server":     strings.TrimSpace(fmt.Sprint(destination["server"])),
		"dest_namespace":  strings.TrimSpace(fmt.Sprint(destination["namespace"])),
		"path":            path,
		"lang":            "yaml",
	}
}

func isArgoCDApplicationSet(apiVersion string, kind string) bool {
	return strings.HasPrefix(apiVersion, "argoproj.io/") && kind == "ApplicationSet"
}

func parseArgoCDApplicationSet(document map[string]any, metadata map[string]any, path string, lineNumber int) map[string]any {
	spec, _ := document["spec"].(map[string]any)
	template, _ := spec["template"].(map[string]any)
	templateSpec, _ := template["spec"].(map[string]any)
	return map[string]any{
		"name":           strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number":    lineNumber,
		"namespace":      strings.TrimSpace(fmt.Sprint(metadata["namespace"])),
		"project":        strings.TrimSpace(fmt.Sprint(templateSpec["project"])),
		"dest_namespace": strings.TrimSpace(fmt.Sprint(nestedMapValue(templateSpec, "destination", "namespace"))),
		"path":           path,
		"lang":           "yaml",
	}
}

func isCrossplaneXRD(apiVersion string, kind string) bool {
	return strings.HasPrefix(apiVersion, "apiextensions.crossplane.io/") && kind == "CompositeResourceDefinition"
}

func parseCrossplaneXRD(document map[string]any, metadata map[string]any, path string, lineNumber int) map[string]any {
	spec, _ := document["spec"].(map[string]any)
	names, _ := spec["names"].(map[string]any)
	claimNames, _ := spec["claimNames"].(map[string]any)
	return map[string]any{
		"name":         strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number":  lineNumber,
		"group":        strings.TrimSpace(fmt.Sprint(spec["group"])),
		"kind":         strings.TrimSpace(fmt.Sprint(names["kind"])),
		"plural":       strings.TrimSpace(fmt.Sprint(names["plural"])),
		"claim_kind":   strings.TrimSpace(fmt.Sprint(claimNames["kind"])),
		"claim_plural": strings.TrimSpace(fmt.Sprint(claimNames["plural"])),
		"path":         path,
		"lang":         "yaml",
	}
}

func isCrossplaneComposition(apiVersion string, kind string) bool {
	return strings.HasPrefix(apiVersion, "apiextensions.crossplane.io/") && kind == "Composition"
}

func parseCrossplaneComposition(document map[string]any, metadata map[string]any, path string, lineNumber int) map[string]any {
	spec, _ := document["spec"].(map[string]any)
	compositeRef, _ := spec["compositeTypeRef"].(map[string]any)
	resourceNames := make([]string, 0)
	if resources, ok := spec["resources"].([]any); ok {
		for _, item := range resources {
			resource, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name := strings.TrimSpace(fmt.Sprint(resource["name"]))
			if name != "" && name != "<nil>" {
				resourceNames = append(resourceNames, name)
			}
		}
	}
	sort.Strings(resourceNames)
	return map[string]any{
		"name":                  strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number":           lineNumber,
		"composite_api_version": strings.TrimSpace(fmt.Sprint(compositeRef["apiVersion"])),
		"composite_kind":        strings.TrimSpace(fmt.Sprint(compositeRef["kind"])),
		"resource_count":        len(resourceNames),
		"resource_names":        strings.Join(resourceNames, ","),
		"path":                  path,
		"lang":                  "yaml",
	}
}

func isCrossplaneClaim(apiVersion string) bool {
	if strings.HasPrefix(apiVersion, "apiextensions.crossplane.io/") {
		return false
	}
	if strings.HasPrefix(apiVersion, "pkg.crossplane.io/") {
		return false
	}
	return strings.Contains(apiVersion, ".crossplane.io/")
}

func parseCrossplaneClaim(metadata map[string]any, apiVersion string, kind string, path string, lineNumber int) map[string]any {
	return map[string]any{
		"name":        strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number": lineNumber,
		"kind":        kind,
		"api_version": apiVersion,
		"namespace":   strings.TrimSpace(fmt.Sprint(metadata["namespace"])),
		"path":        path,
		"lang":        "yaml",
	}
}

func parseK8sResource(document map[string]any, metadata map[string]any, apiVersion string, kind string, path string, lineNumber int) map[string]any {
	row := map[string]any{
		"name":        strings.TrimSpace(fmt.Sprint(metadata["name"])),
		"line_number": lineNumber,
		"kind":        kind,
		"api_version": apiVersion,
		"namespace":   strings.TrimSpace(fmt.Sprint(metadata["namespace"])),
		"path":        path,
		"lang":        "yaml",
	}
	if images := collectContainerImages(document); len(images) > 0 {
		row["container_images"] = strings.Join(images, ",")
	}
	if backends := collectHTTPRouteBackends(document); len(backends) > 0 {
		row["backend_refs"] = strings.Join(backends, ",")
	}
	return row
}

func collectContainerImages(document map[string]any) []string {
	spec, _ := document["spec"].(map[string]any)
	template := nestedMap(spec, "template")
	if len(template) == 0 {
		template = nestedMap(spec, "jobTemplate", "spec", "template")
	}
	podSpec := nestedMap(template, "spec")
	images := make([]string, 0)
	for _, key := range []string{"containers", "initContainers"} {
		if items, ok := podSpec[key].([]any); ok {
			for _, item := range items {
				container, ok := item.(map[string]any)
				if !ok {
					continue
				}
				image := strings.TrimSpace(fmt.Sprint(container["image"]))
				if image != "" && image != "<nil>" {
					images = append(images, image)
				}
			}
		}
	}
	sort.Strings(images)
	return images
}

func collectHTTPRouteBackends(document map[string]any) []string {
	spec, _ := document["spec"].(map[string]any)
	rules, _ := spec["rules"].([]any)
	backends := make([]string, 0)
	for _, item := range rules {
		rule, ok := item.(map[string]any)
		if !ok {
			continue
		}
		refs, _ := rule["backendRefs"].([]any)
		for _, ref := range refs {
			backend, ok := ref.(map[string]any)
			if !ok {
				continue
			}
			name := strings.TrimSpace(fmt.Sprint(backend["name"]))
			if name != "" && name != "<nil>" {
				backends = append(backends, name)
			}
		}
	}
	sort.Strings(backends)
	return backends
}

func nestedMap(values map[string]any, keys ...string) map[string]any {
	current := values
	for _, key := range keys {
		next, ok := current[key].(map[string]any)
		if !ok {
			return nil
		}
		current = next
	}
	return current
}

func nestedMapValue(values map[string]any, keys ...string) any {
	if len(keys) == 0 {
		return nil
	}
	current := values
	for _, key := range keys[:len(keys)-1] {
		next, ok := current[key].(map[string]any)
		if !ok {
			return nil
		}
		current = next
	}
	return current[keys[len(keys)-1]]
}
