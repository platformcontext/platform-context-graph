package query

const openAPIPathsRepositories = `
    "/health": {
      "get": {
        "tags": ["health"],
        "summary": "Health check",
        "description": "Returns the health status of the API service.",
        "operationId": "getHealth",
        "responses": {
          "200": {
            "description": "Service is healthy",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": {"type": "string", "example": "ok"}
                  }
                }
              }
            }
          }
        }
      }
    },
    "/api/v0/repositories": {
      "get": {
        "tags": ["repositories"],
        "summary": "List repositories",
        "description": "Returns all indexed repositories.",
        "operationId": "listRepositories",
        "responses": {
          "200": {
            "description": "List of repositories",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repositories": {
                      "type": "array",
                      "items": {"$ref": "#/components/schemas/Repository"}
                    },
                    "count": {"type": "integer"}
                  }
                }
              }
            }
          },
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/repositories/{repo_id}/context": {
      "get": {
        "tags": ["repositories"],
        "summary": "Get repository context",
        "description": "Returns repository metadata with graph statistics.",
        "operationId": "getRepositoryContext",
        "parameters": [
          {"$ref": "#/components/parameters/RepoId"}
        ],
        "responses": {
          "200": {
            "description": "Repository context",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repository": {"$ref": "#/components/schemas/RepositoryRef"},
                    "file_count": {"type": "integer"},
                    "workload_count": {"type": "integer"},
                    "platform_count": {"type": "integer"},
                    "dependency_count": {"type": "integer"}
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
    "/api/v0/repositories/{repo_id}/story": {
      "get": {
        "tags": ["repositories"],
        "summary": "Get repository story",
        "description": "Returns a structured repository story with deployment and support overviews.",
        "operationId": "getRepositoryStory",
        "parameters": [
          {"$ref": "#/components/parameters/RepoId"}
        ],
        "responses": {
          "200": {
            "description": "Repository narrative",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repository": {"$ref": "#/components/schemas/RepositoryRef"},
                    "subject": {"type": "object"},
                    "story": {"type": "string"},
                    "story_sections": {"type": "array", "items": {"type": "object"}},
                    "semantic_overview": {"type": "object"},
                    "deployment_overview": {"type": "object"},
                    "gitops_overview": {"type": "object"},
                    "documentation_overview": {"type": "object"},
                    "support_overview": {"type": "object"},
                    "coverage_summary": {"type": "object"},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "drilldowns": {"type": "object"}
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
    "/api/v0/repositories/{repo_id}/stats": {
      "get": {
        "tags": ["repositories"],
        "summary": "Get repository statistics",
        "description": "Returns repository statistics including entity counts.",
        "operationId": "getRepositoryStats",
        "parameters": [
          {"$ref": "#/components/parameters/RepoId"}
        ],
        "responses": {
          "200": {
            "description": "Repository statistics",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repository": {"$ref": "#/components/schemas/RepositoryRef"},
                    "file_count": {"type": "integer"},
                    "languages": {"type": "array", "items": {"type": "string"}},
                    "entity_count": {"type": "integer"},
                    "entity_types": {"type": "array", "items": {"type": "string"}}
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
    "/api/v0/repositories/{repo_id}/coverage": {
      "get": {
        "tags": ["repositories"],
        "summary": "Get repository coverage",
        "description": "Returns content store coverage metrics for the repository.",
        "operationId": "getRepositoryCoverage",
        "parameters": [
          {"$ref": "#/components/parameters/RepoId"}
        ],
        "responses": {
          "200": {
            "description": "Repository coverage",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repo_id": {"type": "string"},
                    "file_count": {"type": "integer"},
                    "entity_count": {"type": "integer"},
                    "languages": {
                      "type": "array",
                      "items": {
                        "type": "object",
                        "properties": {
                          "language": {"type": "string"},
                          "file_count": {"type": "integer"}
                        }
                      }
                    }
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
