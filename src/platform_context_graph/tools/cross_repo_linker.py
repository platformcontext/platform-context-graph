"""Cross-repo relationship builder for ecosystem graphs.

After individual repos are indexed, this module creates
relationships that span repository boundaries: ArgoCD ->
Repository sourcing, Crossplane claim -> XRD satisfaction,
Terraform module references, K8s label selector matching, etc.
"""

from typing import Any

from ..core.database import DatabaseManager
from ..repository_identity import normalize_remote_url, repo_slug_from_remote_url
from ..utils.debug_log import (
    error_logger,
    info_logger,
)


def _clean_text(value: Any) -> str | None:
    """Return a trimmed string for matching or ``None`` for empty values."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _repository_match_keys(repository: dict[str, Any]) -> list[str]:
    """Return the lookup keys that should identify one repository node."""

    keys: list[str] = []
    for candidate in (
        normalize_remote_url(repository.get("remote_url")),
        repo_slug_from_remote_url(repository.get("remote_url")),
        normalize_remote_url(repository.get("repo_slug")),
        repo_slug_from_remote_url(repository.get("repo_slug")),
        _clean_text(repository.get("name")),
    ):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def _reference_match_keys(reference: str | None) -> list[str]:
    """Return ranked lookup keys for one remote repository reference."""

    cleaned_reference = _clean_text(reference)
    if cleaned_reference is None:
        return []

    keys: list[str] = []
    for candidate in (
        normalize_remote_url(cleaned_reference),
        repo_slug_from_remote_url(cleaned_reference),
        cleaned_reference,
    ):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def _repository_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Index repository rows by their normalized remote and slug keys."""

    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for key in _repository_match_keys(row):
            index.setdefault(key, []).append(row)
    return index


def _first_matching_repositories(
    reference: str | None,
    repository_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return the best matching repository rows for one source reference."""

    for key in _reference_match_keys(reference):
        rows = repository_index.get(key)
        if rows:
            seen: set[str] = set()
            matches: list[dict[str, Any]] = []
            for row in rows:
                repo_id = _clean_text(row.get("id"))
                if repo_id is None or repo_id in seen:
                    continue
                seen.add(repo_id)
                matches.append(row)
            return matches
    return []


def _split_references(raw_references: str | None) -> list[str]:
    """Return normalized source references from a comma-separated field."""

    if raw_references is None:
        return []
    return [
        reference
        for reference in (_clean_text(part) for part in raw_references.split(","))
        if reference is not None
    ]


class CrossRepoLinker:
    """Builds cross-repository relationships in the graph.

    Scans indexed nodes to find relationships that span repo
    boundaries. Each link type has its own detection method.

    Args:
        db_manager: Database manager for graph queries.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize the linker with a database manager."""
        self.db_manager = db_manager
        self.driver = db_manager.get_driver()
        self.stats: dict[str, int] = {}

    def link_all(self) -> dict[str, Any]:
        """Run all cross-repo linking phases.

        Returns:
            Dict with counts of each relationship type created.
        """
        self.stats = {}

        linkers = [
            ("SOURCES_FROM", self._link_argocd_sources),
            ("SATISFIED_BY", self._link_crossplane_claims),
            ("IMPLEMENTED_BY", self._link_crossplane_compositions),
            ("USES_MODULE", self._link_terraform_modules),
            ("DEPLOYS", self._link_argocd_deploys),
            ("CONFIGURES", self._link_helm_values_to_charts),
            ("SELECTS", self._link_label_selectors),
            ("USES_IAM", self._link_irsa_annotations),
            ("ROUTES_TO", self._link_httproute_backends),
            ("PATCHES", self._link_kustomize_patches),
            ("RUNS_IMAGE", self._link_container_images),
        ]

        for rel_type, linker_fn in linkers:
            try:
                count = linker_fn()
                self.stats[rel_type] = count
                if count > 0:
                    info_logger(f"Created {count} {rel_type} relationships")
            except Exception as e:
                error_logger(f"Error creating {rel_type} relationships: {e}")
                self.stats[rel_type] = 0

        return self.stats

    def _link_argocd_sources(self) -> int:
        """Link ArgoCD Applications to source Repositories.

        Matches spec.source.repoURL against indexed Repository
        nodes by comparing URL patterns.
        """
        with self.driver.session() as session:
            repository_rows = session.run("""
                MATCH (repo:Repository)
                RETURN repo.id as id,
                       repo.name as name,
                       repo[$remote_url_key] as remote_url,
                       repo[$repo_slug_key] as repo_slug
            """, remote_url_key="remote_url", repo_slug_key="repo_slug").data()
            repository_index = _repository_index(repository_rows)
            links: list[dict[str, str]] = []
            seen_links: set[tuple[str, str, str]] = set()

            application_rows = session.run("""
                MATCH (app:ArgoCDApplication)
                WHERE app[$source_repo_key] IS NOT NULL
                  AND app[$source_repo_key] <> ''
                RETURN app[$source_repo_key] as source_repo
            """, source_repo_key="source_repo").data()
            for row in application_rows:
                source_repo = _clean_text(row.get("source_repo"))
                if source_repo is None:
                    continue
                for repo in _first_matching_repositories(source_repo, repository_index):
                    repo_id = _clean_text(repo.get("id"))
                    if repo_id is None:
                        continue
                    link_key = ("application", source_repo, repo_id)
                    if link_key in seen_links:
                        continue
                    seen_links.add(link_key)
                    links.append({"source_repo": source_repo, "repo_id": repo_id})

            appset_rows = session.run("""
                MATCH (app:ArgoCDApplicationSet)
                WHERE app[$source_repos_key] IS NOT NULL
                  AND app[$source_repos_key] <> ''
                RETURN app[$source_repos_key] as source_repos
            """, source_repos_key="source_repos").data()
            for row in appset_rows:
                source_repos = _clean_text(row.get("source_repos"))
                if source_repos is None:
                    continue
                matched_repo_ids: set[str] = set()
                for source_repo in _split_references(source_repos):
                    for repo in _first_matching_repositories(
                        source_repo, repository_index
                    ):
                        repo_id = _clean_text(repo.get("id"))
                        if repo_id is None or repo_id in matched_repo_ids:
                            continue
                        matched_repo_ids.add(repo_id)
                        link_key = ("appset", source_repos, repo_id)
                        if link_key in seen_links:
                            continue
                        seen_links.add(link_key)
                        links.append({"source_repos": source_repos, "repo_id": repo_id})

            application_links = [link for link in links if "source_repo" in link]
            appset_links = [link for link in links if "source_repos" in link]
            if not application_links and not appset_links:
                return 0

            application_record = None
            if application_links:
                application_result = session.run(
                    """
                    UNWIND $links AS link
                    MATCH (app:ArgoCDApplication)
                    WHERE app[$source_repo_key] = link.source_repo
                    MATCH (repo:Repository {id: link.repo_id})
                    MERGE (app)-[:SOURCES_FROM]->(repo)
                    RETURN count(*) as cnt
                    """,
                    links=application_links,
                    source_repo_key="source_repo",
                )
                application_record = application_result.single()

            appset_record = None
            if appset_links:
                appset_result = session.run(
                    """
                    UNWIND $links AS link
                    MATCH (app:ArgoCDApplicationSet)
                    WHERE app[$source_repos_key] = link.source_repos
                    MATCH (repo:Repository {id: link.repo_id})
                    MERGE (app)-[:SOURCES_FROM]->(repo)
                    RETURN count(*) as cnt
                    """,
                    links=appset_links,
                    source_repos_key="source_repos",
                )
                appset_record = appset_result.single()
            return (application_record["cnt"] if application_record else 0) + (
                appset_record["cnt"] if appset_record else 0
            )

    def _link_crossplane_claims(self) -> int:
        """Link Crossplane Claims to their matching XRDs.

        Matches claim kind against XRD claim_kind.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (claim:CrossplaneClaim)
                MATCH (xrd:CrossplaneXRD)
                WHERE claim.kind = xrd[$claim_kind_key]
                MERGE (claim)-[:SATISFIED_BY]->(xrd)
                RETURN count(*) as cnt
            """, claim_kind_key="claim_kind")
            record = result.single()
            return record["cnt"] if record else 0

    def _link_crossplane_compositions(self) -> int:
        """Link XRDs to their implementing Compositions.

        Matches compositeTypeRef.kind against XRD kind.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (xrd:CrossplaneXRD)
                MATCH (comp:CrossplaneComposition)
                WHERE comp[$composite_kind_key] = xrd.kind
                MERGE (xrd)-[:IMPLEMENTED_BY]->(comp)
                RETURN count(*) as cnt
            """, composite_kind_key="composite_kind")
            record = result.single()
            return record["cnt"] if record else 0

    def _link_terraform_modules(self) -> int:
        """Link Terraform module calls to source modules/repos.

        Matches module source URLs/paths against indexed
        Repository names or TerraformModule source paths.
        """
        with self.driver.session() as session:
            repository_rows = session.run("""
                MATCH (repo:Repository)
                RETURN repo.id as id,
                       repo.name as name,
                       repo[$remote_url_key] as remote_url,
                       repo[$repo_slug_key] as repo_slug
            """, remote_url_key="remote_url", repo_slug_key="repo_slug").data()
            repository_index = _repository_index(repository_rows)
            links: list[dict[str, str]] = []
            seen_links: set[tuple[str, str]] = set()

            module_rows = session.run("""
                MATCH (mod:TerraformModule)
                WHERE mod.source IS NOT NULL
                  AND mod.source <> ''
                RETURN mod.source as source
            """).data()
            for row in module_rows:
                source = _clean_text(row.get("source"))
                if source is None:
                    continue
                for repo in _first_matching_repositories(source, repository_index):
                    repo_id = _clean_text(repo.get("id"))
                    if repo_id is None:
                        continue
                    link_key = (source, repo_id)
                    if link_key in seen_links:
                        continue
                    seen_links.add(link_key)
                    links.append({"source": source, "repo_id": repo_id})

            if not links:
                return 0

            result = session.run(
                """
                UNWIND $links AS link
                MATCH (mod:TerraformModule)
                WHERE mod.source = link.source
                MATCH (repo:Repository {id: link.repo_id})
                MERGE (mod)-[:USES_MODULE]->(repo)
                RETURN count(*) as cnt
                """,
                links=links,
            )
            record = result.single()
            return record["cnt"] if record else 0

    def _link_argocd_deploys(self) -> int:
        """Link ArgoCD Applications to K8s resources they deploy.

        Matches by namespace and source path correlation.
        """
        with self.driver.session() as session:
            application_result = session.run("""
                MATCH (app:ArgoCDApplication)
                WHERE app[$dest_namespace_key] IS NOT NULL
                  AND app[$dest_namespace_key] <> ''
                MATCH (k:K8sResource)
                WHERE k.namespace = app[$dest_namespace_key]
                MATCH (f:File)-[:CONTAINS]->(k)
                MATCH (repo:Repository)-[:CONTAINS*]->(f)
                MATCH (app)-[:SOURCES_FROM]->(repo)
                MERGE (app)-[:DEPLOYS]->(k)
                RETURN count(*) as cnt
            """, dest_namespace_key="dest_namespace")
            appset_result = session.run("""
                MATCH (app:ArgoCDApplicationSet)-[:SOURCES_FROM]->(repo:Repository)
                WHERE app[$source_roots_key] IS NOT NULL
                  AND app[$source_roots_key] <> ''
                MATCH (repo)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)
                WHERE any(source_root IN split(app[$source_roots_key], ',')
                    WHERE trim(source_root) <> ''
                      AND f.relative_path STARTS WITH trim(source_root))
                MERGE (app)-[:DEPLOYS]->(k)
                RETURN count(*) as cnt
            """, source_roots_key="source_roots")
            application_record = application_result.single()
            appset_record = appset_result.single()
            return (application_record["cnt"] if application_record else 0) + (
                appset_record["cnt"] if appset_record else 0
            )

    def _link_helm_values_to_charts(self) -> int:
        """Link HelmValues to their HelmChart by colocation.

        values.yaml and Chart.yaml in the same directory or
        parent directory.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (hv:HelmValues)
                MATCH (hc:HelmChart)
                WHERE hv.path STARTS WITH
                    replace(hc.path, '/Chart.yaml', '')
                   OR hv.path STARTS WITH
                    replace(hc.path, '/Chart.yml', '')
                MERGE (hv)-[:CONFIGURES]->(hc)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_label_selectors(self) -> int:
        """Link K8s Services to same-named Deployments.

        Heuristic: matches Service to Deployment by name and
        namespace. Covers the common pattern where both share
        the same name. Does not parse actual label selectors.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (deploy:K8sResource {kind: 'Deployment'})
                MATCH (svc:K8sResource {kind: 'Service'})
                WHERE deploy.namespace = svc.namespace
                  AND deploy.name = svc.name
                MERGE (svc)-[:SELECTS]->(deploy)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_irsa_annotations(self) -> int:
        """Link ServiceAccounts to IAM roles via IRSA annotation.

        Detects eks.amazonaws.com/role-arn annotation on
        ServiceAccount nodes.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (sa:K8sResource {kind: 'ServiceAccount'})
                WHERE sa.annotations IS NOT NULL
                  AND sa.annotations CONTAINS
                    'eks.amazonaws.com/role-arn'
                MATCH (tf:TerraformResource)
                WHERE tf.resource_type = 'aws_iam_role'
                  AND sa.annotations CONTAINS tf.resource_name
                MERGE (sa)-[:USES_IAM]->(tf)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_httproute_backends(self) -> int:
        """Link HTTPRoutes to backend Services via backendRefs.

        Uses the ``backend_refs`` property extracted during parsing
        which contains comma-separated service names from
        ``spec.rules[*].backendRefs[*].name``.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (route:K8sResource {kind: 'HTTPRoute'})
                WHERE route.backend_refs IS NOT NULL
                UNWIND split(route.backend_refs, ',') AS backend_name
                MATCH (svc:K8sResource {kind: 'Service'})
                WHERE svc.name = trim(backend_name)
                  AND svc.namespace = route.namespace
                MERGE (route)-[:ROUTES_TO]->(svc)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_kustomize_patches(self) -> int:
        """Link KustomizeOverlays to resources they reference.

        Matches resource paths listed in kustomization.yaml
        against indexed K8s resource files.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (ko:KustomizeOverlay)
                WHERE ko.resources IS NOT NULL
                MATCH (f:File)-[:CONTAINS]->(k:K8sResource)
                WHERE any(res IN ko.resources
                    WHERE f.relative_path ENDS WITH res)
                MERGE (ko)-[:PATCHES]->(k)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_container_images(self) -> int:
        """Link K8s Deployments to source Repositories via container image.

        Extracts image name from K8sResource container_images property
        and matches against Repository names.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (k:K8sResource)
                WHERE k.container_images IS NOT NULL
                  AND k.container_images <> ''
                MATCH (repo:Repository)
                WHERE any(img IN split(k.container_images, ',')
                    WHERE img CONTAINS repo.name)
                MERGE (k)-[:RUNS_IMAGE]->(repo)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0
