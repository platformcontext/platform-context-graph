from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.graph_builder import GraphBuilder
from platform_context_graph.collectors.git.discovery import (
    resolve_repository_file_sets,
)
from platform_context_graph.collectors.git.execution import (
    build_graph_from_path_async,
)


def _make_builder() -> GraphBuilder:
    builder = GraphBuilder.__new__(GraphBuilder)
    builder.parsers = {
        ".py": object(),
        ".js": object(),
        ".php": object(),
        ".tf": object(),
        ".yaml": object(),
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
        return (
            "venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__"
        )
    if key == "PCG_IGNORE_DEPENDENCY_DIRS":
        return "true"
    if key == "PCG_HONOR_GITIGNORE":
        return "true"
    if key == "SCIP_INDEXER":
        return "false"
    return None


def _config_value_include_hidden(key: str) -> str | None:
    if key == "IGNORE_HIDDEN_FILES":
        return "false"
    return _config_value(key)


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


def test_collect_supported_files_includes_hidden_workflow_dirs_when_config_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value",
        _config_value_include_hidden,
    )

    visible_python = tmp_path / "app.py"
    visible_python.write_text("print('root')\n", encoding="utf-8")
    hidden_workflow = tmp_path / ".github" / "workflows" / "deploy.yaml"
    hidden_workflow.parent.mkdir(parents=True)
    hidden_workflow.write_text("name: deploy\n", encoding="utf-8")
    ignored_git = tmp_path / ".git" / "config"
    ignored_git.parent.mkdir(parents=True)
    ignored_git.write_text("[core]\n", encoding="utf-8")

    files = builder._collect_supported_files(tmp_path)

    assert set(files) == {hidden_workflow, visible_python}


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
        build_graph_from_path_async(
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


def test_resolve_repository_file_sets_excludes_dependency_roots_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built-in dependency roots should be excluded before parse and storage."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    app_file = repo / "src" / "app.py"
    vendor_file = repo / "vendor" / "pkg" / "client.php"
    node_modules_file = repo / "node_modules" / "react" / "index.js"
    bundle_file = repo / "vendor" / "bundle" / "ruby" / "lib.rb"
    for path in (app_file, vendor_file, node_modules_file, bundle_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('x')\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert repo_file_sets == {repo.resolve(): [app_file.resolve()]}


def test_resolve_repository_file_sets_can_include_dependency_roots_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dependency-root exclusion policy should be deploy-configurable."""

    builder = _make_builder()

    def config_value(key: str) -> str | None:
        if key == "PCG_IGNORE_DEPENDENCY_DIRS":
            return "false"
        return _config_value(key)

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value",
        config_value,
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    app_file = repo / "src" / "app.py"
    vendor_file = repo / "vendor" / "pkg" / "client.php"
    node_modules_file = repo / "node_modules" / "react" / "index.js"
    for path in (app_file, vendor_file, node_modules_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('x')\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert set(repo_file_sets[repo.resolve()]) == {
        app_file.resolve(),
        node_modules_file.resolve(),
        vendor_file.resolve(),
    }


def test_resolve_repository_file_sets_keeps_helm_charts_indexed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Helm charts should remain indexed because they can be first-party."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    app_file = repo / "app.py"
    chart_file = repo / "charts" / "payments" / "templates" / "deployment.yaml"
    vendor_file = repo / "vendor" / "pkg" / "client.php"
    for path in (app_file, chart_file, vendor_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kind: ConfigMap\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert set(repo_file_sets[repo.resolve()]) == {
        app_file.resolve(),
        chart_file.resolve(),
    }


def test_resolve_repository_file_sets_ignores_dependency_roots_relative_to_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parent path segments should not make an entire repo look vendored."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    repo = tmp_path / "vendor" / "repo"
    (repo / ".git").mkdir(parents=True)

    app_file = repo / "src" / "app.py"
    nested_vendor_file = repo / "vendor" / "pkg" / "client.php"
    for path in (app_file, nested_vendor_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('x')\n", encoding="utf-8")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=None,
        pathspec_module=__import__("pathspec"),
    )

    assert repo_file_sets == {repo.resolve(): [app_file.resolve()]}


def test_build_graph_from_path_async_explicit_file_bypasses_gitignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct single-file indexing should stay explicit but route to Go runtime."""

    builder = _make_builder()
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.run_go_bootstrap_index",
        lambda path, *, selected_repositories=None, force=False, is_dependency=False: recorded.update(
            {
                "path": path,
                "selected_repositories": selected_repositories,
                "force": force,
                "is_dependency": is_dependency,
            }
        ),
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    ignored_file = repo / "ignored.py"
    ignored_file.write_text("print('override')\n", encoding="utf-8")

    asyncio.run(
        builder.build_graph_from_path_async(
            ignored_file,
            is_dependency=False,
            force=True,
            family="bootstrap",
            source="githubOrg",
            component="bootstrap-index",
        )
    )

    assert recorded["path"] == ignored_file
    assert recorded["selected_repositories"] is None
    assert recorded["force"] is True
    assert recorded["is_dependency"] is False


def test_build_graph_from_path_async_uses_go_bootstrap_runtime_for_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _make_builder()
    recorded: dict[str, object] = {}

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.run_go_bootstrap_index",
        lambda path, *, selected_repositories=None, force=False, is_dependency=False: recorded.update(
            {
                "path": path,
                "selected_repositories": selected_repositories,
                "force": force,
                "is_dependency": is_dependency,
            }
        ),
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

    assert recorded["path"] == tmp_path
    assert recorded["force"] is True
    assert recorded["selected_repositories"] is None
    assert recorded["is_dependency"] is False


def test_build_graph_from_path_async_routes_dependency_directories_to_go_bootstrap_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _make_builder()
    recorded: dict[str, object] = {}
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.run_go_bootstrap_index",
        lambda path, *, selected_repositories=None, force=False, is_dependency=False: recorded.update(
            {
                "path": path,
                "selected_repositories": selected_repositories,
                "force": force,
                "is_dependency": is_dependency,
            }
        ),
    )

    asyncio.run(
        builder.build_graph_from_path_async(
            tmp_path,
            is_dependency=True,
            force=True,
            family="bootstrap",
            source="githubOrg",
            component="bootstrap-index",
        )
    )

    assert recorded["path"] == tmp_path
    assert recorded["is_dependency"] is True
    assert recorded["force"] is True
    assert recorded["selected_repositories"] is None


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
    session.execute_write.side_effect = lambda callback: callback(session)
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
    params = session.run.call_args_list[-1].kwargs["parameters"]

    assert "MERGE (r:Repository {id: $repo_id})" in query
    assert "ON CREATE SET r.path = $repo_path" in query
    assert "ON MATCH SET r.path = $repo_path" in query
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
    session.execute_write.side_effect = lambda callback: callback(session)
    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value={"existing_id": None})),
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

    assert session.run.call_count == 3
    lookup_query = session.run.call_args_list[0].args[0]
    update_query = session.run.call_args_list[2].args[0]
    params = session.run.call_args_list[2].kwargs["parameters"]

    assert "MATCH (r:Repository {path: $repo_path})" in lookup_query
    assert "MATCH (r:Repository {path: $repo_path})" in update_query
    assert "SET r.id = $repo_id" in update_query
    assert params["repo_id"].startswith("repository:r_")
    assert params["repo_path"] == str(repo_path.resolve())


def test_add_repository_to_graph_reconciles_legacy_path_only_repository_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy path-only repository nodes should be merged into the canonical node."""

    builder = GraphBuilder.__new__(GraphBuilder)
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.execute_write.side_effect = lambda callback: callback(session)
    session.run.side_effect = [
        MagicMock(single=MagicMock(return_value={"existing_id": None})),
        MagicMock(
            single=MagicMock(
                return_value={"existing_path": str((tmp_path / "other").resolve())}
            )
        ),
        *([None] * 32),
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

    queries = [call.args[0] for call in session.run.call_args_list]

    assert any(
        "MERGE (winner)-[merged:REPO_CONTAINS]->(target)" in query for query in queries
    )
    assert any(
        "MERGE (winner)-[merged:CONTAINS]->(target)" in query for query in queries
    )
    assert any("DETACH DELETE loser" in query for query in queries)
    assert any("SET winner.path = $repo_path" in query for query in queries)


def test_add_repository_to_graph_rejects_path_and_id_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conflicting canonical identities should still fail with a clear error."""

    builder = GraphBuilder.__new__(GraphBuilder)
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.execute_write.side_effect = lambda callback: callback(session)
    session.run.side_effect = [
        MagicMock(
            single=MagicMock(
                return_value={"existing_id": "repository:r_previous_checkout"}
            )
        ),
        MagicMock(
            single=MagicMock(
                return_value={"existing_path": str((tmp_path / "other").resolve())}
            )
        ),
    ]
    builder.driver = MagicMock()
    builder.driver.session.return_value = session

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.git_remote_for_path",
        lambda _path: "git@github.com:platformcontext/payments-api.git",
    )

    with pytest.raises(RuntimeError, match="Repository identity conflict"):
        builder.add_repository_to_graph(repo_path)
