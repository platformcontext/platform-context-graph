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
		{
			Name:        "execute_language_query",
			Description: "Execute a language-specific query to find code entities (functions, classes, structs, etc.) filtered by programming language. Supports 15 languages: c, cpp, csharp, dart, go, haskell, java, javascript, perl, python, ruby, rust, scala, swift, typescript.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"language": map[string]any{
						"type":        "string",
						"description": "Programming language to filter by (e.g., python, go, rust)",
					},
					"entity_type": map[string]any{
						"type":        "string",
						"description": "Type of code entity to search for",
						"enum":        []string{"repository", "directory", "file", "module", "function", "class", "struct", "enum", "union", "macro", "variable"},
					},
					"query": map[string]any{
						"type":        "string",
						"description": "Optional name pattern to filter results",
					},
					"repo_id": map[string]any{
						"type":        "string",
						"description": "Optional canonical repository identifier to scope the search",
					},
					"limit": map[string]any{
						"type":        "integer",
						"description": "Maximum number of results to return",
						"default":     50,
					},
				},
				"required": []string{"language", "entity_type"},
			},
		},
		{
			Name:        "find_function_call_chain",
			Description: "Find the transitive call chain between two functions by following CALLS edges in the code graph. Returns shortest paths up to a configurable depth.",
			InputSchema: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"start": map[string]any{
						"type":        "string",
						"description": "Starting function name or entity ID",
					},
					"end": map[string]any{
						"type":        "string",
						"description": "Ending function name or entity ID",
					},
					"max_depth": map[string]any{
						"type":        "integer",
						"description": "Maximum chain depth (1-10)",
						"default":     5,
					},
				},
				"required": []string{"start", "end"},
			},
		},
	}
}
