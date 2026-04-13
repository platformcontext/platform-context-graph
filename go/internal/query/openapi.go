package query

import "net/http"

// OpenAPISpec is the OpenAPI 3.0 specification for the PCG Query API.
const OpenAPISpec = `{
  "openapi": "3.0.3",
  "info": {
    "title": "Platform Context Graph API",
    "description": "Query API for the Platform Context Graph canonical knowledge graph. Provides read access to repositories, entities, code analysis, content, infrastructure, impact analysis, pipeline status, and environment comparison.",
    "version": "0.1.0",
    "contact": {
      "name": "Platform Context Graph"
    }
  },
  "servers": [
    {
      "url": "/api/v0",
      "description": "API v0 prefix"
    }
  ],
  "tags": [
    {"name": "health", "description": "Health check endpoints"},
    {"name": "repositories", "description": "Repository queries and context"},
    {"name": "entities", "description": "Entity resolution and relationships"},
    {"name": "code", "description": "Code search and analysis"},
    {"name": "content", "description": "Content store access"},
    {"name": "infrastructure", "description": "Infrastructure resource queries"},
    {"name": "impact", "description": "Impact analysis and dependency tracing"},
    {"name": "status", "description": "Pipeline and ingester status"},
    {"name": "compare", "description": "Environment comparison"}
  ],
  "paths": {
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
        "description": "Returns a narrative summary for the repository.",
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
                    "story": {"type": "string"}
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
    "/api/v0/entities/resolve": {
      "post": {
        "tags": ["entities"],
        "summary": "Resolve entity",
        "description": "Resolves an entity by name with optional type and repository filters.",
        "operationId": "resolveEntity",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {"type": "string", "description": "Entity name to search for"},
                  "type": {"type": "string", "description": "Optional entity type filter"},
                  "repo_id": {"type": "string", "description": "Optional repository ID filter"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Resolved entities",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "entities": {
                      "type": "array",
                      "items": {"$ref": "#/components/schemas/EntityRef"}
                    },
                    "count": {"type": "integer"}
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
    "/api/v0/entities/{entity_id}/context": {
      "get": {
        "tags": ["entities"],
        "summary": "Get entity context",
        "description": "Returns context and relationships for a specific entity.",
        "operationId": "getEntityContext",
        "parameters": [
          {"$ref": "#/components/parameters/EntityId"}
        ],
        "responses": {
          "200": {
            "description": "Entity context",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "id": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "name": {"type": "string"},
                    "file_path": {"type": "string"},
                    "repo_id": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "relationships": {"type": "array", "items": {"$ref": "#/components/schemas/Relationship"}}
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
    "/api/v0/workloads/{workload_id}/context": {
      "get": {
        "tags": ["entities"],
        "summary": "Get workload context",
        "description": "Returns context and deployment instances for a workload.",
        "operationId": "getWorkloadContext",
        "parameters": [
          {"$ref": "#/components/parameters/WorkloadId"}
        ],
        "responses": {
          "200": {
            "description": "Workload context",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/WorkloadContext"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/workloads/{workload_id}/story": {
      "get": {
        "tags": ["entities"],
        "summary": "Get workload story",
        "description": "Returns a narrative summary for the workload.",
        "operationId": "getWorkloadStory",
        "parameters": [
          {"$ref": "#/components/parameters/WorkloadId"}
        ],
        "responses": {
          "200": {
            "description": "Workload narrative",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "workload_id": {"type": "string"},
                    "name": {"type": "string"},
                    "story": {"type": "string"}
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
    "/api/v0/services/{service_name}/context": {
      "get": {
        "tags": ["entities"],
        "summary": "Get service context",
        "description": "Returns context for a service by name.",
        "operationId": "getServiceContext",
        "parameters": [
          {"$ref": "#/components/parameters/ServiceName"}
        ],
        "responses": {
          "200": {
            "description": "Service context",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/WorkloadContext"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/services/{service_name}/story": {
      "get": {
        "tags": ["entities"],
        "summary": "Get service story",
        "description": "Returns a narrative summary for the service.",
        "operationId": "getServiceStory",
        "parameters": [
          {"$ref": "#/components/parameters/ServiceName"}
        ],
        "responses": {
          "200": {
            "description": "Service narrative",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "service_name": {"type": "string"},
                    "story": {"type": "string"}
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
                "schema": {
                  "type": "object",
                  "properties": {
                    "source": {"type": "string", "enum": ["graph", "content"]},
                    "query": {"type": "string"},
                    "repo_id": {"type": "string"},
                    "results": {"type": "array", "items": {"type": "object"}}
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
    "/api/v0/content/files/read": {
      "post": {
        "tags": ["content"],
        "summary": "Read file content",
        "description": "Reads full file content from the content store.",
        "operationId": "readFile",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["repo_id", "relative_path"],
                "properties": {
                  "repo_id": {"type": "string"},
                  "relative_path": {"type": "string"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "File content",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/content/files/lines": {
      "post": {
        "tags": ["content"],
        "summary": "Read file lines",
        "description": "Reads a line range from a file.",
        "operationId": "readFileLines",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["repo_id", "relative_path", "start_line", "end_line"],
                "properties": {
                  "repo_id": {"type": "string"},
                  "relative_path": {"type": "string"},
                  "start_line": {"type": "integer"},
                  "end_line": {"type": "integer"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "File lines",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/content/entities/read": {
      "post": {
        "tags": ["content"],
        "summary": "Read entity content",
        "description": "Reads entity source code from the content store.",
        "operationId": "readEntity",
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
            "description": "Entity content",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/content/files/search": {
      "post": {
        "tags": ["content"],
        "summary": "Search file content",
        "description": "Searches file content by pattern.",
        "operationId": "searchFiles",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["repo_id", "query"],
                "properties": {
                  "repo_id": {"type": "string"},
                  "query": {"type": "string"},
                  "limit": {"type": "integer", "default": 50}
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
                "schema": {
                  "type": "object",
                  "properties": {
                    "results": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"}
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
    "/api/v0/content/entities/search": {
      "post": {
        "tags": ["content"],
        "summary": "Search entity content",
        "description": "Searches entity source code by pattern.",
        "operationId": "searchEntities",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["repo_id", "query"],
                "properties": {
                  "repo_id": {"type": "string"},
                  "query": {"type": "string"},
                  "limit": {"type": "integer", "default": 50}
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
                "schema": {
                  "type": "object",
                  "properties": {
                    "results": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"}
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
    "/api/v0/infra/resources/search": {
      "post": {
        "tags": ["infrastructure"],
        "summary": "Search infrastructure resources",
        "description": "Searches infrastructure resources by name or ID.",
        "operationId": "searchInfraResources",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                  "query": {"type": "string"},
                  "kind": {"type": "string"},
                  "limit": {"type": "integer", "default": 50}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Infrastructure resources",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "results": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"}
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
    "/api/v0/infra/relationships": {
      "post": {
        "tags": ["infrastructure"],
        "summary": "Get infrastructure relationships",
        "description": "Returns all relationships for an infrastructure entity.",
        "operationId": "getInfraRelationships",
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
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
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
    "/api/v0/ecosystem/overview": {
      "get": {
        "tags": ["infrastructure"],
        "summary": "Get ecosystem overview",
        "description": "Returns high-level entity counts from the graph.",
        "operationId": "getEcosystemOverview",
        "responses": {
          "200": {
            "description": "Ecosystem overview",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "repo_count": {"type": "integer"},
                    "workload_count": {"type": "integer"},
                    "platform_count": {"type": "integer"},
                    "instance_count": {"type": "integer"}
                  }
                }
              }
            }
          },
          "500": {"$ref": "#/components/responses/InternalError"}
        }
      }
    },
    "/api/v0/impact/blast-radius": {
      "post": {
        "tags": ["impact"],
        "summary": "Find blast radius",
        "description": "Analyzes the blast radius for a target entity.",
        "operationId": "findBlastRadius",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["target", "target_type"],
                "properties": {
                  "target": {"type": "string", "description": "Target entity name"},
                  "target_type": {
                    "type": "string",
                    "enum": ["repository", "terraform_module", "crossplane_xrd", "sql_table"],
                    "description": "Type of target entity"
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Blast radius analysis",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "target": {"type": "string"},
                    "target_type": {"type": "string"},
                    "affected": {"type": "array", "items": {"type": "object"}},
                    "affected_count": {"type": "integer"}
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
    "/api/v0/impact/change-surface": {
      "post": {
        "tags": ["impact"],
        "summary": "Find change surface",
        "description": "Analyzes the change surface for a target entity.",
        "operationId": "findChangeSurface",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["target"],
                "properties": {
                  "target": {"type": "string", "description": "Target entity ID"},
                  "environment": {"type": "string", "description": "Optional environment filter"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Change surface analysis",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "target": {"type": "object"},
                    "impacted": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "environment": {"type": "string"}
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
    "/api/v0/impact/trace-resource-to-code": {
      "post": {
        "tags": ["impact"],
        "summary": "Trace resource to code",
        "description": "Traces a resource back to its source code repositories.",
        "operationId": "traceResourceToCode",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["start"],
                "properties": {
                  "start": {"type": "string", "description": "Starting entity ID"},
                  "environment": {"type": "string"},
                  "max_depth": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Trace paths",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "start": {"type": "object"},
                    "paths": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "environment": {"type": "string"}
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
    "/api/v0/impact/explain-dependency-path": {
      "post": {
        "tags": ["impact"],
        "summary": "Explain dependency path",
        "description": "Finds and explains the shortest path between two entities.",
        "operationId": "explainDependencyPath",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["source", "target"],
                "properties": {
                  "source": {"type": "string", "description": "Source entity ID"},
                  "target": {"type": "string", "description": "Target entity ID"},
                  "environment": {"type": "string"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Dependency path",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "source": {"type": "object"},
                    "target": {"type": "object"},
                    "path": {"type": "object"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "environment": {"type": "string"}
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
    "/api/v0/status/pipeline": {
      "get": {
        "tags": ["status"],
        "summary": "Get pipeline status",
        "description": "Returns the full pipeline status report.",
        "operationId": "getPipelineStatus",
        "responses": {
          "200": {
            "description": "Pipeline status",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          },
          "500": {"$ref": "#/components/responses/InternalError"},
          "503": {"$ref": "#/components/responses/ServiceUnavailable"}
        }
      }
    },
    "/api/v0/status/ingesters": {
      "get": {
        "tags": ["status"],
        "summary": "List ingesters",
        "description": "Returns known ingesters with basic health info.",
        "operationId": "listIngesters",
        "responses": {
          "200": {
            "description": "List of ingesters",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "ingesters": {"type": "array", "items": {"type": "object"}},
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
    "/api/v0/status/ingesters/{ingester}": {
      "get": {
        "tags": ["status"],
        "summary": "Get ingester status",
        "description": "Returns detailed status for a specific ingester.",
        "operationId": "getIngesterStatus",
        "parameters": [
          {
            "name": "ingester",
            "in": "path",
            "required": true,
            "schema": {"type": "string"},
            "description": "Ingester name"
          }
        ],
        "responses": {
          "200": {
            "description": "Ingester status",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          },
          "400": {"$ref": "#/components/responses/BadRequest"},
          "404": {"$ref": "#/components/responses/NotFound"},
          "500": {"$ref": "#/components/responses/InternalError"},
          "503": {"$ref": "#/components/responses/ServiceUnavailable"}
        }
      }
    },
    "/api/v0/status/index": {
      "get": {
        "tags": ["status"],
        "summary": "Get index status",
        "description": "Returns the index status summary.",
        "operationId": "getIndexStatus",
        "responses": {
          "200": {
            "description": "Index status",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "status": {"type": "string"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "repository_count": {"type": "integer"},
                    "queue": {"type": "object"},
                    "scope_activity": {"type": "object"}
                  }
                }
              }
            }
          },
          "500": {"$ref": "#/components/responses/InternalError"},
          "503": {"$ref": "#/components/responses/ServiceUnavailable"}
        }
      }
    },
    "/api/v0/compare/environments": {
      "post": {
        "tags": ["compare"],
        "summary": "Compare environments",
        "description": "Compares a workload deployment across two environments.",
        "operationId": "compareEnvironments",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["workload_id", "left", "right"],
                "properties": {
                  "workload_id": {"type": "string"},
                  "left": {"type": "string", "description": "Left environment name"},
                  "right": {"type": "string", "description": "Right environment name"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Environment comparison",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "workload": {"type": "object"},
                    "left": {"type": "object"},
                    "right": {"type": "object"},
                    "changed": {"type": "object"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"}
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
    "/api/v0/openapi.json": {
      "get": {
        "tags": ["health"],
        "summary": "OpenAPI specification",
        "description": "Returns the OpenAPI 3.0 specification for this API.",
        "operationId": "getOpenAPISpec",
        "responses": {
          "200": {
            "description": "OpenAPI specification",
            "content": {
              "application/json": {
                "schema": {"type": "object"}
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "parameters": {
      "RepoId": {
        "name": "repo_id",
        "in": "path",
        "required": true,
        "schema": {"type": "string"},
        "description": "Repository ID"
      },
      "EntityId": {
        "name": "entity_id",
        "in": "path",
        "required": true,
        "schema": {"type": "string"},
        "description": "Entity ID"
      },
      "WorkloadId": {
        "name": "workload_id",
        "in": "path",
        "required": true,
        "schema": {"type": "string"},
        "description": "Workload ID"
      },
      "ServiceName": {
        "name": "service_name",
        "in": "path",
        "required": true,
        "schema": {"type": "string"},
        "description": "Service name"
      }
    },
    "schemas": {
      "Repository": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "path": {"type": "string"},
          "local_path": {"type": "string"},
          "remote_url": {"type": "string"},
          "repo_slug": {"type": "string"},
          "has_remote": {"type": "boolean"},
          "is_dependency": {"type": "boolean"}
        }
      },
      "RepositoryRef": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "path": {"type": "string"},
          "remote_url": {"type": "string"},
          "has_remote": {"type": "boolean"}
        }
      },
      "EntityRef": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "labels": {"type": "array", "items": {"type": "string"}},
          "file_path": {"type": "string"},
          "repo_id": {"type": "string"},
          "repo_name": {"type": "string"}
        }
      },
      "Relationship": {
        "type": "object",
        "properties": {
          "type": {"type": "string"},
          "target_name": {"type": "string"},
          "target_id": {"type": "string"},
          "source_name": {"type": "string"},
          "source_id": {"type": "string"},
          "confidence": {"type": "number"},
          "reason": {"type": "string"}
        }
      },
      "WorkloadContext": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "kind": {"type": "string"},
          "repo_id": {"type": "string"},
          "repo_name": {"type": "string"},
          "instances": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "instance_id": {"type": "string"},
                "platform_name": {"type": "string"},
                "platform_kind": {"type": "string"},
                "environment": {"type": "string"}
              }
            }
          }
        }
      },
      "ErrorResponse": {
        "type": "object",
        "properties": {
          "error": {"type": "string"},
          "detail": {"type": "string"}
        }
      }
    },
    "responses": {
      "BadRequest": {
        "description": "Bad request",
        "content": {
          "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
          }
        }
      },
      "NotFound": {
        "description": "Resource not found",
        "content": {
          "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
          }
        }
      },
      "InternalError": {
        "description": "Internal server error",
        "content": {
          "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
          }
        }
      },
      "ServiceUnavailable": {
        "description": "Service unavailable",
        "content": {
          "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
          }
        }
      }
    }
  }
}`

// ServeOpenAPI returns an HTTP handler that serves the OpenAPI spec.
func ServeOpenAPI(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(OpenAPISpec))
}
