package query

const openAPIPathsCode = `
    "/api/v0/code/search": {
      "post": {
        "tags": ["code"],
        "summary": "Search code entities",
        "description": "Searches code entities by name pattern or content.",
        "operationId": "searchCode",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["query", "repo_id"],
                "properties": {
                  "query": {"type": "string", "description": "Search pattern"},
                  "repo_id": {"type": "string", "description": "Repository ID"},
                  "language": {"type": "string", "description": "Optional language filter"},
                  "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Search results",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/CodeSearchResponse"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/code/language-query": {
      "post": {
        "tags": ["code"],
        "summary": "Query entities by language and type",
        "description": "Queries graph-backed or content-backed entities for one language/entity-type pair.",
        "operationId": "queryLanguageEntities",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["language", "entity_type"],
                "properties": {
                  "language": {"type": "string", "description": "Language family to query"},
                  "entity_type": {
                    "type": "string",
                    "description": "Entity type to query",
                    "enum": [
                      "repository",
                      "directory",
                      "file",
                      "module",
                      "function",
                      "class",
                      "struct",
                      "enum",
                      "union",
                      "macro",
                      "variable",
                      "annotation",
                      "protocol",
                      "impl_block",
                      "type_alias",
                      "type_annotation",
                      "typedef",
                      "component",
                      "terraform_module",
                      "terragrunt_config",
                      "terragrunt_dependency",
                      "terragrunt_local",
                      "terragrunt_input"
                    ]
                  },
                  "query": {"type": "string", "description": "Optional name filter"},
                  "repo_id": {"type": "string", "description": "Optional repository ID filter"},
                  "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Language query results",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/LanguageQueryResponse"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/code/relationships": {
      "post": {
        "tags": ["code"],
        "summary": "Get code relationships",
        "description": "Returns incoming and outgoing relationships for an entity.",
        "operationId": "getCodeRelationships",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "anyOf": [
                  {"required": ["entity_id"]},
                  {"required": ["name"]}
                ],
                "properties": {
                  "entity_id": {"type": "string"},
                  "name": {
                    "type": "string",
                    "description": "Optional entity name fragment when entity_id is not available."
                  },
                  "direction": {
                    "type": "string",
                    "enum": ["incoming", "outgoing"],
                    "description": "Optional relationship direction filter."
                  },
                  "relationship_type": {
                    "type": "string",
                    "description": "Optional relationship type filter such as CALLS, IMPORTS, or REFERENCES."
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Entity relationships",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "entity_id": {"type": "string"},
                    "name": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "file_path": {"type": "string"},
                    "repo_id": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "language": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "metadata": {"type": "object", "additionalProperties": true},
                    "outgoing": {"type": "array", "items": {"$ref": "#/components/schemas/Relationship"}},
                    "incoming": {"type": "array", "items": {"$ref": "#/components/schemas/Relationship"}}
                  }
                }
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/code/call-chain": {
      "post": {
        "tags": ["code"],
        "summary": "Find transitive call chains",
        "description": "Finds shortest call chains between two functions by following canonical CALLS edges.",
        "operationId": "getCodeCallChain",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "start": {"type": "string", "description": "Exact caller function name when start_entity_id is omitted"},
                  "end": {"type": "string", "description": "Exact callee function name when end_entity_id is omitted"},
                  "start_entity_id": {"type": "string", "description": "Canonical caller entity id. Takes precedence over start when provided."},
                  "end_entity_id": {"type": "string", "description": "Canonical callee entity id. Takes precedence over end when provided."},
                  "repo_id": {"type": "string", "description": "Optional repository id to scope both endpoints to one repository."},
                  "max_depth": {"type": "integer", "description": "Maximum traversal depth (default 5, max 10)", "default": 5}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Call chain results",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "start_entity_id": {"type": "string"},
                    "end_entity_id": {"type": "string"},
                    "repo_id": {"type": "string"},
                    "chains": {
                      "type": "array",
                      "items": {
                        "type": "object",
                        "properties": {
                          "depth": {"type": "integer"},
                          "chain": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/EntityRef"}
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/code/dead-code": {
      "post": {
        "tags": ["code"],
        "summary": "Find dead code",
        "description": "Finds entities with no incoming references and can exclude known decorator-owned entrypoints.",
        "operationId": "findDeadCode",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "repo_id": {"type": "string", "description": "Optional repository ID filter"},
                  "exclude_decorated_with": {
                    "type": "array",
                    "description": "Optional list of decorator names to exclude from the results.",
                    "items": {"type": "string"}
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Dead code candidates",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repo_id": {"type": "string"},
                    "results": {"type": "array", "items": {"$ref": "#/components/schemas/EntityRef"}}
                  }
                }
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/code/complexity": {
      "post": {
        "tags": ["code"],
        "summary": "Get complexity metrics",
        "description": "Returns relationship-based complexity metrics for an entity.",
        "operationId": "getComplexity",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["entity_id"],
                "properties": {
                  "entity_id": {"type": "string"},
                  "repo_id": {"type": "string"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Complexity metrics",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "entity_id": {"type": "string"},
                    "name": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "file_path": {"type": "string"},
                    "repo_id": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "language": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "metadata": {"type": "object", "additionalProperties": true},
                    "outgoing_count": {"type": "integer"},
                    "incoming_count": {"type": "integer"},
                    "total_relationships": {"type": "integer"}
                  }
                }
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
`
