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
		{name: "storage s3", resourceType: "aws_s3_bucket", want: "storage"},
		{name: "data rds", resourceType: "aws_rds_cluster", want: "data"},
		{name: "networking route53", resourceType: "aws_route53_record", want: "networking"},
		{name: "messaging sqs", resourceType: "aws_sqs_queue", want: "messaging"},
		{name: "security iam", resourceType: "aws_iam_role", want: "security"},
		{name: "cicd codebuild", resourceType: "aws_codebuild_project", want: "cicd"},
		{name: "monitoring cloudwatch", resourceType: "aws_cloudwatch_metric_alarm", want: "monitoring"},
		{name: "cloudwatch event prefers longest prefix", resourceType: "aws_cloudwatch_event_rule", want: "messaging"},
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
