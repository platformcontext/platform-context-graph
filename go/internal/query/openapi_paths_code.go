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
                      "type_alias",
                      "type_annotation",
                      "component"
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
                "required": ["entity_id"],
                "properties": {
                  "entity_id": {"type": "string"}
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
    "/api/v0/code/dead-code": {
      "post": {
        "tags": ["code"],
        "summary": "Find dead code",
        "description": "Finds entities with no incoming references.",
        "operationId": "findDeadCode",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["repo_id"],
                "properties": {
                  "repo_id": {"type": "string"}
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
