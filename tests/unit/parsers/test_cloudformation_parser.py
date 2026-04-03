"""Tests for the CloudFormation parser."""

import json

import pytest

from platform_context_graph.parsers.languages.cloudformation import (
    is_cloudformation_template,
    parse_cloudformation_template,
)
from platform_context_graph.parsers.languages.yaml_infra import InfraYAMLParser


class TestCloudFormationDetection:
    """Test CloudFormation template detection."""

    def test_detect_by_template_version(self):
        doc = {"AWSTemplateFormatVersion": "2010-09-09", "Resources": {}}
        assert is_cloudformation_template(doc)

    def test_detect_by_aws_resource_type(self):
        doc = {"Resources": {"MyBucket": {"Type": "AWS::S3::Bucket"}}}
        assert is_cloudformation_template(doc)

    def test_detect_multiple_resources(self):
        doc = {
            "Resources": {
                "MyBucket": {"Type": "AWS::S3::Bucket"},
                "MyRole": {"Type": "AWS::IAM::Role"},
            }
        }
        assert is_cloudformation_template(doc)

    def test_not_detect_k8s_manifest(self):
        doc = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "svc"}}
        assert not is_cloudformation_template(doc)

    def test_not_detect_empty_doc(self):
        assert not is_cloudformation_template({})

    def test_not_detect_no_resources(self):
        doc = {"Description": "Not a CFN template"}
        assert not is_cloudformation_template(doc)

    def test_not_detect_non_aws_resources(self):
        doc = {"Resources": {"MyThing": {"Type": "Custom::Widget"}}}
        assert not is_cloudformation_template(doc)

    def test_detect_template_version_without_resources(self):
        doc = {"AWSTemplateFormatVersion": "2010-09-09"}
        assert is_cloudformation_template(doc)


class TestCloudFormationResources:
    """Test CloudFormation resource parsing."""

    def test_parse_simple_resources(self):
        doc = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Resources": {
                "DataBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": "my-bucket"},
                },
                "AppRole": {
                    "Type": "AWS::IAM::Role",
                    "Properties": {"RoleName": "my-role"},
                },
            },
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        resources = result["cloudformation_resources"]
        assert len(resources) == 2

        names = [r["name"] for r in resources]
        assert "DataBucket" in names
        assert "AppRole" in names

        bucket = next(r for r in resources if r["name"] == "DataBucket")
        assert bucket["resource_type"] == "AWS::S3::Bucket"
        assert bucket["line_number"] == 1
        assert bucket["path"] == "/test/stack.yaml"
        assert bucket["lang"] == "yaml"

    def test_parse_resource_with_depends_on(self):
        doc = {
            "Resources": {
                "MyBucket": {"Type": "AWS::S3::Bucket"},
                "MyPolicy": {
                    "Type": "AWS::S3::BucketPolicy",
                    "DependsOn": "MyBucket",
                },
            }
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        policy = next(
            r for r in result["cloudformation_resources"] if r["name"] == "MyPolicy"
        )
        assert policy["depends_on"] == "MyBucket"

    def test_parse_resource_with_list_depends_on(self):
        doc = {
            "Resources": {
                "MyService": {
                    "Type": "AWS::ECS::Service",
                    "DependsOn": ["MyCluster", "MyTaskDef"],
                },
            }
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        svc = result["cloudformation_resources"][0]
        assert svc["depends_on"] == "MyCluster,MyTaskDef"

    def test_parse_resource_with_condition(self):
        doc = {
            "Resources": {
                "ProdBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Condition": "IsProduction",
                },
            }
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        bucket = result["cloudformation_resources"][0]
        assert bucket["condition"] == "IsProduction"

    def test_parse_no_resources(self):
        doc = {"AWSTemplateFormatVersion": "2010-09-09"}
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")
        assert result["cloudformation_resources"] == []


class TestCloudFormationParameters:
    """Test CloudFormation parameter parsing."""

    def test_parse_simple_parameters(self):
        doc = {
            "Parameters": {
                "Environment": {
                    "Type": "String",
                    "Default": "development",
                    "Description": "Deployment environment",
                },
                "BucketName": {
                    "Type": "String",
                    "Description": "Name of the S3 bucket",
                },
            },
            "Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}},
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        params = result["cloudformation_parameters"]
        assert len(params) == 2

        env = next(p for p in params if p["name"] == "Environment")
        assert env["param_type"] == "String"
        assert env["default"] == "development"
        assert env["description"] == "Deployment environment"

    def test_parse_parameter_with_allowed_values(self):
        doc = {
            "Parameters": {
                "Env": {
                    "Type": "String",
                    "AllowedValues": ["dev", "staging", "production"],
                },
            },
            "Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}},
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        param = result["cloudformation_parameters"][0]
        assert param["allowed_values"] == "dev,staging,production"

    def test_parse_no_parameters(self):
        doc = {"Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}}}
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")
        assert result["cloudformation_parameters"] == []


class TestCloudFormationOutputs:
    """Test CloudFormation output parsing."""

    def test_parse_simple_outputs(self):
        doc = {
            "Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}},
            "Outputs": {
                "BucketArn": {
                    "Description": "ARN of the bucket",
                    "Value": "!GetAtt Bucket.Arn",
                },
                "BucketName": {
                    "Value": "!Ref Bucket",
                },
            },
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        outputs = result["cloudformation_outputs"]
        assert len(outputs) == 2

        arn = next(o for o in outputs if o["name"] == "BucketArn")
        assert arn["description"] == "ARN of the bucket"
        assert arn["value"] == "!GetAtt Bucket.Arn"

    def test_parse_output_with_export(self):
        doc = {
            "Resources": {"Role": {"Type": "AWS::IAM::Role"}},
            "Outputs": {
                "RoleArn": {
                    "Value": "!GetAtt Role.Arn",
                    "Export": {"Name": "MyStack-RoleArn"},
                },
            },
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        output = result["cloudformation_outputs"][0]
        assert output["export_name"] == "MyStack-RoleArn"

    def test_parse_output_with_condition(self):
        doc = {
            "Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}},
            "Outputs": {
                "BucketArn": {
                    "Condition": "IsProduction",
                    "Value": "!GetAtt Bucket.Arn",
                },
            },
        }
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")

        output = result["cloudformation_outputs"][0]
        assert output["condition"] == "IsProduction"

    def test_parse_no_outputs(self):
        doc = {"Resources": {"Bucket": {"Type": "AWS::S3::Bucket"}}}
        result = parse_cloudformation_template(doc, "/test/stack.yaml", 1, "yaml")
        assert result["cloudformation_outputs"] == []


class TestCloudFormationYAMLDispatch:
    """Test CloudFormation detection through the YAML dispatcher."""

    @pytest.fixture(scope="class")
    def parser(self):
        return InfraYAMLParser("yaml")

    def test_yaml_dispatcher_detects_cfn(self, parser, temp_test_dir):
        content = """AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  Env:
    Type: String
    Default: dev
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
Outputs:
  BucketArn:
    Value: !GetAtt MyBucket.Arn
"""
        f = temp_test_dir / "stack.yaml"
        f.write_text(content)
        result = parser.parse(str(f))

        assert len(result["cloudformation_resources"]) == 1
        assert result["cloudformation_resources"][0]["name"] == "MyBucket"
        assert (
            result["cloudformation_resources"][0]["resource_type"] == "AWS::S3::Bucket"
        )

        assert len(result["cloudformation_parameters"]) == 1
        assert result["cloudformation_parameters"][0]["name"] == "Env"

        assert len(result["cloudformation_outputs"]) == 1

    def test_yaml_dispatcher_cfn_does_not_pollute_k8s(self, parser, temp_test_dir):
        content = """AWSTemplateFormatVersion: "2010-09-09"
Resources:
  MyBucket:
    Type: AWS::S3::Bucket
"""
        f = temp_test_dir / "cfn_only.yaml"
        f.write_text(content)
        result = parser.parse(str(f))

        assert len(result["cloudformation_resources"]) == 1
        assert len(result["k8s_resources"]) == 0
        assert len(result["argocd_applications"]) == 0

    def test_yaml_dispatcher_k8s_not_cfn(self, parser, temp_test_dir):
        content = """apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  ports:
    - port: 80
"""
        f = temp_test_dir / "k8s_svc.yaml"
        f.write_text(content)
        result = parser.parse(str(f))

        assert len(result["k8s_resources"]) == 1
        assert len(result["cloudformation_resources"]) == 0

    def test_yaml_dispatcher_cfn_multi_resource(self, parser, temp_test_dir):
        content = """AWSTemplateFormatVersion: "2010-09-09"
Resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
  Subnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
  SecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Test SG
      VpcId: !Ref VPC
"""
        f = temp_test_dir / "vpc.yaml"
        f.write_text(content)
        result = parser.parse(str(f))

        assert len(result["cloudformation_resources"]) == 3
        types = [r["resource_type"] for r in result["cloudformation_resources"]]
        assert "AWS::EC2::VPC" in types
        assert "AWS::EC2::Subnet" in types
        assert "AWS::EC2::SecurityGroup" in types

    def test_result_has_cfn_buckets(self, parser, temp_test_dir):
        """Verify empty result includes CloudFormation buckets."""
        content = """apiVersion: v1
kind: ConfigMap
metadata:
  name: test
data:
  key: value
"""
        f = temp_test_dir / "configmap.yaml"
        f.write_text(content)
        result = parser.parse(str(f))

        assert "cloudformation_resources" in result
        assert "cloudformation_parameters" in result
        assert "cloudformation_outputs" in result
