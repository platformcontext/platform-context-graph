# Architecture Documentation

This document provides a detailed overview of the architecture of the PlatformContextGraph project.

## High-Level Overview

PlatformContextGraph is a Python-first code-to-cloud graph system. It consists of:

*   **A shared graph and query backend:** Parses code and infrastructure, builds the graph, and serves read/query workflows.
*   **A command-line interface (CLI):** Local operator surface for indexing, analysis, setup, and runtime tasks.
*   **An MCP server:** JSON-RPC surface for AI tools and coding agents.
*   **An HTTP API:** OpenAPI-backed read/query surface for service and automation integrations.

## Backend Architecture

The backend is a Python application located in the `src/platform_context_graph` directory.

### Core Components

The `src/platform_context_graph/core` directory contains the fundamental building blocks of the backend:

*   **Database:** A graph database is used to store the code graph. This allows for efficient querying of relationships between code elements (e.g., function calls, class inheritance).
*   **Jobs:** Asynchronous jobs are used for long-running tasks like indexing a new codebase. This prevents the application from becoming unresponsive.
*   **Runtime Sync:** Bootstrap indexing and repo sync keep the deployable-service graph current.

### Tools

The `src/platform_context_graph/tools` directory contains the logic for code analysis:

*   **Graph Builder:** This component is responsible for parsing the code and building the graph representation that is stored in the database.
*   **Code Finder:** Provides functionality to search for specific code elements within the indexed codebase.
*   **Import Extractor:** This tool analyzes the import statements in the code to understand dependencies between modules.

### Server Surfaces

The backend exposes two transport-facing surfaces:

*   **MCP:** `src/platform_context_graph/mcp/server.py`
*   **HTTP API:** `src/platform_context_graph/api/app.py`

### CLI

The `src/platform_context_graph/cli` directory contains the implementation of the command-line interface. It allows users to:

*   Start and stop the backend server.
*   Index new projects.
*   Run analysis tools from the command line.

## Public Docs Surface

The repo does not ship a separate frontend application. Public product and
reference content lives in the MkDocs site under `docs/docs/`.

## Testing

The `tests/` directory contains the test suite for the project.

*   **Integration Tests:** The integration test suite verifies the interaction between different backend components.
*   **Unit Tests:** Other files in this directory contain unit tests for specific modules and functions.
*   **Sample Project:** The `tests/sample_project` directory contains a variety of Python files used as input for testing the code analysis tools.
