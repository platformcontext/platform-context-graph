#!/usr/bin/env python3
"""Trace evidence promotion end-to-end for one repository.

Queries both the API and Neo4j directly to identify where evidence
is lost between raw graph data and promoted story/context output.

Usage:
    PYTHONPATH=src uv run python scripts/trace_evidence_promotion.py \
        --repo-name api-node-boats \
        --api-url http://localhost:8080/api/v0 \
        --api-key <key>

Environment fallbacks:
    NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, DATABASE_TYPE
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def _api_get(client: httpx.Client, path: str) -> dict[str, Any]:
    """Issue one GET and return JSON."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _neo4j_session():
    """Return a live Neo4j session using env-based config."""

    os.environ.setdefault("DATABASE_TYPE", "neo4j")
    from platform_context_graph.core import get_database_manager

    db = get_database_manager()
    driver = db.get_driver()
    return driver.session()


def _single(session: Any, query: str, **params: Any) -> Any:
    """Run a query and return one record."""

    return session.run(query, **params).single()


def _all(session: Any, query: str, **params: Any) -> list[dict[str, Any]]:
    """Run a query and return all records as dicts."""

    return session.run(query, **params).data()


def _section(title: str) -> None:
    """Print a section header."""

    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def trace_graph(session: Any, repo_name: str) -> dict[str, Any]:
    """Query Neo4j directly for all evidence related to the repo."""

    results: dict[str, Any] = {}

    _section("GRAPH: Repository Node")
    repo = _single(
        session,
        "MATCH (r:Repository {name: $name}) RETURN r",
        name=repo_name,
    )
    if repo:
        print(f"  Found: {dict(repo['r'])}")
        results["repository_found"] = True
    else:
        print(f"  NOT FOUND: {repo_name}")
        results["repository_found"] = False
        return results

    _section("GRAPH: All Relationships")
    rels = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[rel]-(other)
        RETURN type(rel) as type,
               startNode(rel) = r as outgoing,
               labels(other)[0] as other_label,
               other.name as other_name,
               other.id as other_id
        ORDER BY type(rel), other.name
        """,
        name=repo_name,
    )
    for row in rels:
        direction = "->" if row["outgoing"] else "<-"
        print(
            f"  {direction} [{row['type']}] {row['other_label']}"
            f"({row['other_name'] or row['other_id']})"
        )
    results["all_relationships"] = rels

    _section("GRAPH: DEPLOYS_FROM")
    deploys = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:DEPLOYS_FROM]->(dep:Repository)
        RETURN dep.name as name, dep.id as id
        """,
        name=repo_name,
    )
    for row in deploys:
        print(f"  -> {row['name']}")
    results["deploys_from"] = deploys

    _section("GRAPH: PROVISIONS_DEPENDENCY_FOR (incoming)")
    provisioned_by = _all(
        session,
        """
        MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository {name: $name})
        RETURN prov.name as name, prov.id as id
        """,
        name=repo_name,
    )
    for row in provisioned_by:
        print(f"  <- {row['name']}")
    results["provisioned_by"] = provisioned_by

    _section("GRAPH: RUNS_ON (direct)")
    runs_on = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:RUNS_ON]->(p:Platform)
        RETURN p.name as name, p.kind as kind, p.provider as provider,
               p.environment as environment
        """,
        name=repo_name,
    )
    for row in runs_on:
        print(f"  -> Platform({row['kind']}/{row['name']}, env={row['environment']})")
    results["runs_on_direct"] = runs_on

    _section("GRAPH: Workload Chain")
    workloads = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:DEFINES]->(w:Workload)
        RETURN w.id as id, w.name as name
        """,
        name=repo_name,
    )
    for row in workloads:
        print(f"  Workload: {row['id']} ({row['name']})")
    results["workloads"] = workloads

    instances = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:DEFINES]->(w:Workload)
              <-[:INSTANCE_OF]-(i:WorkloadInstance)
        OPTIONAL MATCH (i)-[:RUNS_ON]->(p:Platform)
        RETURN w.id as workload_id,
               i.id as instance_id, i.environment as env,
               p.name as platform_name, p.kind as platform_kind
        """,
        name=repo_name,
    )
    for row in instances:
        print(
            f"  Instance: {row['instance_id']} env={row['env']}"
            f" -> Platform({row['platform_kind']}/{row['platform_name']})"
        )
    results["workload_instances"] = instances

    _section("GRAPH: DEPENDS_ON")
    depends = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:DEPENDS_ON]->(dep:Repository)
        RETURN dep.name as name
        """,
        name=repo_name,
    )
    for row in depends:
        print(f"  -> {row['name']}")
    results["depends_on"] = depends

    _section("GRAPH: Infrastructure Nodes")
    tf_resources = _all(
        session,
        """
        MATCH (r:Repository {name: $name})-[:REPO_CONTAINS]->(f:File)
              -[:CONTAINS]->(tf:TerraformResource)
        RETURN tf.name as name, tf.resource_type as type,
               f.relative_path as file
        LIMIT 20
        """,
        name=repo_name,
    )
    if tf_resources:
        print(f"  TerraformResources: {len(tf_resources)}")
        for row in tf_resources[:5]:
            print(f"    {row['type']} / {row['name']} in {row['file']}")
    else:
        print("  No TerraformResource nodes")
    results["terraform_resources"] = tf_resources

    _section("GRAPH: Platform Nodes (all)")
    platforms = _all(
        session,
        """
        MATCH (p:Platform)
        RETURN p.id as id, p.name as name, p.kind as kind,
               p.provider as provider, p.environment as environment
        ORDER BY p.kind, p.name
        """,
    )
    for row in platforms:
        print(
            f"  Platform({row['kind']}/{row['name']},"
            f" provider={row['provider']}, env={row['environment']})"
        )
    results["all_platforms"] = platforms

    _section("GRAPH: Cross-Repo Relationships from Related Repos")
    related_repos = [
        "terraform-stack-boattrader",
        "helm-charts",
        "iac-eks-argocd",
    ]
    for related in related_repos:
        cross = _all(
            session,
            """
            MATCH (r:Repository {name: $name})-[rel]->(other)
            RETURN type(rel) as type,
                   labels(other)[0] as other_label,
                   other.name as other_name
            ORDER BY type(rel)
            """,
            name=related,
        )
        if cross:
            print(f"\n  {related}:")
            for row in cross:
                print(
                    f"    -> [{row['type']}] "
                    f"{row['other_label']}({row['other_name']})"
                )
    return results


def trace_api(
    client: httpx.Client, repo_name: str
) -> dict[str, Any]:
    """Query the API for promoted context and story."""

    results: dict[str, Any] = {}

    _section("API: Repository Listing")
    repos_payload = _api_get(client, "/repositories")
    repos = list(repos_payload.get("repositories") or [])
    repo_entry = None
    for repo in repos:
        if repo.get("name") == repo_name:
            repo_entry = repo
            break
    if not repo_entry:
        print(f"  NOT FOUND in API: {repo_name}")
        results["api_found"] = False
        return results

    repo_id = str(repo_entry.get("id") or repo_entry.get("repo_id") or "")
    print(f"  Found: id={repo_id}, name={repo_entry.get('name')}")
    results["api_found"] = True
    results["repo_id"] = repo_id

    from urllib.parse import quote

    encoded_id = quote(repo_id, safe="")

    _section("API: Repository Context")
    context = _api_get(client, f"/repositories/{encoded_id}/context")
    promoted_fields = {
        "platforms": context.get("platforms"),
        "deploys_from": context.get("deploys_from"),
        "provisioned_by": context.get("provisioned_by"),
        "deployment_chain": context.get("deployment_chain"),
        "environments": context.get("environments"),
        "limitations": context.get("limitations"),
        "coverage": context.get("coverage"),
        "ecosystem": context.get("ecosystem"),
    }
    for field_name, value in promoted_fields.items():
        if isinstance(value, list):
            status = f"{len(value)} items" if value else "EMPTY"
        elif isinstance(value, dict):
            status = f"{len(value)} keys" if value else "EMPTY"
        elif value is None:
            status = "NULL"
        else:
            status = str(value)
        print(f"  {field_name}: {status}")

    if context.get("platforms"):
        print("\n  Platforms detail:")
        for p in context["platforms"]:
            print(f"    kind={p.get('kind')} name={p.get('name')} provider={p.get('provider')}")
    if context.get("deploys_from"):
        print("\n  Deploys from detail:")
        for d in context["deploys_from"]:
            print(f"    {d.get('name')}")
    if context.get("provisioned_by"):
        print("\n  Provisioned by detail:")
        for p in context["provisioned_by"]:
            print(f"    {p.get('name')}")
    if context.get("ecosystem"):
        eco = context["ecosystem"]
        print(f"\n  Ecosystem: deps={eco.get('dependencies')}, dependents={eco.get('dependents')}")

    results["context"] = promoted_fields
    results["full_context"] = context

    _section("API: Repository Story")
    story = _api_get(client, f"/repositories/{encoded_id}/story")
    dep_overview = story.get("deployment_overview") or {}
    story_text = story.get("story")

    print(f"  story text present: {bool(story_text)}")
    print(f"  runtime_platforms: {dep_overview.get('runtime_platforms', [])}")
    print(f"  deploys_from: {dep_overview.get('deploys_from', [])}")
    print(f"  provisioned_by: {dep_overview.get('provisioned_by', [])}")
    print(f"  deployment_chain: {dep_overview.get('deployment_chain', [])}")
    print(f"  dependencies: {dep_overview.get('dependencies', [])}")

    results["story"] = story
    return results


def evaluate_hypotheses(
    graph: dict[str, Any], api: dict[str, Any]
) -> None:
    """Evaluate the four PRD hypotheses and print a matrix."""

    _section("HYPOTHESIS EVALUATION")

    # H1: Evidence exists but never becomes relationship facts
    graph_has_tf = bool(graph.get("terraform_resources"))
    graph_has_provisions = bool(graph.get("provisioned_by"))
    graph_has_deploys = bool(graph.get("deploys_from"))
    h1_pass = not graph_has_tf or (graph_has_provisions or graph_has_deploys)
    print(
        f"\n  H1: Evidence exists but never becomes relationships"
        f"\n      TF resources in graph: {len(graph.get('terraform_resources', []))}"
        f"\n      PROVISIONS_DEPENDENCY_FOR edges: {len(graph.get('provisioned_by', []))}"
        f"\n      DEPLOYS_FROM edges: {len(graph.get('deploys_from', []))}"
        f"\n      Result: {'PASS' if h1_pass else 'FAIL - evidence exists but no relationship edges'}"
    )

    # H2: Relationships exist but dropped by resolver
    api_platforms = api.get("context", {}).get("platforms") or []
    api_deploys = api.get("context", {}).get("deploys_from") or []
    api_provisioned = api.get("context", {}).get("provisioned_by") or []

    graph_deploys_names = {r["name"] for r in graph.get("deploys_from", [])}
    api_deploys_names = {r.get("name") for r in api_deploys}
    deploys_gap = graph_deploys_names - api_deploys_names

    graph_prov_names = {r["name"] for r in graph.get("provisioned_by", [])}
    api_prov_names = {r.get("name") for r in api_provisioned}
    prov_gap = graph_prov_names - api_prov_names

    h2_pass = not deploys_gap and not prov_gap
    print(
        f"\n  H2: Relationships exist but dropped during resolution"
        f"\n      Graph DEPLOYS_FROM: {graph_deploys_names or '{}'}"
        f"\n      API deploys_from: {api_deploys_names or '{}'}"
        f"\n      Gap: {deploys_gap or 'none'}"
        f"\n      Graph PROVISIONED_BY: {graph_prov_names or '{}'}"
        f"\n      API provisioned_by: {api_prov_names or '{}'}"
        f"\n      Gap: {prov_gap or 'none'}"
        f"\n      Result: {'PASS' if h2_pass else 'FAIL - graph has edges not in API'}"
    )

    # H3: Relationships in graph but not used by story/context
    graph_platforms = graph.get("runs_on_direct", []) + [
        inst
        for inst in graph.get("workload_instances", [])
        if inst.get("platform_kind")
    ]
    api_platform_kinds = {p.get("kind") for p in api_platforms}
    graph_platform_kinds = {
        p.get("kind") or p.get("platform_kind") for p in graph_platforms
    }
    platform_gap = graph_platform_kinds - api_platform_kinds - {None}

    h3_pass = not platform_gap
    print(
        f"\n  H3: Relationships in graph but not in story/context"
        f"\n      Graph platform kinds: {graph_platform_kinds - {None} or '{}'}"
        f"\n      API platform kinds: {api_platform_kinds or '{}'}"
        f"\n      Gap: {platform_gap or 'none'}"
        f"\n      Result: {'PASS' if h3_pass else 'FAIL - graph platforms not in API'}"
    )

    # H4: Coverage/finalization incomplete
    coverage = api.get("context", {}).get("coverage") or {}
    completeness = coverage.get("completeness_state", "unknown")
    finalization_status = coverage.get("finalization_status", "unknown")
    h4_pass = completeness == "complete" and finalization_status == "completed"
    print(
        f"\n  H4: Scan/reindex flow incomplete"
        f"\n      completeness_state: {completeness}"
        f"\n      finalization_status: {finalization_status}"
        f"\n      Result: {'PASS' if h4_pass else 'FAIL - finalization incomplete'}"
    )

    _section("SUMMARY")
    all_pass = h1_pass and h2_pass and h3_pass and h4_pass
    print(f"  H1 (evidence->relationships): {'PASS' if h1_pass else 'FAIL'}")
    print(f"  H2 (resolver drops edges):    {'PASS' if h2_pass else 'FAIL'}")
    print(f"  H3 (query uses all edges):    {'PASS' if h3_pass else 'FAIL'}")
    print(f"  H4 (finalization complete):    {'PASS' if h4_pass else 'FAIL'}")
    print(f"  Overall: {'ALL PASS' if all_pass else 'GAPS FOUND'}")


def main() -> None:
    """Run the evidence promotion trace."""

    parser = argparse.ArgumentParser(description="Trace evidence promotion for one repo")
    parser.add_argument("--repo-name", default="api-node-boats")
    parser.add_argument("--api-url", default="http://localhost:8080/api/v0")
    parser.add_argument("--api-key", default=os.getenv("PCG_E2E_API_KEY", ""))
    parser.add_argument("--output", help="Write JSON report to file")
    args = parser.parse_args()

    headers: dict[str, str] = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    client = httpx.Client(
        base_url=args.api_url.rstrip("/"),
        headers=headers,
        timeout=20.0,
    )

    print(f"Tracing evidence promotion for: {args.repo_name}")
    print(f"API: {args.api_url}")

    session = _neo4j_session()
    try:
        graph_results = trace_graph(session, args.repo_name)
        api_results = trace_api(client, args.repo_name)
        evaluate_hypotheses(graph_results, api_results)

        if args.output:
            report = {
                "repo_name": args.repo_name,
                "graph": _jsonable(graph_results),
                "api": _jsonable(api_results),
            }
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
            print(f"\nJSON report written to {args.output}")
    finally:
        session.close()
        client.close()


def _jsonable(obj: Any) -> Any:
    """Recursively convert neo4j types to JSON-safe values."""

    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(item) for item in obj]
    if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
        return [_jsonable(item) for item in obj]
    return obj


if __name__ == "__main__":
    main()
