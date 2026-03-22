"""Graph-store support for impact queries."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable

from ...domain import EntityType
from .common import (
    coerce_entity,
    dedupe_evidence,
    graph_from_fixture,
    load_fixture_graph,
    ref_from_id,
    ref_from_snapshot,
)
from .database import (
    db_fetch_argocd_source_repo_edges,
    db_fetch_edges,
    db_fetch_entity,
    db_fetch_workload_instances,
    has_direct_edge,
)


class _GraphStore:
    """In-memory graph view used by impact queries."""

    def __init__(
        self,
        entities: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        """Initialize the in-memory graph store.

        Args:
            entities: Canonical entity snapshots keyed by ID.
            edges: Edge snapshots connecting those entities.
        """

        self.entities = {
            entity_id: dict(entity)
            for entity_id, entity in entities.items()
            if entity_id
        }
        seen_edges: set[tuple[Any, Any, Any, Any]] = set()
        deduped_edges: list[dict[str, Any]] = []
        for edge in edges:
            if not edge.get("from") or not edge.get("to"):
                continue
            signature = (
                edge.get("from"),
                edge.get("to"),
                edge.get("type"),
                edge.get("reason"),
            )
            if signature in seen_edges:
                continue
            seen_edges.add(signature)
            deduped_edges.append(dict(edge))
        self.edges = deduped_edges
        self._adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build_adjacency()

    @classmethod
    def from_source(
        cls,
        database: Any,
        root_ids: list[str],
        *,
        environment: str | None = None,
    ) -> "_GraphStore":
        """Build a graph store from a fixture or live database source.

        Args:
            database: Query-layer database dependency or fixture source.
            root_ids: Seed entity identifiers for graph expansion.
            environment: Optional environment scope for workload-instance expansion.

        Returns:
            Populated graph store for the requested roots.
        """

        fixture = load_fixture_graph(database)
        if fixture is not None:
            entities, edges = graph_from_fixture(fixture)
            return cls(entities, edges)

        entities: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        pending = list(dict.fromkeys(root_ids))
        seen: set[str] = set()

        while pending:
            entity_id = pending.pop()
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)

            entity = db_fetch_entity(database, entity_id)
            if entity:
                entities[entity_id] = entity
                if entity.get("workload_id"):
                    pending.append(entity["workload_id"])
                if entity.get("repo_id"):
                    pending.append(entity["repo_id"])
                if entity.get("type") == EntityType.repository.value and entity.get(
                    "name"
                ):
                    for inferred_edge in db_fetch_argocd_source_repo_edges(
                        database,
                        repo_id=entity_id,
                        repo_name=entity["name"],
                    ):
                        edges.append(inferred_edge)
                        if inferred_edge.get("to"):
                            pending.append(inferred_edge["to"])

            for edge in db_fetch_edges(database, entity_id):
                edges.append(edge)
                if edge.get("from"):
                    pending.append(edge["from"])
                if edge.get("to"):
                    pending.append(edge["to"])

            if entity and entity.get("type") == EntityType.workload.value:
                requested_environments = [
                    parts[2]
                    for root_id in root_ids
                    for parts in [root_id.split(":")]
                    if root_id.startswith("workload-instance:")
                    and len(parts) >= 3
                    and parts[1] == entity.get("name")
                ]
                if requested_environments:
                    for requested_environment in dict.fromkeys(requested_environments):
                        for instance in db_fetch_workload_instances(
                            database,
                            workload_id=entity_id,
                            environment=requested_environment,
                        ):
                            if instance["id"] not in entities:
                                entities[instance["id"]] = instance
                                pending.append(instance["id"])
                    continue

                for instance in db_fetch_workload_instances(
                    database,
                    workload_id=entity_id,
                    environment=environment,
                ):
                    if instance["id"] not in entities:
                        entities[instance["id"]] = instance
                        pending.append(instance["id"])

        return cls(entities, edges)

    def snapshot(self, entity_id: str) -> dict[str, Any]:
        """Return a portable entity reference snapshot for the given ID.

        Args:
            entity_id: Canonical entity identifier.

        Returns:
            Portable entity reference payload.
        """

        entity = self.entities.get(entity_id)
        if entity is None:
            return ref_from_id(entity_id)
        return ref_from_snapshot(coerce_entity(entity, entity_id))

    def _add_step(
        self,
        source_id: str,
        target_id: str,
        *,
        relation: str,
        confidence: float | None,
        reason: str | None,
        evidence: Iterable[dict[str, Any]] | None,
        inferred: bool,
        direction: str,
    ) -> None:
        """Add an adjacency step between two snapshots.

        Args:
            source_id: Source entity identifier.
            target_id: Target entity identifier.
            relation: Relationship type name.
            confidence: Optional confidence score.
            reason: Optional reason string.
            evidence: Optional evidence payloads.
            inferred: Whether the edge is inferred.
            direction: Traversal direction label.
        """

        self._adjacency[source_id].append(
            {
                "from": self.snapshot(source_id),
                "to": self.snapshot(target_id),
                "type": relation,
                "confidence": round(
                    float(
                        confidence
                        if confidence is not None
                        else (0.95 if inferred else 0.8)
                    ),
                    2,
                ),
                "reason": reason or relation.replace("_", " ").title(),
                "evidence": dedupe_evidence(list(evidence or [])),
                "inferred": inferred,
                "direction": direction,
            }
        )

    def _build_adjacency(self) -> None:
        """Build the adjacency map used for graph traversal."""

        for edge in self.edges:
            source_id = edge["from"]
            target_id = edge["to"]
            relation = edge.get("type") or "RELATED_TO"
            confidence = edge.get("confidence")
            reason = edge.get("reason")
            evidence = edge.get("evidence") or []
            self._add_step(
                source_id,
                target_id,
                relation=relation,
                confidence=confidence,
                reason=reason,
                evidence=evidence,
                inferred=False,
                direction="forward",
            )
            self._add_step(
                target_id,
                source_id,
                relation=relation,
                confidence=confidence,
                reason=reason,
                evidence=evidence,
                inferred=False,
                direction="reverse",
            )

        for entity_id, entity in self.entities.items():
            if entity.get("type") == EntityType.workload_instance.value and entity.get(
                "workload_id"
            ):
                workload_id = entity["workload_id"]
                self._add_step(
                    entity_id,
                    workload_id,
                    relation="INSTANCE_OF",
                    confidence=1.0,
                    reason="Workload instance belongs to workload",
                    evidence=[
                        {
                            "source": "workload-instance",
                            "detail": f"{entity_id} -> {workload_id}",
                            "weight": 1.0,
                        }
                    ],
                    inferred=True,
                    direction="forward",
                )
                self._add_step(
                    workload_id,
                    entity_id,
                    relation="INSTANCE_OF",
                    confidence=0.95,
                    reason=(
                        f"Environment {entity.get('environment')} resolves workload "
                        "to workload instance"
                    ),
                    evidence=[
                        {
                            "source": "workload-instance",
                            "detail": f"{entity_id} -> {workload_id}",
                            "weight": 0.95,
                        }
                    ],
                    inferred=True,
                    direction="reverse",
                )

            if entity.get("type") == EntityType.workload.value and entity.get(
                "repo_id"
            ):
                repo_id = entity["repo_id"]
                if not has_direct_edge(
                    self.edges, entity_id, repo_id
                ) and not has_direct_edge(self.edges, repo_id, entity_id):
                    self._add_step(
                        entity_id,
                        repo_id,
                        relation="DEFINES",
                        confidence=1.0,
                        reason="Repository defines workload",
                        evidence=[
                            {
                                "source": "repo-manifest",
                                "detail": f"{entity['name']} workload definition",
                                "weight": 1.0,
                            }
                        ],
                        inferred=True,
                        direction="forward",
                    )

            if entity.get("type") == EntityType.terraform_module.value and entity.get(
                "repo_id"
            ):
                repo_id = entity["repo_id"]
                if not has_direct_edge(
                    self.edges, entity_id, repo_id
                ) and not has_direct_edge(self.edges, repo_id, entity_id):
                    self._add_step(
                        entity_id,
                        repo_id,
                        relation="DEFINES",
                        confidence=1.0,
                        reason="Repository defines terraform module",
                        evidence=[
                            {
                                "source": "terraform",
                                "detail": f"{entity['name']} module definition",
                                "weight": 1.0,
                            }
                        ],
                        inferred=True,
                        direction="forward",
                    )

    def neighbors(
        self,
        entity_id: str,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return traversable neighboring steps for an entity.

        Args:
            entity_id: Canonical entity identifier.
            environment: Optional environment preference for sorting.

        Returns:
            Sorted adjacency steps for the entity.
        """

        neighbors = list(self._adjacency.get(entity_id, []))
        if environment is None:
            return sorted(neighbors, key=self._neighbor_sort_key)
        return sorted(
            neighbors,
            key=lambda step: self._neighbor_sort_key(step, environment),
        )

    def _neighbor_sort_key(
        self,
        step: dict[str, Any],
        environment: str | None = None,
    ) -> tuple[int, float, str]:
        """Build a sort key for adjacency traversal.

        Args:
            step: Candidate adjacency step.
            environment: Optional preferred environment.

        Returns:
            Sort key that prioritizes environment-specific runtime entities.
        """

        target = step["to"]
        priority = 2
        if environment and target.get("type") == EntityType.workload_instance.value:
            if target.get("environment") == environment:
                priority = 0
            else:
                priority = 3
        elif target.get("type") in {
            EntityType.repository.value,
            EntityType.cloud_resource.value,
            EntityType.terraform_module.value,
        }:
            priority = 1
        confidence = float(step.get("confidence") or 0.0)
        return (priority, -confidence, target["id"])

    def paths_to(
        self,
        *,
        source_id: str,
        target_predicate: Any,
        environment: str | None = None,
        max_depth: int = 8,
        limit: int | None = None,
        continue_through_targets: bool = False,
    ) -> list[list[dict[str, Any]]]:
        """Traverse the graph to collect paths that satisfy a target predicate.

        Args:
            source_id: Starting entity identifier.
            target_predicate: Callable deciding whether a node is a target.
            environment: Optional preferred environment.
            max_depth: Maximum traversal depth.
            limit: Optional maximum number of paths to return.
            continue_through_targets: Whether traversal should continue after
                hitting a target.

        Returns:
            Matching paths as lists of adjacency steps.
        """

        results: list[list[dict[str, Any]]] = []
        stack: list[tuple[str, list[dict[str, Any]], set[str]]] = [
            (source_id, [], {source_id})
        ]

        while stack:
            current_id, hops, seen = stack.pop()
            if len(hops) >= max_depth:
                continue
            for step in reversed(self.neighbors(current_id, environment=environment)):
                next_id = step["to"]["id"]
                if next_id in seen:
                    continue
                next_hops = hops + [step]
                if target_predicate(step["to"]):
                    results.append(next_hops)
                    if limit is not None and len(results) >= limit:
                        return results
                    if not continue_through_targets:
                        continue
                stack.append((next_id, next_hops, seen | {next_id}))
        return results

    def shortest_path(
        self,
        *,
        source_id: str,
        target_id: str,
        environment: str | None = None,
        max_depth: int = 8,
    ) -> list[dict[str, Any]] | None:
        """Return the shortest path between two entities when one exists.

        Args:
            source_id: Starting entity identifier.
            target_id: Target entity identifier.
            environment: Optional preferred environment.
            max_depth: Maximum traversal depth.

        Returns:
            Shortest path as adjacency steps, or ``None`` when no path exists.
        """

        queue: deque[tuple[str, list[dict[str, Any]], set[str]]] = deque(
            [(source_id, [], {source_id})]
        )
        while queue:
            current_id, hops, seen = queue.popleft()
            if len(hops) >= max_depth:
                continue
            for step in self.neighbors(current_id, environment=environment):
                next_id = step["to"]["id"]
                if next_id in seen:
                    continue
                next_hops = hops + [step]
                if next_id == target_id:
                    return next_hops
                queue.append((next_id, next_hops, seen | {next_id}))
        return None
