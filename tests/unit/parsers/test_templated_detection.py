"""Tests for shared templated-file dialect detection."""

from pathlib import Path

from platform_context_graph.parsers.languages import templated_detection


def test_classify_helm_template_yaml_returns_go_template() -> None:
    """Helm template YAML should classify as Go-template YAML."""

    classification = templated_detection.classify_file(
        root_family="helm_argo",
        relative_path=Path("chart/templates/statefulset.yaml"),
        content=(
            "{{- if .Values.repoSync.enabled }}\n"
            "kind: StatefulSet\n"
            'metadata:\n  name: {{ include "pcg.fullname" . }}\n'
            "{{- end }}\n"
        ),
    )

    assert classification.bucket == "go_template_yaml"
    assert classification.dialects == ("go_template",)
    assert classification.ambiguous is False


def test_classify_plain_yaml_in_helm_root_stays_plain() -> None:
    """Ordinary YAML in a Helm-family repo should not become templated by comments."""

    classification = templated_detection.classify_file(
        root_family="helm_argo",
        relative_path=Path("argocd/base/function.yaml"),
        content=(
            "# Verify all required fields exist before installation.\n"
            "apiVersion: pkg.crossplane.io/v1\n"
            "kind: Function\n"
        ),
    )

    assert classification.bucket == "plain_yaml"
    assert classification.dialects == ()
    assert classification.marker_count == 0


def test_classify_ansible_yaml_returns_jinja() -> None:
    """Ansible-style YAML should classify as Jinja-family YAML."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("deploy.yml"),
        content="hosts: \"{{ env | default('qa') }}\"\n",
    )

    assert classification.bucket == "jinja_yaml"
    assert classification.dialects == ("jinja",)


def test_classify_ansible_quote_filter_stays_jinja() -> None:
    """Ansible `|quote` filters should not be mistaken for Go-template helpers."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("tasks/main.yml"),
        content="command: 'echo {{ host_name|quote }} > /etc/hostname'\n",
    )

    assert classification.bucket == "jinja_yaml"
    assert classification.dialects == ("jinja",)
    assert classification.ambiguous is False


def test_classify_ansible_indent_filter_stays_jinja() -> None:
    """Jinja `indent` filters should not be treated as Go-template helpers."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("tasks/main.yml"),
        content='content: "{{ payload | indent(2) }}"\n',
    )

    assert classification.bucket == "jinja_yaml"
    assert classification.dialects == ("jinja",)
    assert classification.ambiguous is False


def test_classify_terraform_hcl_splits_plain_and_templated() -> None:
    """Terraform HCL should distinguish plain from templated files."""

    plain = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path("modules/example/main.tf"),
        content='resource "aws_s3_bucket" "this" {}\n',
    )
    templated = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path("modules/example/main.tf"),
        content='resource "aws_s3_bucket" "this" { bucket = "${var.bucket_name}" }\n',
    )

    assert plain.bucket == "terraform_hcl"
    assert templated.bucket == "terraform_hcl_templated"
    assert templated.dialects == ("terraform_template",)


def test_classify_github_actions_yaml_avoids_plain_yaml_false_negative() -> None:
    """GitHub Actions `${{ ... }}` YAML should not disappear into plain YAML."""

    classification = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path(".github/workflows/ci.yaml"),
        content=(
            "concurrency:\n"
            "  group: ${{ github.workflow }}-${{ github.ref }}\n"
            "jobs:\n"
            "  terraform:\n"
            "    with:\n"
            "      working-directory: environments/${{ matrix.organization }}\n"
        ),
    )

    assert classification.bucket == "unknown_templated"
    assert classification.dialects == ("github_actions",)
    assert classification.ambiguous is False
    assert classification.renderability_hint == "context_required"


def test_classify_terraform_docs_yaml_detects_go_template_context() -> None:
    """Go-template dot-context in YAML should classify without staying ambiguous."""

    classification = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path(".terraform-docs.yml"),
        content=(
            "output:\n"
            "  template: |-\n"
            "    <!-- BEGIN_TF_DOCS -->\n"
            "    {{ .Content }}\n"
            "    <!-- END_TF_DOCS -->\n"
        ),
    )

    assert classification.bucket == "go_template_yaml"
    assert classification.dialects == ("go_template",)
    assert classification.ambiguous is False


def test_classify_jinja_text_template_keeps_dialect_without_forcing_yaml() -> None:
    """Jinja text templates should keep their dialect even outside YAML suffixes."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("roles/web/templates/site.conf.j2"),
        content=(
            "{% if enabled -%}\n" "server_name {{ host_name }};\n" "{% endif -%}\n"
        ),
    )

    assert classification.bucket == "unknown_templated"
    assert classification.dialects == ("jinja_template",)
    assert classification.ambiguous is False
    assert classification.renderability_hint == "context_required"


def test_classify_yaml_jinja_template_suffix_prefers_jinja_yaml() -> None:
    """Multi-suffix YAML templates like `*.yml.j2` should stay in the YAML bucket."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("roles/newrelic/templates/newrelic.yml.j2"),
        content='license_key: "{{ newrelic_license_key }}"\n',
    )

    assert classification.bucket == "jinja_yaml"
    assert classification.dialects == ("jinja",)
    assert classification.ambiguous is False


def test_classify_terraform_jinja_extension_prefers_terraform_template() -> None:
    """Terraform `template_file` inputs may use `.jinja` names with `${...}` syntax."""

    classification = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path("modules/node/service/templates/default.jinja"),
        content='{"name": "${name}", "cpu": ${cpu}}\n',
    )

    assert classification.bucket == "unknown_templated"
    assert classification.dialects == ("terraform_template",)
    assert classification.ambiguous is False
    assert classification.renderability_hint == "context_required"


def test_classify_dockerfile_marks_raw_ingest_gap() -> None:
    """Dockerfiles should be flagged as raw-ingest candidates and IaC-relevant."""

    classification = templated_detection.classify_file(
        root_family="generic",
        relative_path=Path("Dockerfile"),
        content="FROM python:3.12-slim\nRUN pip install -r requirements.txt\n",
    )

    assert classification.bucket == "plain_text"
    assert classification.artifact_type == "dockerfile"
    assert classification.raw_ingest_candidate is True
    assert classification.iac_relevant is True


def test_classify_apache_conf_template_marks_raw_ingest_gap() -> None:
    """Apache configs should be surfaced as IaC-relevant raw-text candidates."""

    classification = templated_detection.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("roles/apache/templates/sites-available/boattrader.conf.j2"),
        content="ServerName {{ host_name }}\n",
    )

    assert classification.bucket == "unknown_templated"
    assert classification.artifact_type == "apache_config_template"
    assert classification.raw_ingest_candidate is True
    assert classification.iac_relevant is True


def test_infer_content_metadata_detects_nginx_template_from_content() -> None:
    """Config templates with Nginx directives should persist Nginx metadata."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("roles/web/templates/site.conf.j2"),
        content=(
            "{% if enabled -%}\n"
            "server {\n"
            "    location / {\n"
            "        proxy_pass http://backend;\n"
            "    }\n"
            "}\n"
            "{% endif -%}\n"
        ),
    )

    assert metadata.artifact_type == "nginx_config_template"
    assert metadata.template_dialect == "jinja"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_detects_repo_root_nginx_template() -> None:
    """Repo-root-relative config templates should still keep templated Nginx metadata."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("site.conf.j2"),
        content=(
            "{% if enabled -%}\n"
            "server {\n"
            "    location / {\n"
            "        proxy_pass http://backend;\n"
            "    }\n"
            "}\n"
            "{% endif -%}\n"
        ),
    )

    assert metadata.artifact_type == "nginx_config_template"
    assert metadata.template_dialect == "jinja"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_detects_terraform_template_with_jinja_suffix() -> None:
    """Production metadata inference should treat `${...}` `.jinja` templates as Terraform."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("modules/node/service/templates/default.jinja"),
        content='{"name": "${name}", "cpu": ${cpu}}\n',
    )

    assert metadata.artifact_type == "terraform_template_text"
    assert metadata.template_dialect == "terraform_template"
    assert metadata.iac_relevant is True


def test_classify_terraform_tpl_keeps_template_dialect() -> None:
    """Terraform `.tpl` files should not collapse into dialect-free unknown files."""

    classification = templated_detection.classify_file(
        root_family="terraform",
        relative_path=Path("modules/app/templates/cloudwatch/dashboard.tpl"),
        content=(
            "{\n"
            '  "region": "${aws_region}",\n'
            '  "metrics": ${jsonencode([for arn in arns : arn])}\n'
            "}\n"
        ),
    )

    assert classification.bucket == "unknown_templated"
    assert classification.dialects == ("terraform_template",)
    assert classification.ambiguous is False
    assert classification.renderability_hint == "context_required"


def test_classify_mixed_markers_returns_unknown_templated() -> None:
    """Mixed Go-template and Jinja markers should fail closed as ambiguous."""

    classification = templated_detection.classify_file(
        root_family="generic",
        relative_path=Path("mixed.yaml"),
        content=(
            "name: {{ repo_name }}\n"
            "{% if enabled %}\n"
            "key: value\n"
            "{% endif %}\n"
        ),
    )

    assert classification.bucket == "unknown_templated"
    assert classification.ambiguous is True
    assert classification.dialects == ("go_template", "jinja")


def test_infer_content_metadata_for_helm_helper_tpl() -> None:
    """Production metadata should recognize Helm helper templates by path alone."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("chart/templates/_helpers.tpl"),
        content='{{- define "pcg.fullname" -}}pcg{{- end -}}\n',
    )

    assert metadata.artifact_type == "helm_helper_tpl"
    assert metadata.template_dialect == "go_template"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_for_repo_root_helm_helper_tpl() -> None:
    """Repo-root-relative Helm helpers should infer Helm metadata without `chart/`."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("templates/_helpers.tpl"),
        content='{{- define "pcg.fullname" -}}pcg{{- end -}}\n',
    )

    assert metadata.artifact_type == "helm_helper_tpl"
    assert metadata.template_dialect == "go_template"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_for_jinja_yaml() -> None:
    """Production metadata should classify Jinja YAML without inventory root input."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("assets/data_quality/analytics_checks.yaml"),
        content=(
            "{% set portals = ['portal-alpha', 'portal-beta'] %}\n"
            "checks: {{ portals | tojson }}\n"
        ),
    )

    assert metadata.artifact_type == "jinja_yaml"
    assert metadata.template_dialect == "jinja"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_for_templated_dockerfile() -> None:
    """Templated Dockerfiles should preserve Dockerfile artifact type plus dialect."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("roles/builder/templates/Dockerfile.j2"),
        content="FROM {{ docker_image }} as builder\n",
    )

    assert metadata.artifact_type == "dockerfile"
    assert metadata.template_dialect == "jinja"
    assert metadata.iac_relevant is True


def test_infer_content_metadata_for_terraform_template_text() -> None:
    """Terraform template text should keep its dedicated artifact family."""

    metadata = templated_detection.infer_content_metadata(
        relative_path=Path("templates/ecs/container.tpl"),
        content='{"memoryReservation": ${memory}}\n',
    )

    assert metadata.artifact_type == "terraform_template_text"
    assert metadata.template_dialect == "terraform_template"
    assert metadata.iac_relevant is True


def test_exclusion_reason_skips_generated_paths_by_default() -> None:
    """Generated directories should be excluded unless explicitly included."""

    assert (
        templated_detection.exclusion_reason(
            Path(".terraform/modules/example/main.tf"),
            include_generated=False,
        )
        == ".terraform"
    )
    assert (
        templated_detection.exclusion_reason(
            Path(".worktrees/feature/chart/templates/deployment.yaml"),
            include_generated=False,
        )
        == ".worktrees"
    )
    assert (
        templated_detection.exclusion_reason(
            Path("chart/templates/deployment.yaml"),
            include_generated=False,
        )
        is None
    )
