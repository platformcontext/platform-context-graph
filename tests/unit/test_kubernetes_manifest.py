from __future__ import annotations

from platform_context_graph.kubernetes_manifest import (
    extract_container_images,
    parse_k8s_resource,
)


def test_extract_container_images_reads_cronjob_template() -> None:
    """CronJob manifests should surface both container and init images."""

    doc = {
        "spec": {
            "jobTemplate": {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"image": "ghcr.io/example/app:1.2.3"}],
                            "initContainers": [{"image": "busybox:1.36"}],
                        }
                    }
                }
            }
        }
    }

    assert extract_container_images(doc) == [
        "ghcr.io/example/app:1.2.3",
        "busybox:1.36",
    ]


def test_parse_k8s_resource_captures_http_route_backends() -> None:
    """HTTPRoute resources should preserve backend references in metadata."""

    doc = {
        "spec": {
            "rules": [
                {
                    "backendRefs": [
                        {"name": "api-service"},
                        {"name": "worker-service"},
                    ]
                }
            ]
        }
    }

    parsed = parse_k8s_resource(
        doc,
        metadata={"name": "public-route", "namespace": "default"},
        api_version="gateway.networking.k8s.io/v1",
        kind="HTTPRoute",
        path="deploy/public-route.yaml",
        line_number=7,
        language_name="yaml",
    )

    assert parsed["name"] == "public-route"
    assert parsed["backend_refs"] == "api-service,worker-service"
