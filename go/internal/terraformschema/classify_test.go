package terraformschema

import "testing"

func TestClassifyResourceCategory(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name         string
		resourceType string
		want         string
	}{
		{name: "compute lambda", resourceType: "aws_lambda_function", want: "compute"},
		{name: "compute ecs", resourceType: "aws_ecs_service", want: "compute"},
		{name: "compute appautoscaling", resourceType: "aws_appautoscaling_target", want: "compute"},
		{name: "compute launch template", resourceType: "aws_launch_template", want: "compute"},
		{name: "storage s3", resourceType: "aws_s3_bucket", want: "storage"},
		{name: "storage ebs", resourceType: "aws_ebs_volume", want: "storage"},
		{name: "storage datasync", resourceType: "aws_datasync_location_s3", want: "storage"},
		{name: "storage transfer", resourceType: "aws_transfer_server", want: "storage"},
		{name: "data rds", resourceType: "aws_rds_cluster", want: "data"},
		{name: "data dms", resourceType: "aws_dms_endpoint", want: "data"},
		{name: "data docdb", resourceType: "aws_docdb_cluster", want: "data"},
		{name: "networking route53", resourceType: "aws_route53_record", want: "networking"},
		{name: "networking api gateway", resourceType: "aws_api_gateway_resource", want: "networking"},
		{name: "networking subnet plural", resourceType: "aws_subnets", want: "networking"},
		{name: "networking route table plural", resourceType: "aws_route_tables", want: "networking"},
		{name: "networking eip", resourceType: "aws_eip", want: "networking"},
		{name: "networking peering", resourceType: "aws_vpc_peering_connection_accepter", want: "networking"},
		{name: "networking gateway", resourceType: "aws_internet_gateway", want: "networking"},
		{name: "networking acl", resourceType: "aws_network_acl_rule", want: "networking"},
		{name: "messaging sqs", resourceType: "aws_sqs_queue", want: "messaging"},
		{name: "messaging ses", resourceType: "aws_ses_domain_identity", want: "messaging"},
		{name: "security iam", resourceType: "aws_iam_role", want: "security"},
		{name: "security ssoadmin", resourceType: "aws_ssoadmin_permission_set", want: "security"},
		{name: "cicd codebuild", resourceType: "aws_codebuild_project", want: "cicd"},
		{name: "monitoring cloudwatch", resourceType: "aws_cloudwatch_metric_alarm", want: "monitoring"},
		{name: "cloudwatch event prefers longest prefix", resourceType: "aws_cloudwatch_event_rule", want: "messaging"},
		{name: "governance cloudformation", resourceType: "aws_cloudformation_stack", want: "governance"},
		{name: "governance caller identity", resourceType: "aws_caller_identity", want: "governance"},
		{name: "unknown defaults infrastructure", resourceType: "aws_unknown_thing", want: "infrastructure"},
		{name: "security wafv2", resourceType: "aws_wafv2_web_acl", want: "security"},
		{name: "data neptune", resourceType: "aws_neptune_cluster", want: "data"},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := ClassifyResourceCategory(tc.resourceType); got != tc.want {
				t.Fatalf("ClassifyResourceCategory(%q) = %q, want %q", tc.resourceType, got, tc.want)
			}
		})
	}
}

func TestClassifyResourceService(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name         string
		resourceType string
		want         string
	}{
		{name: "iam policy document", resourceType: "aws_iam_policy_document", want: "iam"},
		{name: "cloudwatch event", resourceType: "aws_cloudwatch_event_rule", want: "cloudwatch_event"},
		{name: "api gateway", resourceType: "aws_api_gateway_resource", want: "api_gateway"},
		{name: "api gateway v2", resourceType: "aws_apigatewayv2_api", want: "apigatewayv2"},
		{name: "vpc peering", resourceType: "aws_vpc_peering_connection_accepter", want: "vpc_peering_connection"},
		{name: "caller identity", resourceType: "aws_caller_identity", want: "caller_identity"},
		{name: "unknown falls back to first service token", resourceType: "aws_custom_service_widget", want: "custom"},
		{name: "invalid", resourceType: "aws", want: ""},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := ClassifyResourceService(tc.resourceType); got != tc.want {
				t.Fatalf("ClassifyResourceService(%q) = %q, want %q", tc.resourceType, got, tc.want)
			}
		})
	}
}
