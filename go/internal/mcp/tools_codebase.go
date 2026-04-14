package mcp

func codebaseTools() []ToolDefinition {
	return []ToolDefinition{
		{
			Name:        "find_code",
			Description: "Find relevant code snippets related to a keyword (e.g., function name, class name, or content) within an optional canonical repository identifier.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"query": map[string]any{
						"type":        "string",
						"description": "Keyword or phrase to search for",
					},
					"exact": map[string]any{
						"type":        "boolean",
						"description": "Whether to perform exact matching",
						"default":     false,
					},
					"edit_distance": map[string]any{
						"type":        "number",
						"description": "Maximum edit distance for fuzzy matching",
						"default":     2,
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier to scope the search",
					},
					"limit": map[string]any{
						"type":        "integer",
						"description": "Maximum number of results to return",
						"default":     10,
					},
					"scope": map[string]any{
						"type":        "string",
						"description": "Search scope",
						"default":     "auto",
					},
				},
				"required": []string{"query"},
			},
		},
		{
			Name:        "analyze_code_relationships",
			Description: "Analyze code relationships like 'who calls this function' or 'class hierarchy'. Supported query types include: find_callers, find_callees, find_all_callers, find_all_callees, find_importers, who_modifies, class_hierarchy, overrides, dead_code, call_chain, module_deps, variable_scope, find_complexity, find_functions_by_argument, find_functions_by_decorator.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"query_type": map[string]any{
						"type":        "string",
						"description": "Type of relationship analysis to perform",
						"enum": []string{
							"find_callers",
							"find_callees",
							"find_all_callers",
							"find_all_callees",
							"find_importers",
							"who_modifies",
							"class_hierarchy",
							"overrides",
							"dead_code",
							"call_chain",
							"module_deps",
							"variable_scope",
							"find_complexity",
							"find_functions_by_argument",
							"find_functions_by_decorator",
						},
					},
					"target": map[string]any{
						"type":        "string",
						"description": "Target entity to analyze",
					},
					"context": map[string]any{
						"type":        "string",
						"description": "Optional context for the analysis",
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier",
					},
					"scope": map[string]any{
						"type":        "string",
						"description": "Analysis scope",
						"default":     "auto",
					},
				},
				"required": []string{"query_type", "target"},
			},
		},
		{
			Name:        "find_dead_code",
			Description: "Find potentially unused functions (dead code) across the indexed codebase, optionally scoped to a canonical repository identifier and excluding functions with specific decorators.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"exclude_decorated_with": map[string]any{
						"type":        "array",
						"items":       map[string]any{"type": "string"},
						"description": "List of decorator names to exclude from dead code analysis",
						"default":     []any{},
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier",
					},
					"scope": map[string]any{
						"type":        "string",
						"description": "Search scope",
						"default":     "auto",
					},
				},
				"required": []string{},
			},
		},
		{
			Name:        "calculate_cyclomatic_complexity",
			Description: "Calculate the cyclomatic complexity of a specific function to measure its complexity.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"function_name": map[string]any{
						"type":        "string",
						"description": "Name of the function to analyze",
					},
					"path": map[string]any{
						"type":        "string",
						"description": "Optional file path containing the function",
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier",
					},
					"scope": map[string]any{
						"type":        "string",
						"description": "Analysis scope",
						"default":     "auto",
					},
				},
				"required": []string{"function_name"},
			},
		},
		{
			Name:        "find_most_complex_functions",
			Description: "Find the most complex functions in the codebase based on cyclomatic complexity.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"limit": map[string]any{
						"type":        "integer",
						"description": "Maximum number of results to return",
						"default":     10,
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier",
					},
					"scope": map[string]any{
						"type":        "string",
						"description": "Search scope",
						"default":     "auto",
					},
				},
				"required": []string{},
			},
		},
		{
			Name:        "list_indexed_repositories",
			Description: "List all indexed repositories.",
			InputSchema: map[string]any{
				"type":       "object",
				"properties": map[string]any{},
				"required":   []string{},
			},
		},
		{
			Name:        "execute_cypher_query",
			Description: "Fallback tool to run a direct, read-only Cypher query against the code graph.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"cypher_query": map[string]any{
						"type":        "string",
						"description": "Read-only Cypher query to execute",
					},
				},
				"required": []string{"cypher_query"},
			},
		},
		{
			Name:        "visualize_graph_query",
			Description: "Generates a URL to visualize the results of a Cypher query in the Neo4j Browser.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"cypher_query": map[string]any{
						"type":        "string",
						"description": "Cypher query to visualize",
					},
				},
				"required": []string{"cypher_query"},
			},
		},
		{
			Name:        "search_registry_bundles",
			Description: "Search for available pre-indexed bundles in the registry.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"query": map[string]any{
						"type":        "string",
						"description": "Search query for bundles",
					},
					"unique_only": map[string]any{
						"type":        "boolean",
						"description": "Return only unique bundles",
						"default":     false,
					},
				},
				"required": []string{},
			},
		},
		{
			Name:        "get_repository_stats",
			Description: "Get graph-derived statistics about indexed repositories.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier",
					},
				},
				"required": []string{},
			},
		},
	}
}
