package query

const openAPISpecPrefix = `{
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
    {"name": "admin", "description": "Administrative control and inspection routes"},
    {"name": "status", "description": "Pipeline and ingester status"},
    {"name": "compare", "description": "Environment comparison"}
  ],
  "paths": {
`
