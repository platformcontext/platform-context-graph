"""Static OpenAPI examples for the API schema."""

from __future__ import annotations

WORKLOAD_CONTEXT_EXAMPLE = {
    "workload": {
        "id": "workload:payments-api",
        "type": "workload",
        "kind": "service",
        "name": "payments-api",
    },
    "instance": {
        "id": "workload-instance:payments-api:prod",
        "type": "workload_instance",
        "kind": "service",
        "name": "payments-api",
        "environment": "prod",
        "workload_id": "workload:payments-api",
    },
    "repositories": [
        {
            "id": "repository:r_ab12cd34",
            "type": "repository",
            "name": "payments-api",
            "repo_slug": "platformcontext/payments-api",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "has_remote": True,
        }
    ],
    "images": [],
    "instances": [],
    "k8s_resources": [],
    "cloud_resources": [],
    "shared_resources": [],
    "dependencies": [],
    "entrypoints": [],
    "evidence": [],
}
SERVICE_CONTEXT_EXAMPLE = {
    **WORKLOAD_CONTEXT_EXAMPLE,
    "requested_as": "service",
}
WORKLOAD_STORY_EXAMPLE = {
    "subject": WORKLOAD_CONTEXT_EXAMPLE["workload"],
    "story": [
        "payments-api has an environment-scoped instance for prod.",
        "Owned by repositories payments-api.",
    ],
    "story_sections": [
        {
            "id": "runtime",
            "title": "Runtime",
            "summary": "Selected instance workload-instance:payments-api:prod.",
            "items": [WORKLOAD_CONTEXT_EXAMPLE["instance"]],
        }
    ],
    "deployment_overview": {
        "instances": [WORKLOAD_CONTEXT_EXAMPLE["instance"]],
        "repositories": WORKLOAD_CONTEXT_EXAMPLE["repositories"],
        "entrypoints": [],
        "cloud_resources": [],
        "shared_resources": [],
        "dependencies": [],
    },
    "gitops_overview": {
        "owner": {
            "source_repositories": [],
            "delivery_controllers": [],
            "workflow_families": [],
        },
        "environment": {
            "selected": "prod",
            "declared": ["prod"],
            "observed_config": [],
        },
        "chart": {"charts": [], "images": [], "service_ports": []},
        "value_layers": [],
        "rendered_resources": [],
        "supporting_resources": [],
        "limitations": [],
    },
    "documentation_overview": {
        "audiences": [
            "engineering",
            "service-owner",
            "platform-engineering",
            "support",
        ],
        "service_summary": "payments-api is a deployable service story backed by payments-api.",
        "code_summary": "Code detail should be drilled into through repository and content reads.",
        "deployment_summary": "GitOps and deployment drilldowns provide the supporting evidence.",
        "key_artifacts": [],
        "recommended_drilldowns": [
            {
                "tool": "workload_context",
                "args": {"workload_id": "workload:payments-api"},
            }
        ],
        "documentation_evidence": {
            "graph_context": [],
            "file_content": [],
            "entity_content": [],
            "content_search": [],
        },
        "limitations": [
            "postgres_file_evidence_missing",
            "content_search_evidence_missing",
        ],
    },
    "support_overview": {
        "runtime_components": [WORKLOAD_CONTEXT_EXAMPLE["instance"]],
        "entrypoints": [],
        "dependency_hotspots": [],
        "investigation_paths": [],
        "key_artifacts": [],
        "limitations": ["support_artifacts_missing"],
    },
    "deployment_fact_summary": {
        "adapter": "cloudformation",
        "mapping_mode": "iac",
        "overall_confidence": "high",
        "overall_confidence_reason": "explicit_iac_adapter",
        "evidence_sources": ["delivery_path", "platform"],
        "high_confidence_fact_types": [
            "PROVISIONED_BY_IAC",
            "RUNS_ON_PLATFORM",
        ],
        "medium_confidence_fact_types": [],
        "fact_thresholds": {
            "PROVISIONED_BY_IAC": "explicit_iac_adapter",
            "RUNS_ON_PLATFORM": "explicit_platform_match",
        },
        "limitations": [],
    },
    "deployment_facts": [
        {
            "fact_type": "PROVISIONED_BY_IAC",
            "adapter": "cloudformation",
            "value": "cloudformation",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": "cloudformation_eks",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "cloudformation",
            "value": "eks",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "eks",
                    "environment": "prod",
                }
            ],
        },
    ],
    "evidence": [],
    "limitations": [],
    "coverage": None,
    "drilldowns": {
        "workload_context": {"workload_id": "workload:payments-api"},
        "service_context": {"workload_id": "workload:payments-api"},
    },
}
SERVICE_STORY_EXAMPLE = {
    **WORKLOAD_STORY_EXAMPLE,
    "deployment_fact_summary": {
        "adapter": "unknown",
        "mapping_mode": "none",
        "overall_confidence": "low",
        "overall_confidence_reason": "no_deployment_evidence",
        "evidence_sources": [],
        "high_confidence_fact_types": [],
        "medium_confidence_fact_types": [],
        "fact_thresholds": {},
        "limitations": [
            "deployment_evidence_missing",
            "deployment_source_unknown",
            "runtime_platform_unknown",
            "environment_unknown",
            "entrypoint_unknown",
        ],
    },
    "deployment_facts": [],
    "requested_as": "service",
}
REPOSITORY_STORY_EXAMPLE = {
    "subject": {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
    },
    "story": [
        "Public entrypoints: payments-api.prod.example.com.",
        "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
    ],
    "story_sections": [
        {
            "id": "deployment",
            "title": "Deployment",
            "summary": "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
            "items": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
        }
    ],
    "deployment_overview": {
        "internet_entrypoints": ["payments-api.prod.example.com"],
        "internal_entrypoints": [],
        "api_surface": {"docs_routes": ["/_specs"], "api_versions": ["v1"]},
        "runtime_platforms": [{"kind": "eks"}],
        "delivery_paths": [
            {
                "path_kind": "gitops",
                "controller": "github_actions",
                "delivery_mode": "eks_gitops",
                "deployment_sources": ["helm-charts"],
                "platform_kinds": ["eks"],
            }
        ],
        "controller_driven_paths": [],
        "consumer_repositories": [],
        "deployment_story": [
            "Public entrypoints: payments-api.prod.example.com.",
            "API surface exposes versions v1 and docs /_specs.",
            "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
        ],
        "topology_story": [
            "Public entrypoints: payments-api.prod.example.com.",
            "API surface exposes versions v1 and docs /_specs.",
            "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
        ],
    },
    "gitops_overview": {
        "owner": {
            "source_repositories": [{"name": "helm-charts"}],
            "delivery_controllers": ["github_actions"],
            "workflow_families": [],
        },
        "environment": {
            "selected": None,
            "declared": ["prod"],
            "observed_config": ["prod"],
        },
        "chart": {"charts": [], "images": [], "service_ports": []},
        "value_layers": [
            {
                "relative_path": "argocd/payments-api/base/values.yaml",
                "source_repo": "helm-charts",
                "layer_kind": "base_values",
                "precedence": 0,
            }
        ],
        "rendered_resources": [],
        "supporting_resources": [],
        "limitations": [],
    },
    "documentation_overview": {
        "audiences": [
            "engineering",
            "service-owner",
            "platform-engineering",
            "support",
        ],
        "service_summary": "payments-api is a repository story backed by payments-api.",
        "code_summary": "Code context includes 12 functions, 3 classes, and 42 discovered files.",
        "deployment_summary": "Entry points include payments-api.prod.example.com. GitOps delivery uses github_actions.",
        "key_artifacts": [
            {
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "README.md",
                "source_backend": "postgres",
                "reason": "Service overview and debugging notes.",
            }
        ],
        "recommended_drilldowns": [
            {"tool": "repo_context", "args": {"repo_id": "repository:r_ab12cd34"}},
            {"tool": "repo_summary", "args": {"repo_id": "repository:r_ab12cd34"}},
            {"tool": "deployment_chain", "args": {"service_name": "payments-api"}},
        ],
        "documentation_evidence": {
            "graph_context": [
                {"kind": "entrypoint", "detail": "payments-api.prod.example.com"}
            ],
            "file_content": [
                {
                    "repo_id": "repository:r_ab12cd34",
                    "relative_path": "README.md",
                    "source_backend": "postgres",
                    "title": "Payments API",
                    "summary": "Service overview and debugging notes.",
                }
            ],
            "entity_content": [],
            "content_search": [],
        },
        "limitations": ["content_search_evidence_missing"],
    },
    "support_overview": {
        "runtime_components": [
            {
                "id": "repository:r_ab12cd34",
                "type": "repository",
                "name": "payments-api",
            }
        ],
        "entrypoints": [
            {
                "hostname": "payments-api.prod.example.com",
            }
        ],
        "dependency_hotspots": [],
        "investigation_paths": [
            {
                "topic": "request_failures",
                "summary": "Start with payments-api.prod.example.com and then confirm runtime and routing evidence.",
                "artifacts": [
                    {
                        "repo_id": "repository:r_ab12cd34",
                        "relative_path": "README.md",
                        "source_backend": "postgres",
                        "reason": "Service overview and debugging notes.",
                    }
                ],
            }
        ],
        "key_artifacts": [
            {
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "README.md",
                "source_backend": "postgres",
                "reason": "Service overview and debugging notes.",
            }
        ],
        "limitations": [],
    },
    "deployment_fact_summary": {
        "adapter": "github_actions",
        "mapping_mode": "controller",
        "overall_confidence": "medium",
        "overall_confidence_reason": "controller_delivery_signal",
        "evidence_sources": ["delivery_path"],
        "high_confidence_fact_types": [],
        "medium_confidence_fact_types": [
            "MANAGED_BY_CONTROLLER",
            "DEPLOYS_FROM",
        ],
        "fact_thresholds": {
            "MANAGED_BY_CONTROLLER": "explicit_controller_signal",
            "DEPLOYS_FROM": "named_deployment_source",
        },
        "limitations": [
            "config_source_unknown",
            "runtime_platform_unknown",
            "environment_unknown",
            "entrypoint_unknown",
        ],
    },
    "deployment_facts": [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "github_actions",
            "value": "github_actions",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "github_actions",
            "value": "helm-charts",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
    ],
    "code_overview": {
        "file_count": 42,
        "functions": 12,
        "classes": 3,
        "class_methods": 4,
    },
    "evidence": [{"source": "hostnames", "detail": "payments-api.prod.example.com"}],
    "limitations": [],
    "coverage": {"completeness_state": "complete"},
    "drilldowns": {
        "repo_context": {"repo_id": "repository:r_ab12cd34"},
        "repo_summary": {"repo_id": "repository:r_ab12cd34"},
        "deployment_chain": {"service_name": "payments-api"},
    },
}
RESOLVE_ENTITY_RESPONSE_EXAMPLE = {
    "matches": [
        {
            "ref": WORKLOAD_CONTEXT_EXAMPLE["workload"],
            "score": 0.98,
        }
    ]
}
CODE_SEARCH_REQUEST_EXAMPLE = {
    "query": "process_payment",
    "repo_id": "repository:r_ab12cd34",
    "exact": False,
    "limit": 10,
}
