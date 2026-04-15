package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
)

// dispatchTool routes an MCP tool call to the appropriate internal HTTP endpoint.
func dispatchTool(ctx context.Context, handler http.Handler, toolName string, args map[string]any, logger *slog.Logger) (any, error) {
	route, err := resolveRoute(toolName, args)
	if err != nil {
		return nil, err
	}

	logger.Debug("dispatch tool", "tool", toolName, "method", route.method, "path", route.path)

	var body io.Reader
	if route.body != nil {
		encoded, err := json.Marshal(route.body)
		if err != nil {
			return nil, fmt.Errorf("encode request body: %w", err)
		}
		body = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, route.method, route.path, body)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	// Set query parameters
	if len(route.query) > 0 {
		q := req.URL.Query()
		for k, v := range route.query {
			q.Set(k, v)
		}
		req.URL.RawQuery = q.Encode()
	}

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code >= 400 {
		return nil, fmt.Errorf("HTTP %d: %s", rec.Code, rec.Body.String())
	}

	var result any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		return rec.Body.String(), nil
	}
	return result, nil
}

type route struct {
	method string
	path   string
	body   any
	query  map[string]string
}

func str(args map[string]any, key string) string {
	v, _ := args[key].(string)
	return v
}

func intOr(args map[string]any, key string, def int) int {
	v, ok := args[key].(float64)
	if !ok {
		return def
	}
	return int(v)
}

func boolOr(args map[string]any, key string, def bool) bool {
	v, ok := args[key].(bool)
	if !ok {
		return def
	}
	return v
}

func stringSlice(args map[string]any, key string) []any {
	raw, ok := args[key]
	if !ok {
		return nil
	}
	values, ok := raw.([]any)
	if ok {
		return values
	}
	stringValues, ok := raw.([]string)
	if !ok {
		return nil
	}
	result := make([]any, 0, len(stringValues))
	for _, value := range stringValues {
		result = append(result, value)
	}
	return result
}

func parseMaxDepth(args map[string]any, defaultDepth int) int {
	if depth, ok := args["max_depth"].(float64); ok {
		return int(depth)
	}
	contextValue := str(args, "context")
	if contextValue == "" {
		return defaultDepth
	}
	depth, err := strconv.Atoi(strings.TrimSpace(contextValue))
	if err != nil {
		return defaultDepth
	}
	return depth
}

// resolveRoute maps a tool name and its arguments to an internal HTTP route.
func resolveRoute(toolName string, args map[string]any) (*route, error) {
	switch toolName {
	// ── Code ──
	case "find_code":
		return &route{method: "POST", path: "/api/v0/code/search", body: map[string]any{
			"query": str(args, "query"), "repo_id": str(args, "repo_id"),
			"limit": intOr(args, "limit", 10), "exact": boolOr(args, "exact", false),
		}}, nil
	case "analyze_code_relationships":
		body := map[string]any{
			"entity_id":  str(args, "target"),
			"query_type": str(args, "query_type"),
		}
		switch str(args, "query_type") {
		case "find_callers":
			body = map[string]any{
				"name":              str(args, "target"),
				"direction":         "incoming",
				"relationship_type": "CALLS",
			}
		case "find_callees":
			body = map[string]any{
				"name":              str(args, "target"),
				"direction":         "outgoing",
				"relationship_type": "CALLS",
			}
		case "find_importers":
			body = map[string]any{
				"name":              str(args, "target"),
				"direction":         "incoming",
				"relationship_type": "IMPORTS",
			}
		case "call_chain":
			start, end, ok := strings.Cut(str(args, "target"), "->")
			if !ok {
				return nil, fmt.Errorf("call_chain target must use start->end format")
			}
			return &route{method: "POST", path: "/api/v0/code/call-chain", body: map[string]any{
				"start":     strings.TrimSpace(start),
				"end":       strings.TrimSpace(end),
				"max_depth": parseMaxDepth(args, 5),
			}}, nil
		case "dead_code":
			return &route{method: "POST", path: "/api/v0/code/dead-code", body: map[string]any{
				"repo_id":                str(args, "repo_id"),
				"exclude_decorated_with": stringSlice(args, "exclude_decorated_with"),
			}}, nil
		}
		return &route{method: "POST", path: "/api/v0/code/relationships", body: body}, nil
	case "find_dead_code":
		return &route{method: "POST", path: "/api/v0/code/dead-code", body: map[string]any{
			"repo_id":                str(args, "repo_id"),
			"exclude_decorated_with": stringSlice(args, "exclude_decorated_with"),
		}}, nil
	case "calculate_cyclomatic_complexity":
		return &route{method: "POST", path: "/api/v0/code/complexity", body: map[string]any{
			"entity_id": str(args, "function_name"), "repo_id": str(args, "repo_id"),
		}}, nil
	case "find_most_complex_functions":
		return &route{method: "POST", path: "/api/v0/code/complexity", body: map[string]any{
			"repo_id": str(args, "repo_id"), "limit": intOr(args, "limit", 10),
		}}, nil
	case "execute_language_query":
		return &route{method: "POST", path: "/api/v0/code/language-query", body: map[string]any{
			"language": str(args, "language"), "entity_type": str(args, "entity_type"),
			"query": str(args, "query"), "repo_id": str(args, "repo_id"),
			"limit": intOr(args, "limit", 50),
		}}, nil
	case "find_function_call_chain":
		return &route{method: "POST", path: "/api/v0/code/call-chain", body: map[string]any{
			"start": str(args, "start"), "end": str(args, "end"),
			"max_depth": intOr(args, "max_depth", 5),
		}}, nil

	// ── Repositories ──
	case "list_indexed_repositories":
		return &route{method: "GET", path: "/api/v0/repositories"}, nil
	case "get_repository_stats":
		repoID := str(args, "repo_id")
		if repoID == "" {
			return &route{method: "GET", path: "/api/v0/repositories"}, nil
		}
		return &route{method: "GET", path: "/api/v0/repositories/" + url.PathEscape(repoID) + "/stats"}, nil
	case "get_repo_context":
		return &route{method: "GET", path: "/api/v0/repositories/" + url.PathEscape(str(args, "repo_id")) + "/context"}, nil
	case "get_repo_story":
		return &route{method: "GET", path: "/api/v0/repositories/" + url.PathEscape(str(args, "repo_id")) + "/story"}, nil
	case "get_repo_summary":
		// repo_summary uses repo_name, map to context endpoint
		name := str(args, "repo_name")
		if name == "" {
			name = str(args, "repo_id")
		}
		return &route{method: "GET", path: "/api/v0/repositories/" + url.PathEscape(name) + "/context"}, nil
	case "get_repository_coverage":
		return &route{method: "GET", path: "/api/v0/repositories/" + url.PathEscape(str(args, "repo_id")) + "/coverage"}, nil

	// ── Entities ──
	case "resolve_entity":
		return &route{method: "POST", path: "/api/v0/entities/resolve", body: args}, nil
	case "get_entity_context":
		q := map[string]string{}
		if env := str(args, "environment"); env != "" {
			q["environment"] = env
		}
		return &route{method: "GET", path: "/api/v0/entities/" + url.PathEscape(str(args, "entity_id")) + "/context", query: q}, nil
	case "get_workload_context":
		q := map[string]string{}
		if env := str(args, "environment"); env != "" {
			q["environment"] = env
		}
		return &route{method: "GET", path: "/api/v0/workloads/" + url.PathEscape(str(args, "workload_id")) + "/context", query: q}, nil
	case "get_workload_story":
		q := map[string]string{}
		if env := str(args, "environment"); env != "" {
			q["environment"] = env
		}
		return &route{method: "GET", path: "/api/v0/workloads/" + url.PathEscape(str(args, "workload_id")) + "/story", query: q}, nil
	case "get_service_context":
		q := map[string]string{}
		if env := str(args, "environment"); env != "" {
			q["environment"] = env
		}
		return &route{method: "GET", path: "/api/v0/services/" + url.PathEscape(str(args, "workload_id")) + "/context", query: q}, nil
	case "get_service_story":
		q := map[string]string{}
		if env := str(args, "environment"); env != "" {
			q["environment"] = env
		}
		return &route{method: "GET", path: "/api/v0/services/" + url.PathEscape(str(args, "workload_id")) + "/story", query: q}, nil

	// ── Content ──
	case "get_file_content":
		return &route{method: "POST", path: "/api/v0/content/files/read", body: map[string]any{
			"repo_id": str(args, "repo_id"), "relative_path": str(args, "relative_path"),
		}}, nil
	case "get_file_lines":
		return &route{method: "POST", path: "/api/v0/content/files/lines", body: args}, nil
	case "get_entity_content":
		return &route{method: "POST", path: "/api/v0/content/entities/read", body: map[string]any{
			"entity_id": str(args, "entity_id"),
		}}, nil
	case "search_file_content":
		return &route{method: "POST", path: "/api/v0/content/files/search", body: args}, nil
	case "search_entity_content":
		return &route{method: "POST", path: "/api/v0/content/entities/search", body: args}, nil

	// ── Infra ──
	case "find_infra_resources":
		return &route{method: "POST", path: "/api/v0/infra/resources/search", body: map[string]any{
			"query": str(args, "query"), "category": str(args, "category"),
		}}, nil
	case "analyze_infra_relationships":
		return &route{method: "POST", path: "/api/v0/infra/relationships", body: map[string]any{
			"entity_id": str(args, "target"), "relationship_type": str(args, "query_type"),
		}}, nil
	case "get_ecosystem_overview":
		return &route{method: "GET", path: "/api/v0/ecosystem/overview"}, nil

	// ── Impact ──
	case "trace_deployment_chain":
		return &route{method: "POST", path: "/api/v0/impact/trace-deployment-chain", body: map[string]any{
			"service_name":                 str(args, "service_name"),
			"direct_only":                  boolOr(args, "direct_only", true),
			"max_depth":                    intOr(args, "max_depth", 8),
			"include_related_module_usage": boolOr(args, "include_related_module_usage", false),
		}}, nil
	case "find_blast_radius":
		return &route{method: "POST", path: "/api/v0/impact/blast-radius", body: args}, nil
	case "find_change_surface":
		return &route{method: "POST", path: "/api/v0/impact/change-surface", body: args}, nil
	case "trace_resource_to_code":
		return &route{method: "POST", path: "/api/v0/impact/trace-resource-to-code", body: args}, nil
	case "explain_dependency_path":
		return &route{method: "POST", path: "/api/v0/impact/explain-dependency-path", body: args}, nil

	// ── Compare ──
	case "compare_environments":
		return &route{method: "POST", path: "/api/v0/compare/environments", body: args}, nil

	// ── Status ──
	case "list_ingesters":
		return &route{method: "GET", path: "/api/v0/status/ingesters"}, nil
	case "get_ingester_status":
		ingester := str(args, "ingester")
		if ingester == "" {
			ingester = "repository"
		}
		return &route{method: "GET", path: "/api/v0/status/ingesters/" + url.PathEscape(ingester)}, nil
	case "get_index_status":
		return &route{method: "GET", path: "/api/v0/index-status"}, nil

	default:
		return nil, fmt.Errorf("unknown tool: %s", toolName)
	}
}
