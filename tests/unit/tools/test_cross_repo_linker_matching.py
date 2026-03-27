"""Unit tests for cross-repository relationship matching."""

from __future__ import annotations

from types import SimpleNamespace

from platform_context_graph.tools.cross_repo_linker import CrossRepoLinker


class _FakeResult:
    """Minimal query result stub for linker tests."""

    def __init__(self, rows: list[dict[str, object]] | None = None, cnt: int = 0):
        self._rows = rows or []
        self._cnt = cnt

    def data(self) -> list[dict[str, object]]:
        return self._rows

    def single(self) -> dict[str, int]:
        return {"cnt": self._cnt}


class _FakeSession:
    """Context-managed fake Neo4j session."""

    def __init__(
        self,
        *,
        repository_rows: list[dict[str, object]],
        application_rows: list[dict[str, object]] | None = None,
        appset_rows: list[dict[str, object]] | None = None,
        module_rows: list[dict[str, object]] | None = None,
        terragrunt_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.repository_rows = repository_rows
        self.application_rows = application_rows or []
        self.appset_rows = appset_rows or []
        self.module_rows = module_rows or []
        self.terragrunt_rows = terragrunt_rows or []
        self.links: list[list[dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **params):
        if "RETURN repo.id as id" in query:
            return _FakeResult(self.repository_rows)
        if "RETURN app[$source_repo_key] as source_repo" in query:
            return _FakeResult(self.application_rows)
        if "RETURN app[$source_repos_key] as source_repos" in query:
            return _FakeResult(self.appset_rows)
        if "RETURN mod.source as source" in query:
            return _FakeResult(self.module_rows)
        if "RETURN tg[$terraform_source_key] as source" in query:
            return _FakeResult(self.terragrunt_rows)
        if "UNWIND $links AS link" in query:
            self.links.append(params["links"])
            return _FakeResult(cnt=len(params["links"]))
        raise AssertionError(f"Unexpected query: {query}")


def test_argocd_source_links_use_normalized_remote_url() -> None:
    """ArgoCD source refs should match by remote URL before falling back to name."""

    session = _FakeSession(
        repository_rows=[
            {
                "id": "repository:r_payments",
                "name": "payments-checkout",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "repo_slug": "platformcontext/payments-api",
            }
        ],
        application_rows=[
            {
                "source_repo": "git@github.com:platformcontext/payments-api.git",
            }
        ],
    )
    linker = CrossRepoLinker(
        SimpleNamespace(get_driver=lambda: SimpleNamespace(session=lambda: session))
    )

    count = linker._link_argocd_sources()

    assert count == 1
    assert session.links == [
        [
            {
                "source_repo": "git@github.com:platformcontext/payments-api.git",
                "repo_id": "repository:r_payments",
            }
        ]
    ]


def test_terraform_module_links_use_normalized_remote_url() -> None:
    """Terraform module refs should match by slug or remote URL before name."""

    session = _FakeSession(
        repository_rows=[
            {
                "id": "repository:r_network",
                "name": "network-checkout",
                "remote_url": "https://github.com/platformcontext/network-module",
                "repo_slug": "platformcontext/network-module",
            }
        ],
        module_rows=[
            {
                "source": "git@github.com:platformcontext/network-module.git",
            }
        ],
    )
    linker = CrossRepoLinker(
        SimpleNamespace(get_driver=lambda: SimpleNamespace(session=lambda: session))
    )

    count = linker._link_terraform_modules()

    assert count == 1
    assert session.links == [
        [
            {
                "source": "git@github.com:platformcontext/network-module.git",
                "repo_id": "repository:r_network",
            }
        ]
    ]


def test_terragrunt_source_links_use_normalized_remote_url() -> None:
    """Terragrunt terraform_source refs should match by slug or remote URL."""

    session = _FakeSession(
        repository_rows=[
            {
                "id": "repository:r_platform",
                "name": "terraform-platform-modules",
                "remote_url": "https://github.com/platformcontext/terraform-platform-modules",
                "repo_slug": "platformcontext/terraform-platform-modules",
            }
        ],
        terragrunt_rows=[
            {
                "source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
            }
        ],
    )
    linker = CrossRepoLinker(
        SimpleNamespace(get_driver=lambda: SimpleNamespace(session=lambda: session))
    )

    count = linker._link_terraform_modules()

    assert count == 1
    assert session.links == [
        [
            {
                "source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
                "repo_id": "repository:r_platform",
            }
        ]
    ]
