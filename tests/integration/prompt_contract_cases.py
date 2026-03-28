from __future__ import annotations

REPO_ID = "repository:r_api_node_boats"
HELM_REPO_ID = "repository:r_helm_charts"
RESOLVED_REPO_ID = "repository:r_20871f7f"
WORKLOAD_ID = "workload:api-node-boats"
PAYMENTS_REPO_ID = "repository:r_ab12cd34"


STORY_PROMPT_CASES = [
    {
        "prompt": "What can you tell me about api-node-boats: API endpoints, DNS, AWS resources it depends on, what environments it is deployed to, what repos it depends on, and what Terraform or IaC repos are related to it? I want the end-to-end flow from Internet to cloud to code.",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
        "expected_story_section_ids": ["internet", "deployment"],
    },
    {
        "prompt": "Show me the Internet-to-code request path for api-node-boats in QA, from DNS and gateway routing down to the service, container, and code entrypoints.",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats", "environment": "qa"},
        },
        "http": {
            "method": "GET",
            "path": f"/api/v0/services/{WORKLOAD_ID}/story",
            "params": {"environment": "qa"},
        },
    },
    {
        "prompt": "Where is api-node-boats deployed today, and how does QA differ from production in runtime, cluster, account, region, and deployment source?",
        "mcp": {
            "tool_name": "get_workload_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/workloads/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "What AWS resources does api-node-boats depend on, which ones are direct versus shared, and where in IaC are those dependencies declared?",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/services/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "Show me every public or internal hostname and API endpoint associated with api-node-boats, and tell me which repo and code path owns each one.",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
    {
        "prompt": "If api-node-boats is down in QA, walk me through the most likely failure points from DNS to gateway to workload to config to code.",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats", "environment": "qa"},
        },
        "http": {
            "method": "GET",
            "path": f"/api/v0/services/{WORKLOAD_ID}/story",
            "params": {"environment": "qa"},
        },
    },
    {
        "prompt": "If I change helm-charts for api-node-boats, what services, environments, and infrastructure components could be affected?",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "helm-charts"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{HELM_REPO_ID}/story"},
    },
    {
        "prompt": "If I change api-node-boats itself, who consumes it directly or transitively, and what is the likely change surface?",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
    {
        "prompt": "Resolve repository:r_20871f7f to a repo name and explain what role that repo plays in the deployment or dependency chain for api-node-boats.",
        "mcp": {
            "tool_name": "get_repo_story",
            "args": {"repo_id": "repository:r_20871f7f"},
        },
        "http": {
            "method": "GET",
            "path": f"/api/v0/repositories/{RESOLVED_REPO_ID}/story",
        },
    },
    {
        "prompt": "Which IaC repositories are related to api-node-boats, and what exactly does each one own: ArgoCD, Helm, Terraform, Crossplane, or cluster/platform setup?",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
    {
        "prompt": "Show me all environment overlays and config sources for api-node-boats, and infer whether each environment runs on EKS, ECS, or something else.",
        "mcp": {
            "tool_name": "get_workload_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/workloads/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "What AWS accounts, regions, clusters, and namespaces does api-node-boats run in, and what files prove that?",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/services/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "What secrets, SSM paths, IAM roles, or policy grants does api-node-boats rely on, and where are those permissions defined?",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/services/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "What container image does api-node-boats run, where is it built, how is it versioned, and what deploys that image into each environment?",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/services/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "Given the domain api-node-boats.qa.bgrp.io, what service owns it, how does traffic route, and what code repository is ultimately behind it?",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats", "environment": "qa"},
        },
        "http": {
            "method": "GET",
            "path": f"/api/v0/services/{WORKLOAD_ID}/story",
            "params": {"environment": "qa"},
        },
    },
    {
        "prompt": "Given this cloud resource or ARN, tell me which workload depends on it, what environment it belongs to, and which repos define or consume it.",
        "mcp": {
            "tool_name": "get_service_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/services/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "Compare api-node-boats and api-node-boattrader: shared dependencies, shared infrastructure, shared IaC repos, and key deployment differences.",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
    {
        "prompt": "Create onboarding documentation for api-node-boats: what it does, how it is exposed, where it runs, what it depends on, who consumes it, and which repos matter.",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
    {
        "prompt": "Why is api-node-boats on EKS in QA but ECS in production, and what evidence supports that conclusion?",
        "mcp": {
            "tool_name": "get_workload_story",
            "args": {"workload_id": "api-node-boats"},
        },
        "http": {"method": "GET", "path": f"/api/v0/workloads/{WORKLOAD_ID}/story"},
    },
    {
        "prompt": "Show me the full deployment chain for api-node-boats, but keep it focused on only directly relevant repos, resources, and files instead of every shared module in the ecosystem.",
        "mcp": {"tool_name": "get_repo_story", "args": {"repo_id": "api-node-boats"}},
        "http": {"method": "GET", "path": f"/api/v0/repositories/{REPO_ID}/story"},
    },
]


PROGRAMMING_PROMPT_CASES = [
    {
        "prompt": "Where is process_payment defined?",
        "mcp": {"tool_name": "find_code", "args": {"query": "process_payment"}},
        "http": {
            "method": "POST",
            "path": "/api/v0/code/search",
            "json": {"query": "process_payment"},
        },
        "kind": "search",
        "round_trip": True,
    },
    {
        "prompt": "Who calls process_payment?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_callers", "target": "process_payment"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_callers", "target": "process_payment"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "What does process_payment call?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_callees", "target": "process_payment"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_callees", "target": "process_payment"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Find all indirect callers of normalize_config.",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_all_callers", "target": "normalize_config"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_all_callers", "target": "normalize_config"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Find all indirect callees from handleRequest.",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_all_callees", "target": "handleRequest"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_all_callees", "target": "handleRequest"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Find the call chain from main to process_payment.",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "call_chain", "target": "main -> process_payment"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "call_chain", "target": "main -> process_payment"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Which files import requests?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_importers", "target": "requests"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_importers", "target": "requests"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Show the class hierarchy for Employee.",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "class_hierarchy", "target": "Employee"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "class_hierarchy", "target": "Employee"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "What methods does Employee have?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "class_hierarchy", "target": "Employee"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "class_hierarchy", "target": "Employee"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Find implementations of render.",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "overrides", "target": "render"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "overrides", "target": "render"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Which functions take user_id?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "find_functions_by_argument", "target": "user_id"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "find_functions_by_argument", "target": "user_id"},
        },
        "kind": "relationships",
    },
    {
        "prompt": "Which functions are decorated with @app.route?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {
                "query_type": "find_functions_by_decorator",
                "target": "@app.route",
            },
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {
                "query_type": "find_functions_by_decorator",
                "target": "@app.route",
            },
        },
        "kind": "relationships",
    },
    {
        "prompt": "What is the complexity of process_payment in src/payments.py?",
        "mcp": {
            "tool_name": "calculate_cyclomatic_complexity",
            "args": {"function_name": "process_payment", "path": "src/payments.py"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/complexity",
            "json": {
                "mode": "function",
                "function_name": "process_payment",
                "path": "src/payments.py",
            },
        },
        "kind": "complexity_function",
    },
    {
        "prompt": "Show the most complex functions in payments-api.",
        "mcp": {
            "tool_name": "find_most_complex_functions",
            "args": {"repo_id": PAYMENTS_REPO_ID, "limit": 10, "scope": "repo"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/complexity",
            "json": {
                "mode": "top",
                "repo_id": PAYMENTS_REPO_ID,
                "limit": 10,
                "scope": "repo",
            },
        },
        "kind": "complexity_top",
    },
    {
        "prompt": "Find dead code in this repo.",
        "mcp": {
            "tool_name": "find_dead_code",
            "args": {"repo_id": PAYMENTS_REPO_ID, "scope": "repo"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/dead-code",
            "json": {"repo_id": PAYMENTS_REPO_ID, "scope": "repo"},
        },
        "kind": "dead_code",
    },
    {
        "prompt": "Where is API_KEY modified?",
        "mcp": {
            "tool_name": "analyze_code_relationships",
            "args": {"query_type": "who_modifies", "target": "API_KEY"},
        },
        "http": {
            "method": "POST",
            "path": "/api/v0/code/relationships",
            "json": {"query_type": "who_modifies", "target": "API_KEY"},
        },
        "kind": "relationships",
    },
]
