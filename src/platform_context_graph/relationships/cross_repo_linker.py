"""Cross-repo relationship builder for ecosystem graphs."""

from typing import Any

from ..core.database import DatabaseManager
from .cross_repo_linker_support import (
    clean_text,
    first_matching_repositories,
    reference_links,
    repository_index,
    split_references,
)
from ..utils.debug_log import error_logger, info_logger


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
            repo_lookup = repository_index(repository_rows)
            links: list[dict[str, str]] = []
            seen_links: set[tuple[str, str, str]] = set()

            application_rows = session.run("""
                MATCH (app:ArgoCDApplication)
                WHERE app[$source_repo_key] IS NOT NULL
                  AND app[$source_repo_key] <> ''
                RETURN app[$source_repo_key] as source_repo
            """, source_repo_key="source_repo").data()
            for row in application_rows:
                source_repo = clean_text(row.get("source_repo"))
                if source_repo is None:
                    continue
                for repo in first_matching_repositories(source_repo, repo_lookup):
                    repo_id = clean_text(repo.get("id"))
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
                source_repos = clean_text(row.get("source_repos"))
                if source_repos is None:
                    continue
                matched_repo_ids: set[str] = set()
                for source_repo in split_references(source_repos):
                    for repo in first_matching_repositories(source_repo, repo_lookup):
                        repo_id = clean_text(repo.get("id"))
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
        """Link Terraform and Terragrunt module sources to repositories.

        Matches module source URLs/paths against indexed
        Repository names or module source paths.
        """
        with self.driver.session() as session:
            repository_rows = session.run("""
                MATCH (repo:Repository)
                RETURN repo.id as id,
                       repo.name as name,
                       repo[$remote_url_key] as remote_url,
                       repo[$repo_slug_key] as repo_slug
            """, remote_url_key="remote_url", repo_slug_key="repo_slug").data()
            repo_lookup = repository_index(repository_rows)

            module_rows = session.run("""
                MATCH (mod:TerraformModule)
                WHERE mod.source IS NOT NULL
                  AND mod.source <> ''
                RETURN mod.source as source
            """).data()
            terragrunt_rows = session.run("""
                MATCH (tg:TerragruntConfig)
                WHERE tg[$terraform_source_key] IS NOT NULL
                  AND tg[$terraform_source_key] <> ''
                RETURN tg[$terraform_source_key] as source
            """, terraform_source_key="terraform_source").data()

            module_links = reference_links(module_rows, repo_lookup)
            terragrunt_links = reference_links(terragrunt_rows, repo_lookup)

            count = 0
            if module_links:
                result = session.run(
                    """
                    UNWIND $links AS link
                    MATCH (mod:TerraformModule)
                    WHERE mod.source = link.source
                    MATCH (repo:Repository {id: link.repo_id})
                    MERGE (mod)-[:USES_MODULE]->(repo)
                    RETURN count(*) as cnt
                    """,
                    links=module_links,
                )
                record = result.single()
                count += record["cnt"] if record else 0

            if terragrunt_links:
                result = session.run(
                    """
                    UNWIND $links AS link
                    MATCH (tg:TerragruntConfig)
                    WHERE tg[$terraform_source_key] = link.source
                    MATCH (repo:Repository {id: link.repo_id})
                    MERGE (tg)-[:USES_MODULE]->(repo)
                    RETURN count(*) as cnt
                    """,
                    links=terragrunt_links,
                    terraform_source_key="terraform_source",
                )
                record = result.single()
                count += record["cnt"] if record else 0

            return count

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
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                MATCH (app)-[:SOURCES_FROM]->(repo)
                MERGE (app)-[:DEPLOYS]->(k)
                RETURN count(*) as cnt
            """, dest_namespace_key="dest_namespace")
            appset_result = session.run("""
                MATCH (app:ArgoCDApplicationSet)-[:SOURCES_FROM]->(repo:Repository)
                WHERE app[$source_roots_key] IS NOT NULL
                  AND app[$source_roots_key] <> ''
                MATCH (repo)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(k:K8sResource)
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
