"""Cross-repo relationship builder for ecosystem graphs.

After individual repos are indexed, this module creates
relationships that span repository boundaries: ArgoCD ->
Repository sourcing, Crossplane claim -> XRD satisfaction,
Terraform module references, K8s label selector matching, etc.
"""

from typing import Any

from ..core.database import DatabaseManager
from ..utils.debug_log import (
    error_logger,
    info_logger,
)


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
            application_result = session.run("""
                MATCH (app:ArgoCDApplication)
                WHERE app.source_repo IS NOT NULL
                  AND app.source_repo <> ''
                MATCH (repo:Repository)
                WHERE app.source_repo CONTAINS repo.name
                MERGE (app)-[:SOURCES_FROM]->(repo)
                RETURN count(*) as cnt
            """)
            appset_result = session.run("""
                MATCH (app:ArgoCDApplicationSet)
                WHERE app.source_repos IS NOT NULL
                  AND app.source_repos <> ''
                MATCH (repo:Repository)
                WHERE any(source_repo IN split(app.source_repos, ',')
                    WHERE trim(source_repo) CONTAINS repo.name)
                MERGE (app)-[:SOURCES_FROM]->(repo)
                RETURN count(*) as cnt
            """)
            application_record = application_result.single()
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
                WHERE claim.kind = xrd.claim_kind
                MERGE (claim)-[:SATISFIED_BY]->(xrd)
                RETURN count(*) as cnt
            """)
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
                WHERE comp.composite_kind = xrd.kind
                MERGE (xrd)-[:IMPLEMENTED_BY]->(comp)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_terraform_modules(self) -> int:
        """Link Terraform module calls to source modules/repos.

        Matches module source URLs/paths against indexed
        Repository names or TerraformModule source paths.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (mod:TerraformModule)
                WHERE mod.source IS NOT NULL
                  AND mod.source <> ''
                MATCH (repo:Repository)
                WHERE mod.source CONTAINS repo.name
                MERGE (mod)-[:USES_MODULE]->(repo)
                RETURN count(*) as cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0

    def _link_argocd_deploys(self) -> int:
        """Link ArgoCD Applications to K8s resources they deploy.

        Matches by namespace and source path correlation.
        """
        with self.driver.session() as session:
            application_result = session.run("""
                MATCH (app:ArgoCDApplication)
                WHERE app.dest_namespace IS NOT NULL
                  AND app.dest_namespace <> ''
                MATCH (k:K8sResource)
                WHERE k.namespace = app.dest_namespace
                MATCH (f:File)-[:CONTAINS]->(k)
                MATCH (repo:Repository)-[:CONTAINS*]->(f)
                MATCH (app)-[:SOURCES_FROM]->(repo)
                MERGE (app)-[:DEPLOYS]->(k)
                RETURN count(*) as cnt
            """)
            appset_result = session.run("""
                MATCH (app:ArgoCDApplicationSet)-[:SOURCES_FROM]->(repo:Repository)
                WHERE app.source_roots IS NOT NULL
                  AND app.source_roots <> ''
                MATCH (repo)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)
                WHERE any(source_root IN split(app.source_roots, ',')
                    WHERE trim(source_root) <> ''
                      AND f.relative_path STARTS WITH trim(source_root))
                MERGE (app)-[:DEPLOYS]->(k)
                RETURN count(*) as cnt
            """)
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
        """Link HTTPRoutes to likely backend Services.

        Heuristic: matches routes to services by name prefix
        within the same namespace. Does not parse actual
        backendRef specs from the HTTPRoute.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (route:K8sResource {kind: 'HTTPRoute'})
                MATCH (svc:K8sResource {kind: 'Service'})
                WHERE route.namespace = svc.namespace
                  AND route.name STARTS WITH svc.name
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
