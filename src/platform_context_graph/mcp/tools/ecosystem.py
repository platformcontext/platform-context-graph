"""Tool definitions for ecosystem, infrastructure, and impact analysis workflows."""

ECOSYSTEM_TOOLS = {
    "index_ecosystem": {
        "name": "index_ecosystem",
        "description": "Index all repositories in an ecosystem manifest (dependency-graph.yaml). Creates a unified graph across all repos with cross-repo relationships. Supports incremental updates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "manifest_path": {
                    "type": "string",
                    "description": "Path to the ecosystem dependency-graph.yaml manifest file.",
                },
                "base_path": {
                    "type": "string",
                    "description": "Base directory where repos are cloned locally.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force re-index all repos regardless of state.",
                    "default": False,
                },
                "parallel": {
                    "type": "integer",
                    "description": "Max concurrent repo indexing.",
                    "default": 4,
                },
                "clone_missing": {
                    "type": "boolean",
                    "description": "Clone missing repos via gh CLI.",
                    "default": False,
                },
            },
            "required": ["manifest_path", "base_path"],
        },
    },
    "ecosystem_status": {
        "name": "ecosystem_status",
        "description": "Show the indexing status of all repos in the ecosystem. Shows which repos are indexed, stale, or failed.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "get_ecosystem_overview": {
        "name": "get_ecosystem_overview",
        "description": "Get a high-level overview of the indexed ecosystem: repos, tiers, infrastructure counts, and cross-repo relationships. Use this instead of reading dependency-graph.yaml and browsing 20 repos.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "trace_resource_to_code": {
        "name": "trace_resource_to_code",
        "description": "Trace an infrastructure resource back to the code and repositories that own or configure it. Prefer environment-specific instance edges when environment is provided.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Canonical entity id for the starting resource.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to prefer when resolving workload instances.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum traversal depth.",
                    "default": 8,
                },
            },
            "required": ["start"],
        },
    },
    "explain_dependency_path": {
        "name": "explain_dependency_path",
        "description": "Explain the dependency path between two canonical entities with confidence, reason, and evidence for each hop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Canonical entity id for the source entity.",
                },
                "target": {
                    "type": "string",
                    "description": "Canonical entity id for the target entity.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to prefer when resolving workload instances.",
                },
            },
            "required": ["source", "target"],
        },
    },
    "find_change_surface": {
        "name": "find_change_surface",
        "description": "Find the blast or change surface for a workload, cloud resource, or terraform module. Returns impacted entities with evidence and confidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Canonical entity id to analyze.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to prefer when resolving workload instances.",
                },
            },
            "required": ["target"],
        },
    },
    "compare_environments": {
        "name": "compare_environments",
        "description": "Compare the dependency surface for a workload across two environments and report changed resources and impacted surfaces.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workload_id": {
                    "type": "string",
                    "description": "Canonical workload id to compare.",
                },
                "left": {"type": "string", "description": "Left environment name."},
                "right": {"type": "string", "description": "Right environment name."},
            },
            "required": ["workload_id", "left", "right"],
        },
    },
    "trace_deployment_chain": {
        "name": "trace_deployment_chain",
        "description": "Trace the full deployment chain for a service across ArgoCD Applications and ApplicationSets, then surface the related K8s, Crossplane, and Terraform resources. Start with the top-level `story` field for the concise deployment narrative, then use `deployment_overview` and the detailed fields for drill-down. Useful for incident investigation and impact analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service/repository to trace.",
                },
                "direct_only": {
                    "type": "boolean",
                    "description": "Keep the trace focused on direct deployment evidence by default.",
                    "default": True,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Optional maximum depth for retained trace branches.",
                },
                "include_related_module_usage": {
                    "type": "boolean",
                    "description": "Include related Terraform module usage even when it is not direct service evidence.",
                    "default": False,
                },
            },
            "required": ["service_name"],
        },
    },
    "find_blast_radius": {
        "name": "find_blast_radius",
        "description": "Find all repos and resources affected by changing a target. Graph traversal of transitive dependencies to assess impact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Name of the target to analyze.",
                },
                "target_type": {
                    "type": "string",
                    "description": "Type of target.",
                    "enum": ["repository", "terraform_module", "crossplane_xrd"],
                    "default": "repository",
                },
            },
            "required": ["target"],
        },
    },
    "find_infra_resources": {
        "name": "find_infra_resources",
        "description": "Search infrastructure resources (K8s, Terraform, ArgoCD, Crossplane, Helm) by name or type across all indexed repos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for resource name or type.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional filter.",
                    "enum": ["k8s", "terraform", "argocd", "crossplane", "helm"],
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
    "analyze_infra_relationships": {
        "name": "analyze_infra_relationships",
        "description": "Analyze infrastructure relationships: what deploys what, what provisions what, who consumes this XRD, what uses this Terraform module.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "description": "Type of relationship query.",
                    "enum": [
                        "what_deploys",
                        "what_provisions",
                        "who_consumes_xrd",
                        "module_consumers",
                    ],
                },
                "target": {
                    "type": "string",
                    "description": "Name of the target resource to analyze.",
                },
            },
            "required": ["query_type", "target"],
        },
    },
    "get_repo_summary": {
        "name": "get_repo_summary",
        "description": "Get a structured summary of a repository: files, code entities, infrastructure resources, canonical platform/runtime relationships, deploy/config sources, ecosystem connections, dependencies, environments, tier info, repository coverage, and stable limitation codes. Start with the top-level `story` field for the concise repo and deployment narrative, then use `deployment_overview` and the detailed fields for drill-down. If completeness_state is not complete, report the missing graph/content coverage and any limitation codes instead of implying those files or entities do not exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Name of the repository.",
                }
            },
            "required": ["repo_name"],
        },
    },
    "get_repo_context": {
        "name": "get_repo_context",
        "description": "Get complete context for a repository in a single call: recursive file counts, code entities, infrastructure resources, canonical platform/runtime relationships, deployment chains, ecosystem info, and a concise coverage summary with stable limitation codes. Accepts either a canonical repository ID or a plain repository name/slug. If completeness_state is not complete, report the missing coverage instead of implying the repo lacks those files or entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Canonical repository identifier or plain repository name.",
                }
            },
            "required": ["repo_id"],
        },
    },
    "get_repo_story": {
        "name": "get_repo_story",
        "description": "Get a structured story for a repository: subject, story lines, story sections, deployment or code overviews, evidence, limitations, coverage, and drill-down handles. Accepts either a canonical repository ID or a plain repository name/slug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Canonical repository identifier or plain repository name.",
                }
            },
            "required": ["repo_id"],
        },
    },
    "get_repository_coverage": {
        "name": "get_repository_coverage",
        "description": "Get durable per-run coverage and completeness data for one canonical repository identifier, including discovered-vs-graph and graph-vs-content gap counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Canonical repository identifier.",
                },
                "run_id": {
                    "type": "string",
                    "description": "Optional checkpoint run identifier. Defaults to the latest row for the repository.",
                },
            },
            "required": ["repo_id"],
        },
    },
    "list_repository_coverage": {
        "name": "list_repository_coverage",
        "description": "List durable repository coverage rows for one run or across runs, including incomplete repositories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Optional checkpoint run identifier to scope the listing.",
                },
                "only_incomplete": {
                    "type": "boolean",
                    "description": "If true, only return repositories that are not fully completed.",
                    "default": False,
                },
                "statuses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional explicit repository-status filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return.",
                    "default": 100,
                },
            },
        },
    },
}

__all__ = ["ECOSYSTEM_TOOLS"]
