# MCP Reference & Natural Language Queries

This page lists all available **MCP Tools** that your AI assistant (Cursor, Claude, VS Code) can use.

When you ask a question in natural language, the AI selects one of these tools behind the scenes.

For documentation-oriented answers, use a simple orchestration rule:

- start with story or context when the user wants explanation, onboarding, support guidance, or deployment narrative
- use content reads and content search after the story identifies the exact artifacts worth citing
- keep all file-shaped answers portable through `repo_id + relative_path` or `entity_id`
- when the answer spans multiple repos, tell PCG to scan all related repositories, deployment sources, and indexed documentation first

Repository-bearing results may include `repo_access` metadata. If PCG is running remotely, treat repository identity as remote-first and use `repo_id`, `repo_slug`, and repo-relative paths before assuming any `local_path` exists on the user's machine.

Content-oriented tools use the same rule:

- file lookup uses `repo_id + relative_path`
- entity lookup uses `entity_id`
- deployed MCP/API runtimes prefer the PostgreSQL content store and report `unavailable` when a row is not yet indexed
- local helper flows may still use workspace or graph-cache fallbacks
- file and entity read responses include `source_backend` so the client can see whether PCG answered from `postgres`, `workspace`, `graph-cache`, or `unavailable`
- content search tools require the PostgreSQL content store and return an error when it is disabled
- `repo_access` prompting is only for workflows that truly need the user's local machine

Prompt-suite and docs examples should stay portable too:

- use `repo_id + relative_path` for file-shaped answers
- prefer structured query tools before `execute_cypher_query`
- treat raw Cypher as a manual diagnostic tool, not a fallback path for prompt coverage
- avoid teaching prompt tests to depend on server-local filesystem paths

!!! tip "File Exclusion"
    You can control what gets indexed using `.pcgignore`.
    [**📄 Read the Guide**](pcgignore.md)

## Core Analysis Tools

These are the most commonly used tools for understanding code.

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`find_code`** | Search for code by name or fuzzy text. | "Where is the `User` class defined?" |
| **`analyze_code_relationships`** | The swiss-army knife for call graphs and dependencies. | "Find all callers of `process_payment`." |
| **`calculate_cyclomatic_complexity`** | Measure function complexity. | "What is the complexity of `main`?" |
| **`find_most_complex_functions`** | List the hardest-to-maintain functions. | "Show me the 5 most complex functions." |
| **`find_dead_code`** | Identify unused functions, optionally scoped by canonical `repo_id`. | "Find dead code in this repo, but ignore `@route`." |

## Story & Context

Use these tools when the user is asking for a narrative answer such as
"Internet to cloud to code" or "tell me everything about this service."

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`get_repo_story`** | Return a structured repository story with `subject`, `story`, `story_sections`, evidence-oriented overviews, limitations, coverage, and drill-down handles. Accepts a canonical repository ID or a plain repository name/slug. | "Tell me the end-to-end story for payments-api." |
| **`get_workload_story`** | Return a structured workload story using canonical workload identity, optionally scoped to one environment. Story payloads may include `gitops_overview`, `documentation_overview`, and `support_overview` when evidence exists. | "Show me how payments-api is deployed in prod." |
| **`get_service_story`** | Service alias wrapper around workload story for service-shaped prompts. This is the preferred first hop for support, onboarding, and service-explainer prompts. | "What can you tell me about payments-api in QA?" |
| **`investigate_service`** | Orchestrated service investigation that widens across related repos, evidence families, and deployment planes, then reports coverage and recommended next calls. | "Explain the deployment flow for api-node-boats using PCG only." |
| **`get_repo_context`** | Durable drill-down for repository details after the story answer. | "Show me the full repo context behind that story." |
| **`get_workload_context`** | Durable drill-down for workload details after the story answer. | "Show me the workload context behind that story." |
| **`get_service_context`** | Service alias drill-down for service-shaped prompts. | "Show me the service context behind that story." |

Story responses may now include deployment-mapping fields alongside the narrative:

- `controller_overview`
- `runtime_overview`
- `deployment_facts`
- `deployment_fact_summary`

`deployment_facts` are normalized, evidence-backed facts such as:

- `MANAGED_BY_CONTROLLER`
- `PROVISIONED_BY_IAC`
- `USES_PACKAGING_LAYER`
- `DEPLOYS_FROM`
- `DISCOVERS_CONFIG_IN`
- `RUNS_ON_PLATFORM`
- `OBSERVED_IN_ENVIRONMENT`
- `EXPOSES_ENTRYPOINT`
- `DELIVERY_PATH_PRESENT`

`deployment_fact_summary` is the compact interpretation layer:

- `mapping_mode=controller` means explicit controller evidence was found
- `mapping_mode=iac` means explicit infrastructure-as-code evidence was found
- `mapping_mode=evidence_only` means only delivery/runtime evidence was found, and PCG intentionally avoided guessing a controller family
- `mapping_mode=none` means the indexed context is too sparse to map deployment evidence truthfully yet
- `overall_confidence_reason` explains the reason code behind the top-level confidence
- `fact_thresholds` maps each emitted fact type to a stable threshold code
- `limitations` uses stable deployment-mapping limitation codes

Current threshold-code examples:

- `explicit_iac_adapter`
- `explicit_controller_signal`
- `explicit_packaging_signal`
- `explicit_automation_signal`
- `named_deployment_source`
- `named_config_source`
- `explicit_platform_match`
- `explicit_environment_evidence`
- `named_entrypoint`
- `delivery_path_present`

This keeps the contract portable across ArgoCD, Flux, Terraform, CloudFormation, plain Kubernetes manifests, ECS, Lambda, and environments that do not use a controller at all.

`investigate_service` is the new investigation-first companion to the story
tools.

Use it when:

- the user asks a normal operator question and should not need prompt engineering
- you want PCG to widen into deployment-adjacent repos automatically
- you need explicit coverage reporting and recommended next calls

The main output fields are:

- `repositories_considered`
- `repositories_with_evidence`
- `evidence_families_found`
- `coverage_summary`
- `investigation_findings`
- `recommended_next_calls`

## Content Retrieval & Search

Tools for portable source retrieval and indexed content search.

Use these after story or context determines which files, snippets, or docs matter most.

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`get_file_content`** | Read a file using `repo_id + relative_path`. | "Show me `src/payments.py` from the payments repo." |
| **`get_file_lines`** | Read a specific line range from one repo-relative file. | "Show me lines 20 to 40 from `src/server.py`." |
| **`get_entity_content`** | Read source for one content-bearing entity using its canonical `entity_id`. | "Show me the source for this resolved function." |
| **`search_file_content`** | Search indexed file text through the content store. | "Find every file that mentions `shared-payments-prod`." |
| **`search_entity_content`** | Search cached entity snippets through the content store. | "Find entities whose source mentions `process_payment`." |

## System & Management

Tools for managing the graph and background jobs.

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`monitor_directory`** | Start monitoring a folder (Alias: `watch_directory`)| "Watch the `src` folder." |
| **`list_watched_paths`** | See what is being monitored. | "What directories are being watched?" |
| **`unwatch_directory`** | Stop monitoring a folder. | "Stop watching `src`." |
| **`list_indexed_repositories`** | Show what projects are currently indexed. | "What repos are indexed?" |
| **`get_repository_stats`** | Show counts of files, classes, LOC. | "Show stats for the backend repo." |
| **`delete_repository`** | Remove a repo from the graph. | "Remove the frontend repo." |
| **`add_code_to_graph`** | Manually add a specific path. | "Add the `lib` folder." |
| **`add_package_to_graph`** | Index an external library/package. | "Add the `requests` library." |

## Ingester Runtime

Tools for inspecting the status of the deployed ingester runtimes.

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`list_ingesters`** | Show the latest persisted status for all configured ingesters. | "What ingesters are configured and what state are they in?" |
| **`get_ingester_status`** | Show detailed status for one ingester runtime, including retry timing and repo progress counts. | "What is the repository ingester doing right now?" |

## Job Control

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`list_jobs`** | View all background tasks. | "Show me active jobs." |
| **`check_job_status`** | Check if a specific job is done. | "Is job `xyz` finished?" |

## Bundles & Registry

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`search_registry_bundles`** | Find shared graphs in the cloud. | "Search for a `flask` bundle." |
| **`load_bundle`** | Install a graph bundle. | "Load the `flask` bundle." |

## Advanced Querying

For complex questions that standard tools can't answer.

| Tool Name | Description | Natural Language Example |
| :--- | :--- | :--- |
| **`execute_cypher_query`** | Run a raw read-only database query. | "Find all recursive functions." |
| **`visualize_graph_query`** | Generate a Neo4j Browser link for a query. | "Visualize the class hierarchy of `BaseModel`." |

---

## Example Queries (Cookbook)

For a deep dive into exactly how to phrase questions and what JSON arguments look like, check out the Cookbook.

[📖 View the MCP Cookbook](mcp-cookbook.md)
