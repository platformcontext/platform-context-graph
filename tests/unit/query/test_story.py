from __future__ import annotations

from platform_context_graph.query.story import (
    build_repository_story_response,
    build_workload_story_response,
)


def test_repository_story_subject_omits_server_local_checkout_paths() -> None:
    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_ab12cd34",
                "name": "payments-api",
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "local_path": "/srv/repos/payments-api",
                "path": "/srv/repos/payments-api",
                "has_remote": True,
            },
            "code": {"functions": 12, "classes": 3, "class_methods": 8},
        }
    )

    assert result["subject"] == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
        "repo_slug": "platformcontext/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "has_remote": True,
    }


def test_workload_story_omits_server_local_repo_paths_from_nested_items() -> None:
    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
            "repositories": [
                {
                    "id": "repository:r_ab12cd34",
                    "type": "repository",
                    "name": "payments-api",
                    "path": "/srv/repos/payments-api",
                    "local_path": "/srv/repos/payments-api",
                    "repo_slug": "platformcontext/payments-api",
                    "remote_url": "https://github.com/platformcontext/payments-api",
                    "has_remote": True,
                }
            ],
        }
    )

    repository = result["deployment_overview"]["repositories"][0]
    assert repository == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
        "repo_slug": "platformcontext/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "has_remote": True,
    }
