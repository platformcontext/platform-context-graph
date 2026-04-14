package parser

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func isHelmChartFile(filename string) bool {
	lower := strings.ToLower(filename)
	return lower == "chart.yaml" || lower == "chart.yml"
}

func isHelmValuesFile(filename string) bool {
	lower := strings.ToLower(filename)
	return strings.HasPrefix(lower, "values") &&
		(strings.HasSuffix(lower, ".yaml") || strings.HasSuffix(lower, ".yml"))
}

func isHelmTemplateManifest(path string) bool {
	parts := strings.Split(filepath.ToSlash(path), "/")
	for index, part := range parts {
		if part != "templates" || index == 0 {
			continue
		}
		chartDir := filepath.Join(filepath.Dir(path), "..")
		if fileExists(filepath.Join(chartDir, "Chart.yaml")) ||
			fileExists(filepath.Join(chartDir, "Chart.yml")) {
			return true
		}
	}
	return false
}

func parseHelmChart(path string, source []byte) map[string]any {
	documents, err := decodeYAMLDocuments(string(source))
	if err != nil || len(documents) == 0 {
		return nil
	}
	document, ok := documents[0].(map[string]any)
	if !ok {
		return nil
	}
	dependencies := make([]string, 0)
	if items, ok := document["dependencies"].([]any); ok {
		for _, item := range items {
			dependency, ok := item.(map[string]any)
			if !ok {
				continue
			}
			name := strings.TrimSpace(fmt.Sprint(dependency["name"]))
			if name != "" && name != "<nil>" {
				dependencies = append(dependencies, name)
			}
		}
	}
	sort.Strings(dependencies)
	return map[string]any{
		"name":         strings.TrimSpace(fmt.Sprint(document["name"])),
		"line_number":  1,
		"version":      strings.TrimSpace(fmt.Sprint(document["version"])),
		"app_version":  strings.TrimSpace(fmt.Sprint(document["appVersion"])),
		"chart_type":   fallbackString(document["type"], "application"),
		"description":  strings.TrimSpace(fmt.Sprint(document["description"])),
		"dependencies": strings.Join(dependencies, ","),
		"path":         path,
		"lang":         "yaml",
	}
}

func parseHelmValues(path string, source []byte) map[string]any {
	documents, err := decodeYAMLDocuments(string(source))
	if err != nil || len(documents) == 0 {
		return nil
	}
	document, ok := documents[0].(map[string]any)
	if !ok {
		return nil
	}
	delete(document, "__pcg_line_number")
	return map[string]any{
		"name":           strings.TrimSuffix(filepath.Base(path), filepath.Ext(path)),
		"line_number":    1,
		"top_level_keys": strings.Join(sortedMapKeys(document), ","),
		"path":           path,
		"lang":           "yaml",
	}
}

func fallbackString(value any, fallback string) string {
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" || text == "<nil>" {
		return fallback
	}
	return text
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
