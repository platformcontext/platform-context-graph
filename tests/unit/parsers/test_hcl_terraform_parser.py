"""Tests for HCL/Terraform parser."""

import pytest

from platform_context_graph.tools.languages.hcl_terraform import (
    HCLTerraformParser,
)


class TestHCLTerraformParser:
    """Test the HCL/Terraform parser."""

    @pytest.fixture(scope="class")
    def parser(self):
        return HCLTerraformParser("hcl")

    @pytest.fixture(scope="class")
    def tf_fixtures(self, sample_projects_path):
        path = sample_projects_path / "sample_project_terraform"
        if not path.exists():
            pytest.fail(f"Terraform sample project not found at {path}")
        return path

    # --- Resources ---

    def test_parse_terraform_resources(self, parser, tf_fixtures):
        """Parse terraform resource blocks."""
        result = parser.parse(str(tf_fixtures / "main.tf"))

        assert "terraform_resources" in result
        resources = result["terraform_resources"]
        assert len(resources) == 2

        names = [r["name"] for r in resources]
        assert "aws_iam_role.irsa_role" in names
        assert "aws_iam_role_policy_attachment.main" in names

        role = next(r for r in resources if r["name"] == "aws_iam_role.irsa_role")
        assert role["resource_type"] == "aws_iam_role"
        assert role["resource_name"] == "irsa_role"
        assert "line_number" in role
        assert isinstance(role["line_number"], int)

    # --- Variables ---

    def test_parse_terraform_variables(self, parser, tf_fixtures):
        """Parse terraform variable blocks."""
        result = parser.parse(str(tf_fixtures / "variables.tf"))

        assert "terraform_variables" in result
        variables = result["terraform_variables"]
        assert len(variables) == 9

        names = [v["name"] for v in variables]
        assert "aws_region" in names
        assert "role_name" in names
        assert "bucket_name" in names

        region = next(v for v in variables if v["name"] == "aws_region")
        assert region["var_type"] == "string"
        assert region["default"] == "us-east-1"
        assert region["description"] == "AWS region for resources"

    # --- Outputs ---

    def test_parse_terraform_outputs(self, parser, tf_fixtures):
        """Parse terraform output blocks."""
        result = parser.parse(str(tf_fixtures / "outputs.tf"))

        assert "terraform_outputs" in result
        outputs = result["terraform_outputs"]
        assert len(outputs) == 2

        names = [o["name"] for o in outputs]
        assert "role_arn" in names
        assert "role_name" in names

        role_arn = next(o for o in outputs if o["name"] == "role_arn")
        assert role_arn["description"] == "ARN of the created IAM role"
        assert role_arn["value"] == "aws_iam_role.irsa_role.arn"

    # --- Modules ---

    def test_parse_terraform_modules(self, parser, tf_fixtures):
        """Parse terraform module blocks."""
        result = parser.parse(str(tf_fixtures / "main.tf"))

        assert "terraform_modules" in result
        modules = result["terraform_modules"]
        assert len(modules) == 1

        mod = modules[0]
        assert mod["name"] == "s3_bucket"
        assert mod["source"] == "terraform-aws-modules/s3-bucket/aws"
        assert mod["version"] == "3.15.1"

    # --- Data Sources ---

    def test_parse_terraform_data_sources(self, parser, tf_fixtures):
        """Parse terraform data blocks."""
        result = parser.parse(str(tf_fixtures / "main.tf"))

        assert "terraform_data_sources" in result
        data_sources = result["terraform_data_sources"]
        assert len(data_sources) == 1

        ds = data_sources[0]
        assert ds["name"] == "aws_iam_policy_document.trust"
        assert ds["data_type"] == "aws_iam_policy_document"
        assert ds["data_name"] == "trust"

    # --- Result structure ---

    def test_result_structure(self, parser, tf_fixtures):
        """Verify result has standard keys."""
        result = parser.parse(str(tf_fixtures / "main.tf"))

        assert result["path"] == str(tf_fixtures / "main.tf")
        assert result["lang"] == "hcl"
        assert "is_dependency" in result

    # --- Edge Cases ---

    def test_parse_empty_tf_file(self, parser, temp_test_dir):
        """Parse an empty .tf file."""
        f = temp_test_dir / "empty.tf"
        f.write_text("")

        result = parser.parse(str(f))
        assert result["path"] == str(f)
        assert len(result.get("terraform_resources", [])) == 0

    def test_parse_comments_only(self, parser, temp_test_dir):
        """Parse a .tf file with only comments."""
        f = temp_test_dir / "comments.tf"
        f.write_text("# This is a comment\n// Another comment\n/* Block comment */\n")

        result = parser.parse(str(f))
        assert len(result.get("terraform_resources", [])) == 0

    def test_parse_terragrunt_config(self, parser, temp_test_dir):
        """Parse a terragrunt.hcl file."""
        f = temp_test_dir / "terragrunt.hcl"
        f.write_text(
            "terraform {\n"
            '  source = "tfr:///terraform-aws-modules/'
            's3-bucket/aws?version=3.15.1"\n'
            "}\n\n"
            'include "root" {\n'
            "  path = find_in_parent_folders()\n"
            "}\n\n"
            "inputs = {\n"
            '  bucket_name = "my-bucket"\n'
            "}\n"
        )

        result = parser.parse(str(f))
        assert "terragrunt_configs" in result
        configs = result["terragrunt_configs"]
        assert len(configs) == 1

        config = configs[0]
        assert config["name"] == "terragrunt"
        assert "terraform_source" in config

    def test_line_numbers_are_accurate(self, parser, tf_fixtures):
        """Verify line numbers point to the right location."""
        result = parser.parse(str(tf_fixtures / "main.tf"))

        resources = result["terraform_resources"]
        for resource in resources:
            assert "line_number" in resource
            assert isinstance(resource["line_number"], int)
            assert resource["line_number"] >= 1

    def test_parse_resource_with_nested_blocks(self, parser, temp_test_dir):
        """Parse a resource with deeply nested blocks."""
        f = temp_test_dir / "nested.tf"
        f.write_text(
            'resource "aws_security_group" "main" {\n'
            '  name = "my-sg"\n\n'
            "  ingress {\n"
            "    from_port   = 443\n"
            "    to_port     = 443\n"
            '    protocol    = "tcp"\n'
            '    cidr_blocks = ["0.0.0.0/0"]\n'
            "  }\n\n"
            "  egress {\n"
            "    from_port   = 0\n"
            "    to_port     = 0\n"
            '    protocol    = "-1"\n'
            '    cidr_blocks = ["0.0.0.0/0"]\n'
            "  }\n"
            "}\n"
        )

        result = parser.parse(str(f))
        resources = result["terraform_resources"]
        assert len(resources) == 1
        assert resources[0]["name"] == "aws_security_group.main"
        assert resources[0]["resource_type"] == "aws_security_group"
