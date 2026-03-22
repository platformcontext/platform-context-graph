from __future__ import annotations

from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"
HOME_DOC = DOCS_ROOT / "docs" / "index.md"
QUICKSTART_DOC = DOCS_ROOT / "docs" / "getting-started" / "quickstart.md"
DEPLOY_OVERVIEW_DOC = DOCS_ROOT / "docs" / "deployment" / "overview.md"
MCP_GUIDE_DOC = DOCS_ROOT / "docs" / "guides" / "mcp-guide.md"
HTTP_API_DOC = DOCS_ROOT / "docs" / "reference" / "http-api.md"
SHARED_INFRA_GUIDE = DOCS_ROOT / "docs" / "guides" / "shared-infra-trace.md"
MKDOCS_CONFIG = DOCS_ROOT / "mkdocs.yml"
PROMPTS_FILE = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "platform_context_graph"
    / "prompts.py"
)


def test_docs_pages_and_nav_cover_http_api_and_shared_infra() -> None:
    assert HOME_DOC.exists()
    assert QUICKSTART_DOC.exists()
    assert DEPLOY_OVERVIEW_DOC.exists()
    assert MCP_GUIDE_DOC.exists()
    assert HTTP_API_DOC.exists()
    assert SHARED_INFRA_GUIDE.exists()

    mkdocs = MKDOCS_CONFIG.read_text()
    assert "getting-started/quickstart.md" in mkdocs
    assert "deployment/overview.md" in mkdocs
    assert "guides/mcp-guide.md" in mkdocs
    assert "reference/http-api.md" in mkdocs
    assert "guides/shared-infra-trace.md" in mkdocs

    landing = HOME_DOC.read_text()
    assert "Code-to-cloud context graph" in landing
    assert "Get Started" in landing
    assert "Deploy" in landing
    assert "HTTP API" in landing
    assert "MCP" in landing

    http_api = HTTP_API_DOC.read_text()
    assert "/api/v0/entities/resolve" in http_api
    assert "/api/v0/workloads/{id}/context" in http_api
    assert "/api/v0/services/{id}/context" in http_api
    assert "/api/v0/code/search" in http_api
    assert "/api/v0/infra/resources/search" in http_api
    assert "/api/v0/repositories" in http_api
    assert "/api/v0/openapi.json" in http_api

    shared_infra = SHARED_INFRA_GUIDE.read_text()
    assert "shared RDS" in shared_infra
    assert "Terraform" in shared_infra
    assert "workload" in shared_infra
    assert "service alias" in shared_infra


def test_prompt_guidance_mentions_http_api_and_context_queries() -> None:
    prompts = PROMPTS_FILE.read_text()

    assert "resolve_entity" in prompts
    assert "get_workload_context" in prompts
    assert "get_service_context" in prompts
    assert "HTTP API" in prompts
