"""Tests for ecosystem manifest parser and state management."""

import pytest
from pathlib import Path

from platform_context_graph.core.ecosystem import (
    EcosystemManifest,
    EcosystemRepo,
    EcosystemState,
    RepoIndexState,
    load_state,
    parse_manifest,
    resolve_repo_paths,
    save_state,
    topological_sort_tiers,
)


class TestParseManifest:
    """Test ecosystem manifest parsing."""

    @pytest.fixture(scope="class")
    def manifest_path(self):
        path = (
            Path(__file__).parent.parent.parent
            / "fixtures"
            / "sample_ecosystem"
            / "dependency-graph.yaml"
        )
        if not path.exists():
            pytest.fail(f"Manifest not found at {path}")
        return str(path)

    def test_parse_manifest_returns_manifest(self, manifest_path):
        manifest = parse_manifest(manifest_path)
        assert isinstance(manifest, EcosystemManifest)
        assert manifest.name == "test-platform"
        assert manifest.org == "myorg"

    def test_parse_manifest_tiers(self, manifest_path):
        manifest = parse_manifest(manifest_path)

        assert "infrastructure" in manifest.tiers
        assert "core" in manifest.tiers
        assert "gitops" in manifest.tiers

        infra = manifest.tiers["infrastructure"]
        assert infra.risk_level == "high"
        assert "terraform-stack-monitoring" in infra.repos

        core = manifest.tiers["core"]
        assert core.depends_on == ["infrastructure"]

    def test_parse_manifest_repos(self, manifest_path):
        manifest = parse_manifest(manifest_path)

        assert len(manifest.repos) == 6

        irsa = manifest.repos["terraform-module-core-irsa"]
        assert irsa.tier == "core"
        assert irsa.role == "IRSA IAM role Terraform module"
        assert "terraform-stack-monitoring" in irsa.dependencies

    def test_parse_manifest_key_docs(self, manifest_path):
        manifest = parse_manifest(manifest_path)

        argocd = manifest.repos["iac-eks-argocd"]
        assert "AGENTS.md" in argocd.key_docs

    def test_parse_missing_manifest_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_manifest("/nonexistent/path.yaml")

    def test_parse_invalid_manifest_raises(self, temp_test_dir):
        f = temp_test_dir / "bad.yaml"
        f.write_text("- just a list\n- not a mapping")

        with pytest.raises(ValueError):
            parse_manifest(str(f))


class TestTopologicalSort:
    """Test tier dependency ordering."""

    @pytest.fixture(scope="class")
    def manifest(self):
        path = (
            Path(__file__).parent.parent.parent
            / "fixtures"
            / "sample_ecosystem"
            / "dependency-graph.yaml"
        )
        return parse_manifest(str(path))

    def test_infrastructure_first(self, manifest):
        waves = topological_sort_tiers(manifest)
        assert len(waves) > 0
        assert "infrastructure" in waves[0]

    def test_core_after_infrastructure(self, manifest):
        waves = topological_sort_tiers(manifest)

        infra_wave = next(i for i, w in enumerate(waves) if "infrastructure" in w)
        core_wave = next(i for i, w in enumerate(waves) if "core" in w)
        assert core_wave > infra_wave

    def test_utility_last(self, manifest):
        waves = topological_sort_tiers(manifest)
        utility_wave = next(i for i, w in enumerate(waves) if "utility" in w)
        assert utility_wave == len(waves) - 1

    def test_parallel_tiers_in_same_wave(self, manifest):
        """gitops and xrd both depend on core only."""
        waves = topological_sort_tiers(manifest)
        gitops_wave = next(i for i, w in enumerate(waves) if "gitops" in w)
        xrd_wave = next(i for i, w in enumerate(waves) if "xrd" in w)
        assert gitops_wave == xrd_wave


class TestResolveRepoPaths:
    """Test repo path resolution."""

    def test_resolve_existing_repos(self, temp_test_dir):
        # Create fake repo directories
        (temp_test_dir / "repo-a").mkdir()
        (temp_test_dir / "repo-b").mkdir()

        manifest = EcosystemManifest(
            name="test",
            org="myorg",
            repos={
                "repo-a": EcosystemRepo(name="repo-a", tier="core"),
                "repo-b": EcosystemRepo(name="repo-b", tier="core"),
                "repo-c": EcosystemRepo(name="repo-c", tier="core"),
            },
        )

        paths = resolve_repo_paths(manifest, str(temp_test_dir))

        resolved = temp_test_dir.resolve()
        assert paths["repo-a"] == str(resolved / "repo-a")
        assert paths["repo-b"] == str(resolved / "repo-b")
        assert paths["repo-c"] == ""

    def test_resolve_org_subdir(self, temp_test_dir):
        """Try org/repo-name structure."""
        (temp_test_dir / "myorg" / "repo-x").mkdir(parents=True)

        manifest = EcosystemManifest(
            name="test",
            org="myorg",
            repos={
                "repo-x": EcosystemRepo(name="repo-x", tier="core"),
            },
        )

        paths = resolve_repo_paths(manifest, str(temp_test_dir))
        resolved = temp_test_dir.resolve()
        assert paths["repo-x"] == str(resolved / "myorg" / "repo-x")


class TestEcosystemState:
    """Test state persistence."""

    def test_save_and_load_state(self, temp_test_dir, monkeypatch):
        # Monkeypatch the state file location
        state_file = temp_test_dir / "ecosystem-state.json"
        import platform_context_graph.core.ecosystem as eco_mod

        monkeypatch.setattr(eco_mod, "_STATE_DIR", temp_test_dir)
        monkeypatch.setattr(eco_mod, "_STATE_FILE", state_file)

        state = EcosystemState(
            manifest_path="/some/path.yaml",
            repos={
                "test-repo": RepoIndexState(
                    name="test-repo",
                    last_indexed_commit="abc123",
                    status="indexed",
                    file_count=42,
                ),
            },
        )

        save_state(state)
        assert state_file.exists()

        loaded = load_state()
        assert loaded.manifest_path == "/some/path.yaml"
        assert "test-repo" in loaded.repos
        assert loaded.repos["test-repo"].status == "indexed"
        assert loaded.repos["test-repo"].file_count == 42

    def test_load_state_missing_file(self, temp_test_dir, monkeypatch):
        import platform_context_graph.core.ecosystem as eco_mod

        monkeypatch.setattr(
            eco_mod,
            "_STATE_FILE",
            temp_test_dir / "nonexistent.json",
        )

        state = load_state()
        assert isinstance(state, EcosystemState)
        assert len(state.repos) == 0
