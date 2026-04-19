package query

import (
	"context"
	"fmt"
	"net/url"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

type serviceEvidenceReader interface {
	ListRepoFiles(ctx context.Context, repoID string, limit int) ([]FileContent, error)
	GetFileContent(ctx context.Context, repoID, relativePath string) (*FileContent, error)
}

type ServiceQueryEvidence struct {
	Hostnames    []ServiceHostnameEvidence    `json:"hostnames,omitempty"`
	Environments []ServiceEnvironmentEvidence `json:"environments,omitempty"`
	DocsRoutes   []ServiceDocsRouteEvidence   `json:"docs_routes,omitempty"`
	APISpecs     []ServiceAPISpecEvidence     `json:"api_specs,omitempty"`
}

type ServiceHostnameEvidence struct {
	Hostname     string `json:"hostname"`
	Environment  string `json:"environment,omitempty"`
	RelativePath string `json:"relative_path"`
	Reason       string `json:"reason"`
}

type ServiceEnvironmentEvidence struct {
	Environment  string `json:"environment"`
	RelativePath string `json:"relative_path"`
	Reason       string `json:"reason"`
}

type ServiceDocsRouteEvidence struct {
	Route        string `json:"route"`
	RelativePath string `json:"relative_path"`
	Reason       string `json:"reason"`
}

type ServiceAPISpecEvidence struct {
	RelativePath     string                       `json:"relative_path"`
	Format           string                       `json:"format"`
	Parsed           bool                         `json:"parsed"`
	SpecVersion      string                       `json:"spec_version,omitempty"`
	APIVersion       string                       `json:"api_version,omitempty"`
	EndpointCount    int                          `json:"endpoint_count,omitempty"`
	MethodCount      int                          `json:"method_count,omitempty"`
	OperationIDCount int                          `json:"operation_id_count,omitempty"`
	DocsRoutes       []string                     `json:"docs_routes,omitempty"`
	Hostnames        []string                     `json:"hostnames,omitempty"`
	Endpoints        []ServiceAPIEndpointEvidence `json:"endpoints,omitempty"`
}

type ServiceAPIEndpointEvidence struct {
	Path         string   `json:"path"`
	Methods      []string `json:"methods,omitempty"`
	OperationIDs []string `json:"operation_ids,omitempty"`
}

var (
	serviceHostnamePattern  = regexp.MustCompile(`(?i)\b(?:https?://)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62})\b`)
	serviceDocsRoutePattern = regexp.MustCompile(`(?i)['"](/[^'"]+)['"]`)
	serviceHostnameKeyPattern = regexp.MustCompile(`(?i)(?:^|[\s\[{,])["']?(?:host|hostname|url|origin|endpoint|ingress|server_name|base_url|baseurl|public_url|publicurl|service_url|serviceurl|api_url|apiurl)["']?\s*:`)
	serviceHostnameEnvKeyPattern = regexp.MustCompile(`(?i)\b(?:host|hostname|url|origin|endpoint|base_url|public_url|service_url|api_url|ingress)\b\s*=`)
)

const serviceEvidenceFileLimit = 5000

var environmentAliases = []struct {
	canonical string
	aliases   []string
}{
	{canonical: "prod", aliases: []string{"prod", "production"}},
	{canonical: "qa", aliases: []string{"qa"}},
	{canonical: "stage", aliases: []string{"stage", "staging"}},
	{canonical: "dev", aliases: []string{"dev", "development"}},
	{canonical: "test", aliases: []string{"test"}},
	{canonical: "sandbox", aliases: []string{"sandbox"}},
	{canonical: "preview", aliases: []string{"preview"}},
}

var openAPIMethodNames = map[string]struct{}{
	"get": {}, "put": {}, "post": {}, "delete": {}, "patch": {}, "options": {}, "head": {}, "trace": {},
}

func loadServiceQueryEvidence(
	ctx context.Context,
	reader serviceEvidenceReader,
	repoID string,
	serviceName string,
) (ServiceQueryEvidence, error) {
	if reader == nil || repoID == "" {
		return ServiceQueryEvidence{}, nil
	}

	files, err := reader.ListRepoFiles(ctx, repoID, serviceEvidenceFileLimit)
	if err != nil {
		return ServiceQueryEvidence{}, fmt.Errorf("list service evidence files: %w", err)
	}

	var evidence ServiceQueryEvidence
	seenHostnames := map[string]struct{}{}
	seenEnvironments := map[string]struct{}{}
	seenDocsRoutes := map[string]struct{}{}
	seenSpecs := map[string]struct{}{}
	normalizedServiceName := normalizeEvidenceToken(serviceName)

	for _, file := range files {
		if !isServiceEvidenceCandidate(file, normalizedServiceName) {
			continue
		}

		hydrated := file
		if strings.TrimSpace(hydrated.Content) == "" {
			fileContent, err := reader.GetFileContent(ctx, repoID, file.RelativePath)
			if err != nil {
				return ServiceQueryEvidence{}, fmt.Errorf("get service evidence file %q: %w", file.RelativePath, err)
			}
			if fileContent == nil {
				continue
			}
			hydrated = *fileContent
		}

		hostnames := extractObservedHostnames(hydrated.Content)
		environments := inferObservedEnvironments(hydrated.RelativePath, hydrated.Content, hostnames)
		for _, hostname := range hostnames {
			environment := inferHostnameEnvironment(hostname)
			if environment == "" && len(environments) > 0 {
				environment = environments[0]
			}
			if _, ok := seenHostnames[hostname]; ok {
				continue
			}
			seenHostnames[hostname] = struct{}{}
			evidence.Hostnames = append(evidence.Hostnames, ServiceHostnameEvidence{
				Hostname:     hostname,
				Environment:  environment,
				RelativePath: hydrated.RelativePath,
				Reason:       "content_hostname_reference",
			})
		}

		for _, environment := range environments {
			if _, ok := seenEnvironments[environment]; ok {
				continue
			}
			seenEnvironments[environment] = struct{}{}
			evidence.Environments = append(evidence.Environments, ServiceEnvironmentEvidence{
				Environment:  environment,
				RelativePath: hydrated.RelativePath,
				Reason:       "path_or_content_environment_signal",
			})
		}

		for _, route := range extractDocsRoutes(hydrated.Content) {
			if _, ok := seenDocsRoutes[route]; ok {
				continue
			}
			seenDocsRoutes[route] = struct{}{}
			evidence.DocsRoutes = append(evidence.DocsRoutes, ServiceDocsRouteEvidence{
				Route:        route,
				RelativePath: hydrated.RelativePath,
				Reason:       "docs_route_reference",
			})
		}

		if spec, ok := extractAPISpecEvidence(hydrated); ok {
			key := spec.RelativePath
			if _, ok := seenSpecs[key]; ok {
				continue
			}
			seenSpecs[key] = struct{}{}
			evidence.APISpecs = append(evidence.APISpecs, spec)
		}
	}

	sort.Slice(evidence.Hostnames, func(i, j int) bool {
		if evidence.Hostnames[i].Hostname != evidence.Hostnames[j].Hostname {
			return evidence.Hostnames[i].Hostname < evidence.Hostnames[j].Hostname
		}
		return evidence.Hostnames[i].RelativePath < evidence.Hostnames[j].RelativePath
	})
	sort.Slice(evidence.Environments, func(i, j int) bool {
		if evidence.Environments[i].Environment != evidence.Environments[j].Environment {
			return evidence.Environments[i].Environment < evidence.Environments[j].Environment
		}
		return evidence.Environments[i].RelativePath < evidence.Environments[j].RelativePath
	})
	sort.Slice(evidence.DocsRoutes, func(i, j int) bool {
		if evidence.DocsRoutes[i].Route != evidence.DocsRoutes[j].Route {
			return evidence.DocsRoutes[i].Route < evidence.DocsRoutes[j].Route
		}
		return evidence.DocsRoutes[i].RelativePath < evidence.DocsRoutes[j].RelativePath
	})
	sort.Slice(evidence.APISpecs, func(i, j int) bool {
		return evidence.APISpecs[i].RelativePath < evidence.APISpecs[j].RelativePath
	})

	return evidence, nil
}

func isServiceEvidenceCandidate(file FileContent, normalizedServiceName string) bool {
	path := strings.ToLower(file.RelativePath)
	if path == "" {
		return false
	}
	if normalizedServiceName != "" && strings.Contains(normalizeEvidenceToken(path), normalizedServiceName) {
		return true
	}

	switch filepath.Ext(path) {
	case ".yaml", ".yml", ".json", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".md":
	default:
		return false
	}

	for _, keyword := range []string{
		"openapi", "swagger", "spec", "docs", "route", "server", "ingress",
		"gateway", "deploy", "values", "config", "application",
	} {
		if strings.Contains(path, keyword) {
			return true
		}
	}
	return false
}

func extractObservedHostnames(content string) []string {
	seen := map[string]struct{}{}
	hostnames := make([]string, 0)
	for _, line := range strings.Split(content, "\n") {
		if !lineLikelyContainsHostname(line) {
			continue
		}
		matches := serviceHostnamePattern.FindAllStringSubmatch(line, -1)
		for _, match := range matches {
			if len(match) < 2 {
				continue
			}
			hostname := strings.ToLower(strings.TrimSpace(match[1]))
			if hostname == "" {
				continue
			}
			if isLikelyFalsePositiveHostname(hostname) {
				continue
			}
			if _, ok := seen[hostname]; ok {
				continue
			}
			seen[hostname] = struct{}{}
			hostnames = append(hostnames, hostname)
		}
	}
	sort.Strings(hostnames)
	return hostnames
}

// isLikelyFalsePositiveHostname rejects regex matches that look like file
// names, code property chains, or test matchers rather than real hostnames.
func isLikelyFalsePositiveHostname(hostname string) bool {
	// Reject file extensions masquerading as TLDs.
	lastDot := strings.LastIndex(hostname, ".")
	if lastDot < 0 {
		return true
	}
	tld := hostname[lastDot+1:]
	if _, blocked := falsePositiveTLDs[tld]; blocked {
		return true
	}

	// Reject compound-word TLDs that indicate code properties (e.g.
	// "baseurl", "cdnprefix", "mediatype"). Real TLDs don't contain
	// these substrings.
	for _, keyword := range codeCompoundKeywords {
		if strings.Contains(tld, keyword) {
			return true
		}
	}

	// Reject code property chains: any segment contains camelCase or
	// underscore patterns that don't appear in real hostnames.
	for _, segment := range strings.Split(hostname, ".") {
		if containsCamelCase(segment) {
			return true
		}
	}

	// Reject if any segment is in the code identifier blocklist.
	for _, segment := range strings.Split(hostname, ".") {
		if _, blocked := falsePositiveSegments[segment]; blocked {
			return true
		}
	}

	// Reject single-character segments (x.jpg, a.b.c patterns).
	parts := strings.Split(hostname, ".")
	for _, part := range parts {
		if len(part) == 0 {
			return true
		}
	}
	if len(parts[0]) <= 1 && len(parts) <= 2 {
		return true
	}

	return false
}

var codeCompoundKeywords = []string{
	"url", "uri", "prefix", "suffix", "path", "type",
	"config", "handler", "helper", "builder", "generator",
	"factory", "controller", "middleware",
}

var falsePositiveSegments = map[string]struct{}{
	"exports": {}, "module": {}, "internals": {}, "require": {},
	"prototype": {}, "constructor": {}, "this": {},
}

var falsePositiveTLDs = map[string]struct{}{
	// File extensions
	"jpg": {}, "jpeg": {}, "png": {}, "gif": {}, "svg": {}, "ico": {},
	"webp": {}, "bmp": {}, "zip": {}, "tar": {}, "gz": {}, "pdf": {},
	"doc": {}, "docx": {}, "xls": {}, "xlsx": {}, "css": {}, "js": {},
	"ts": {}, "mjs": {}, "cjs": {}, "json": {}, "yaml": {}, "yml": {},
	"xml": {}, "html": {}, "htm": {}, "txt": {}, "log": {}, "md": {},
	"csv": {}, "sql": {}, "proto": {}, "lock": {}, "toml": {},
	// Code property/method names
	"debug": {}, "info": {}, "error": {}, "warn": {}, "value": {},
	"url": {}, "includes": {}, "replace": {}, "register": {},
	"tostring": {}, "exports": {}, "equal": {}, "client": {},
	"stub": {}, "spark": {}, "img": {}, "type": {},
	"plugin": {}, "length": {}, "push": {}, "map": {},
	"filter": {}, "reduce": {}, "keys": {}, "values": {},
	"then": {}, "catch": {}, "resolve": {}, "reject": {},
}

var camelCaseRE = regexp.MustCompile(`[a-z][A-Z]`)

func containsCamelCase(s string) bool {
	return camelCaseRE.MatchString(s)
}

func lineLikelyContainsHostname(line string) bool {
	trimmed := strings.TrimSpace(line)
	if trimmed == "" {
		return false
	}
	if strings.Contains(strings.ToLower(trimmed), "://") {
		return true
	}
	return serviceHostnameKeyPattern.MatchString(trimmed) || serviceHostnameEnvKeyPattern.MatchString(trimmed)
}

func inferObservedEnvironments(relativePath string, content string, hostnames []string) []string {
	seen := map[string]struct{}{}
	addMatches := func(text string) {
		for _, environment := range detectEnvironmentAliases(text) {
			seen[environment] = struct{}{}
		}
	}
	addMatches(relativePath)
	addMatches(content)
	for _, hostname := range hostnames {
		addMatches(hostname)
	}

	environments := make([]string, 0, len(seen))
	for environment := range seen {
		environments = append(environments, environment)
	}
	sort.Strings(environments)
	return environments
}

func detectEnvironmentAliases(text string) []string {
	normalized := normalizeEvidenceToken(text)
	if normalized == "" {
		return nil
	}
	seen := map[string]struct{}{}
	for _, row := range environmentAliases {
		for _, alias := range row.aliases {
			if strings.Contains(normalized, "_"+alias+"_") {
				seen[row.canonical] = struct{}{}
				break
			}
		}
	}
	environments := make([]string, 0, len(seen))
	for environment := range seen {
		environments = append(environments, environment)
	}
	sort.Strings(environments)
	return environments
}

func inferHostnameEnvironment(hostname string) string {
	matches := detectEnvironmentAliases(hostname)
	if len(matches) == 0 {
		return ""
	}
	return matches[0]
}

func extractDocsRoutes(content string) []string {
	matches := serviceDocsRoutePattern.FindAllStringSubmatch(content, -1)
	if len(matches) == 0 {
		return nil
	}
	seen := map[string]struct{}{}
	routes := make([]string, 0, len(matches))
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		route := strings.TrimSpace(match[1])
		if route == "" {
			continue
		}
		if !looksLikeDocsRoute(route) {
			continue
		}
		if _, ok := seen[route]; ok {
			continue
		}
		seen[route] = struct{}{}
		routes = append(routes, route)
	}
	sort.Strings(routes)
	return routes
}

func extractAPISpecEvidence(file FileContent) (ServiceAPISpecEvidence, bool) {
	format := serviceEvidenceFormat(file.RelativePath)
	if !isPotentialAPISpecPath(file.RelativePath) {
		return ServiceAPISpecEvidence{}, false
	}

	doc, err := parseLooseYAMLDocument(file.Content)
	if err == nil {
		if spec, ok := buildOpenAPISpecEvidence(file.RelativePath, format, doc); ok {
			return spec, true
		}
	}

	return ServiceAPISpecEvidence{
		RelativePath: file.RelativePath,
		Format:       format,
		Parsed:       false,
	}, true
}

func buildOpenAPISpecEvidence(relativePath string, format string, doc map[string]any) (ServiceAPISpecEvidence, bool) {
	specVersion := serviceStringValue(doc["openapi"])
	if specVersion == "" {
		specVersion = serviceStringValue(doc["swagger"])
	}

	paths := serviceMapValue(doc["paths"])
	if specVersion == "" && len(paths) == 0 {
		return ServiceAPISpecEvidence{}, false
	}

	operationIDCount := 0
	methodCount := 0
	docsRoutes := make([]string, 0)
	endpoints := make([]ServiceAPIEndpointEvidence, 0, len(paths))
	for route, rawOperation := range paths {
		routeMap := serviceMapValue(rawOperation)
		methods := make([]string, 0, len(routeMap))
		operationIDs := make([]string, 0, len(routeMap))
		for method, rawOperationSpec := range routeMap {
			if _, ok := openAPIMethodNames[strings.ToLower(method)]; !ok {
				continue
			}
			methodCount++
			methods = append(methods, strings.ToLower(method))
			operationMap := serviceMapValue(rawOperationSpec)
			if operationID := serviceStringValue(operationMap["operationId"]); operationID != "" {
				operationIDCount++
				operationIDs = append(operationIDs, operationID)
			}
		}
		sort.Strings(methods)
		sort.Strings(operationIDs)
		endpoints = append(endpoints, ServiceAPIEndpointEvidence{
			Path:         route,
			Methods:      methods,
			OperationIDs: operationIDs,
		})
		if looksLikeDocsRoute(route) {
			docsRoutes = append(docsRoutes, route)
		}
	}
	sort.Strings(docsRoutes)
	sort.Slice(endpoints, func(i, j int) bool {
		return endpoints[i].Path < endpoints[j].Path
	})

	hostnames := make([]string, 0)
	seenHostnames := map[string]struct{}{}
	for _, server := range serviceSliceValue(doc["servers"]) {
		serverMap := serviceMapValue(server)
		serverURL := serviceStringValue(serverMap["url"])
		if serverURL == "" {
			continue
		}
		hostname := hostnameFromURL(serverURL)
		if hostname == "" {
			continue
		}
		if _, ok := seenHostnames[hostname]; ok {
			continue
		}
		seenHostnames[hostname] = struct{}{}
		hostnames = append(hostnames, hostname)
	}
	sort.Strings(hostnames)

	info := serviceMapValue(doc["info"])
	return ServiceAPISpecEvidence{
		RelativePath:     relativePath,
		Format:           format,
		Parsed:           true,
		SpecVersion:      specVersion,
		APIVersion:       serviceStringValue(info["version"]),
		EndpointCount:    len(paths),
		MethodCount:      methodCount,
		OperationIDCount: operationIDCount,
		DocsRoutes:       docsRoutes,
		Hostnames:        hostnames,
		Endpoints:        endpoints,
	}, true
}

func parseLooseYAMLDocument(content string) (map[string]any, error) {
	var document map[string]any
	if err := yaml.Unmarshal([]byte(content), &document); err != nil {
		return nil, err
	}
	return document, nil
}

func serviceEvidenceFormat(relativePath string) string {
	switch strings.ToLower(filepath.Ext(relativePath)) {
	case ".yaml", ".yml":
		return "yaml"
	case ".json":
		return "json"
	case ".js", ".mjs", ".cjs":
		return "javascript"
	case ".ts", ".mts", ".cts":
		return "typescript"
	case ".md":
		return "markdown"
	default:
		return "text"
	}
}

func isPotentialAPISpecPath(relativePath string) bool {
	lower := strings.ToLower(relativePath)
	return strings.Contains(lower, "openapi") ||
		strings.Contains(lower, "swagger") ||
		strings.Contains(lower, "spec")
}

func looksLikeDocsRoute(route string) bool {
	lower := strings.ToLower(route)
	if strings.Contains(lower, "docs") || strings.Contains(lower, "swagger") || strings.Contains(lower, "openapi") {
		return true
	}
	for _, segment := range strings.FieldsFunc(lower, func(r rune) bool {
		switch r {
		case '/', '_', '-', '.', ':':
			return true
		default:
			return false
		}
	}) {
		if segment == "spec" || segment == "specs" {
			return true
		}
	}
	return false
}

func hostnameFromURL(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	return strings.ToLower(parsed.Hostname())
}

func normalizeEvidenceToken(text string) string {
	lower := strings.ToLower(text)
	replacer := strings.NewReplacer(
		"/", "_",
		".", "_",
		"-", "_",
		":", "_",
		"@", "_",
		"\n", "_",
		"\t", "_",
		" ", "_",
	)
	return "_" + replacer.Replace(lower) + "_"
}

func serviceSliceValue(raw any) []any {
	switch typed := raw.(type) {
	case []any:
		return typed
	default:
		return nil
	}
}

func serviceMapValue(raw any) map[string]any {
	typed, _ := raw.(map[string]any)
	return typed
}

func serviceStringValue(raw any) string {
	value, _ := raw.(string)
	return value
}
