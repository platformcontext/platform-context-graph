package parser

import "testing"

func TestIsCloudFormationTemplateDetectsSAMTransformList(t *testing.T) {
	t.Parallel()

	document := map[string]any{
		"Transform": []any{
			"AWS::Serverless-2016-10-31",
		},
		"Resources": map[string]any{
			"Example": map[string]any{
				"Type": "Custom::Widget",
			},
		},
	}

	if !isCloudFormationTemplate(document) {
		t.Fatalf("isCloudFormationTemplate() = false, want true")
	}
}

func TestParseCloudFormationTemplateDefaultsParameterTypeToString(t *testing.T) {
	t.Parallel()

	document := map[string]any{
		"AWSTemplateFormatVersion": "2010-09-09",
		"Parameters": map[string]any{
			"Environment": map[string]any{
				"Default": "dev",
			},
		},
	}

	result := parseCloudFormationTemplate(document, "/test/stack.json", 1, "json")
	params := result.params
	if len(params) != 1 {
		t.Fatalf("len(params) = %d, want 1", len(params))
	}

	if got, want := params[0]["name"], "Environment"; got != want {
		t.Fatalf("parameter name = %#v, want %#v", got, want)
	}
	if got, want := params[0]["param_type"], "String"; got != want {
		t.Fatalf("parameter param_type = %#v, want %#v", got, want)
	}
}
