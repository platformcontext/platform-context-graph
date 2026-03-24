from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.graph_builder import GraphBuilder
from platform_context_graph.tools.graph_builder_indexing_discovery import (
    resolve_repository_file_sets,
)
from platform_context_graph.tools.graph_builder_indexing_execution import (
    build_graph_from_path_async as legacy_build_graph_from_path_async,
)


def _make_builder() -> GraphBuilder:
    builder = GraphBuilder.__new__(GraphBuilder)
    builder.parsers = {
        ".py": object(),
        ".tf": object(),
    }
    builder.add_repository_to_graph = MagicMock()
    builder.add_file_to_graph = MagicMock()
    builder.parse_file = MagicMock(
        side_effect=lambda repo_path, file_path, is_dependency: {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "functions": [],
            "classes": [],
            "imports": [],
            "variables": [],
        }
    )
    builder._pre_scan_for_imports = MagicMock(return_value={})
    builder._create_all_inheritance_links = MagicMock()
    builder._create_all_function_calls = MagicMock()
    builder._create_all_infra_links = MagicMock()
    builder._materialize_workloads = MagicMock(return_value={})
    return builder


def _config_value(key: str) -> str | None:
    if key == "IGNORE_DIRS":
        return ".terraform,.terragrunt-cache,.pulumi,.crossplane,.serverless,.aws-sam,cdk.out,.terramate-cache,node_modules"
    if key == "PCG_HONOR_GITIGNORE":
        return "true"
    if key == "SCIP_INDEXER":
        return "false"
    return None


def test_estimate_processing_time_skips_hidden_and_ignored_directories(
    tmp_path: Path, monkeypatch
):
    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("print('root')\n")
    (tmp_path / "infra.tf").write_text('resource "null_resource" "visible" {}\n')

    terragrunt_file = tmp_path / ".terragrunt-cache" / "hash" / "module" / "main.tf"
    terragrunt_file.parent.mkdir(parents=True)
    terragrunt_file.write_text('resource "null_resource" "cached" {}\n')

    terraform_file = tmp_path / ".terraform" / "modules" / "cached.tf"
    terraform_file.parent.mkdir(parents=True)
    terraform_file.write_text('resource "null_resource" "cached" {}\n')

    pulumi_file = tmp_path / ".pulumi" / "stacks" / "stack.tf"
    pulumi_file.parent.mkdir(parents=True)
    pulumi_file.write_text('resource "null_resource" "pulumi" {}\n')

    crossplane_file = tmp_path / ".crossplane" / "cache" / "resource.yaml"
    crossplane_file.parent.mkdir(parents=True)
    crossplane_file.write_text("apiVersion: v1\nkind: ConfigMap\n")

    cdk_file = tmp_path / "cdk.out" / "manifest.tf"
    cdk_file.parent.mkdir(parents=True)
    cdk_file.write_text('resource "null_resource" "cdk" {}\n')

    hidden_python = tmp_path / ".hidden" / "hidden.py"
    hidden_python.parent.mkdir(parents=True)
    hidden_python.write_text("print('hidden')\n")

    total_files, estimated_time = builder.estimate_processing_time(tmp_path)

    assert total_files == 2
    assert estimated_time == 0.1


def test_build_graph_from_path_async_skips_hidden_cache_repos_but_keeps_visible_git_repos(
    tmp_path: Path, monkeypatch
):
    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    async def immediate_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.asyncio.sleep", immediate_sleep
    )

    (tmp_path / ".git").mkdir()

    root_file = tmp_path / "service.py"
    root_file.write_text("print('root')\n")

    nested_repo = tmp_path / "packages" / "nested-service"
    (nested_repo / ".git").mkdir(parents=True)
    nested_file = nested_repo / "worker.py"
    nested_file.write_text("print('nested')\n")

    cache_repo = tmp_path / ".generated-cache" / "abc123" / "module"
    (cache_repo / ".git").mkdir(parents=True)
    cached_file = cache_repo / "generated.py"
    cached_file.write_text("print('cached')\n")

    asyncio.run(
        legacy_build_graph_from_path_async(
            builder,
            tmp_path,
            False,
            None,
            asyncio_module=asyncio,
            datetime_cls=SimpleNamespace(now=lambda: None),
            debug_log_fn=lambda *_args, **_kwargs: None,
            error_logger_fn=lambda *_args, **_kwargs: None,
            get_config_value_fn=_config_value,
            info_logger_fn=lambda *_args, **_kwargs: None,
            pathspec_module=__import__("pathspec"),
            warning_logger_fn=lambda *_args, **_kwargs: None,
            job_status_enum=SimpleNamespace(
                COMPLETED="completed",
                FAILED="failed",
                CANCELLED="cancelled",
                RUNNING="running",
            ),
        )
    )

    indexed_repos = {
        call.args[0].resolve()
        for call in builder.add_repository_to_graph.call_args_list
    }
    indexed_files = {
        Path(call.args[0]["path"]).resolve()
        for call in builder.add_file_to_graph.call_args_list
    }

    assert indexed_repos == {tmp_path.resolve(), nested_repo.resolve()}
    assert indexed_files == {root_file.resolve(), nested_file.resolve()}
    assert cached_file.resolve() not in indexed_files


def test_resolve_repository_file_sets_honors_repo_local_gitignore_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each repo should honor only its own .gitignore, not workspace parents."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo_a = workspace / "repo-a"
    repo_b = workspace / "repo-b"
    (workspace / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    (repo_a / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (repo_b / ".gitignore").write_text("skip.py\n", encoding="utf-8")

    kept_a = repo_a / "kept.py"
    ignored_a = repo_a / "ignored.py"
    kept_b = repo_b / "kept.py"
    ignored_b = repo_b / "skip.py"
    for path in (kept_a, ignored_a, kept_b, ignored_b):
        path.write_text("print('x')\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        workspace,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert repo_file_sets == {
        repo_a.resolve(): [kept_a.resolve()],
        repo_b.resolve(): [kept_b.resolve()],
    }


def test_resolve_repository_file_sets_honors_nested_gitignore_negation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nested .gitignore files should apply only within their subtrees."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "generated"
    nested.mkdir()
    (nested / ".gitignore").write_text("*\n!keep.py\n", encoding="utf-8")

    kept = nested / "keep.py"
    dropped = nested / "drop.py"
    outside = repo / "outside.py"
    for path in (kept, dropped, outside):
        path.write_text("print('x')\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert set(repo_file_sets) == {repo.resolve()}
    assert set(repo_file_sets[repo.resolve()]) == {
        outside.resolve(),
        kept.resolve(),
    }


def test_build_graph_from_path_async_explicit_file_bypasses_gitignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct single-file indexing should remain an explicit override."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    async def immediate_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.asyncio.sleep", immediate_sleep
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    ignored_file = repo / "ignored.py"
    ignored_file.write_text("print('override')\n", encoding="utf-8")

    asyncio.run(
        legacy_build_graph_from_path_async(
            builder,
            ignored_file,
            False,
            None,
            asyncio_module=asyncio,
            datetime_cls=SimpleNamespace(now=lambda: None),
            debug_log_fn=lambda *_args, **_kwargs: None,
            error_logger_fn=lambda *_args, **_kwargs: None,
            get_config_value_fn=_config_value,
            info_logger_fn=lambda *_args, **_kwargs: None,
            pathspec_module=__import__("pathspec"),
            warning_logger_fn=lambda *_args, **_kwargs: None,
            job_status_enum=SimpleNamespace(
                COMPLETED="completed",
                FAILED="failed",
                CANCELLED="cancelled",
                RUNNING="running",
            ),
        )
    )

    indexed_files = {
        Path(call.args[0]["path"]).resolve()
        for call in builder.add_file_to_graph.call_args_list
    }

    assert indexed_files == {ignored_file.resolve()}


def test_build_graph_from_path_async_uses_checkpointed_coordinator_for_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _make_builder()
    recorded: dict[str, object] = {}

    async def fake_execute_index_run(
        builder_arg,
        path,
        *,
        is_dependency,
        job_id,
        selected_repositories,
        family,
        source,
        force,
        component,
        **_kwargs,
    ):
        recorded.update(
            {
                "builder": builder_arg,
                "path": path,
                "is_dependency": is_dependency,
                "job_id": job_id,
                "selected_repositories": selected_repositories,
                "family": family,
                "source": source,
                "force": force,
                "component": component,
            }
        )
        return SimpleNamespace(status="completed")

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.execute_index_run",
        fake_execute_index_run,
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.raise_for_failed_index_run",
        lambda result: recorded.setdefault("result", result),
    )

    asyncio.run(
        builder.build_graph_from_path_async(
            tmp_path,
            force=True,
            family="bootstrap",
            source="githubOrg",
            component="bootstrap-index",
        )
    )

    assert recorded["builder"] is builder
    assert recorded["path"] == tmp_path
    assert recorded["family"] == "bootstrap"
    assert recorded["source"] == "githubOrg"
    assert recorded["force"] is True
    assert recorded["component"] == "bootstrap-index"


def test_graph_builder_create_all_function_calls_returns_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The GraphBuilder wrapper should return finalization call metrics."""

    import platform_context_graph.tools.graph_builder as graph_builder_module

    builder = GraphBuilder.__new__(GraphBuilder)
    expected = {
        "contextual_exact_duration_seconds": 1.0,
        "contextual_fallback_duration_seconds": 2.0,
        "file_level_exact_duration_seconds": 3.0,
        "file_level_fallback_duration_seconds": 4.0,
        "total_duration_seconds": 10.0,
    }

    monkeypatch.setattr(
        graph_builder_module,
        "_create_all_function_calls",
        lambda *_args, **_kwargs: expected,
    )

    metrics = builder._create_all_function_calls([], {})

    assert metrics is expected


def test_collect_supported_files_records_hidden_directory_skip_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from platform_context_graph import observability

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    observability.initialize_observability(
        component="bootstrap-index",
        metric_reader=metric_reader,
        span_exporter=InMemorySpanExporter(),
    )

    (tmp_path / "app.py").write_text("print('root')\n")
    hidden_python = tmp_path / ".hidden" / "hidden.py"
    hidden_python.parent.mkdir(parents=True)
    hidden_python.write_text("print('hidden')\n")
    terraform_file = tmp_path / ".terraform" / "modules" / "cached.tf"
    terraform_file.parent.mkdir(parents=True)
    terraform_file.write_text('resource "null_resource" "cached" {}\n')
    pulumi_file = tmp_path / ".pulumi" / "stacks" / "cached.tf"
    pulumi_file.parent.mkdir(parents=True)
    pulumi_file.write_text('resource "null_resource" "cached" {}\n')
    cdk_file = tmp_path / "cdk.out" / "cached.tf"
    cdk_file.parent.mkdir(parents=True)
    cdk_file.write_text('resource "null_resource" "cached" {}\n')

    files = builder._collect_supported_files(tmp_path)

    assert files == [tmp_path / "app.py"]
    metrics_data = metric_reader.get_metrics_data()
    points = []
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                for point in metric.data.data_points:
                    points.append(
                        (
                            metric.name,
                            dict(point.attributes),
                            getattr(point, "value", None),
                        )
                    )

    assert any(
        metric_name == "pcg_hidden_dirs_skipped_total"
        and attrs.get("kind") == ".terraform"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_hidden_dirs_skipped_total"
        and attrs.get("kind") == ".pulumi"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_hidden_dirs_skipped_total"
        and attrs.get("kind") == "cdk.out"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_hidden_dirs_skipped_total" and attrs.get("kind") == "hidden"
        for metric_name, attrs, _value in points
    )


def test_collect_supported_files_includes_raw_text_iac_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery should include searchable raw-text IaC files, not just parser suffixes."""

    builder = _make_builder()
    builder.parsers.update(
        {
            ".j2": object(),
            ".tpl": object(),
            ".conf": object(),
            "__dockerfile__": object(),
        }
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")
    apache_template = tmp_path / "roles" / "apache" / "templates" / "site.conf.j2"
    apache_template.parent.mkdir(parents=True)
    apache_template.write_text("ServerName {{ host_name }}\n", encoding="utf-8")
    terraform_template = tmp_path / "templates" / "dashboard.tpl"
    terraform_template.parent.mkdir(parents=True)
    terraform_template.write_text('{"region":"${aws_region}"}\n', encoding="utf-8")
    python_file = tmp_path / "app.py"
    python_file.write_text("print('ok')\n", encoding="utf-8")
    ignored = tmp_path / "README.md"
    ignored.write_text("# docs\n", encoding="utf-8")

    files = builder._collect_supported_files(tmp_path)

    assert files == [
        dockerfile,
        python_file,
        apache_template,
        terraform_template,
    ]


def test_add_repository_to_graph_persists_remote_first_repository_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    builder = GraphBuilder.__new__(GraphBuilder)
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value=None)),
        MagicMock(single=MagicMock(return_value=None)),
        None,
    ]
    builder.driver = MagicMock()
    builder.driver.session.return_value = session

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.git_remote_for_path",
        lambda _path: "git@github.com:platformcontext/payments-api.git",
    )

    builder.add_repository_to_graph(repo_path)

    query = session.run.call_args_list[-1].args[0]
    params = session.run.call_args_list[-1].kwargs

    assert "CREATE (r:Repository {path: $repo_path})" in query
    assert "SET r.id = $repo_id" in query
    assert params["repo_id"].startswith("repository:r_")
    assert params["name"] == "payments-api"
    assert params["local_path"] == str(repo_path.resolve())
    assert params["repo_path"] == str(repo_path.resolve())
    assert params["remote_url"] == "https://github.com/platformcontext/payments-api"
    assert params["repo_slug"] == "platformcontext/payments-api"
    assert params["has_remote"] is True


def test_add_repository_to_graph_adopts_existing_path_only_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Promote an existing path-keyed repository node to the canonical ID."""

    builder = GraphBuilder.__new__(GraphBuilder)
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value={"id": None})),
        None,
    ]
    builder.driver = MagicMock()
    builder.driver.session.return_value = session

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.git_remote_for_path",
        lambda _path: "git@github.com:platformcontext/payments-api.git",
    )

    builder.add_repository_to_graph(repo_path)

    assert session.run.call_count == 2
    lookup_query = session.run.call_args_list[0].args[0]
    update_query = session.run.call_args_list[1].args[0]
    params = session.run.call_args_list[1].kwargs

    assert "MATCH (r:Repository {path: $repo_path})" in lookup_query
    assert "WHERE r.path = $repo_path OR r.id = $repo_id" in update_query
    assert params["repo_id"].startswith("repository:r_")
    assert params["repo_path"] == str(repo_path.resolve())
