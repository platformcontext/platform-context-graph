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

func TestParseCloudFormationTemplatePersistsFileFormat(t *testing.T) {
	t.Parallel()

	document := map[string]any{
		"AWSTemplateFormatVersion": "2010-09-09",
		"Parameters": map[string]any{
			"Environment": map[string]any{
				"AllowedValues": []any{"dev", "prod"},
			},
		},
		"Resources": map[string]any{
			"DataBucket": map[string]any{
				"Type": "AWS::S3::Bucket",
				"DependsOn": []any{
					"BootstrapBucket",
				},
			},
		},
		"Outputs": map[string]any{
			"BucketArn": map[string]any{
				"Export": map[string]any{
					"Name": "Stack-BucketArn",
				},
			},
		},
	}

	for _, tc := range []struct {
		name       string
		fileFormat string
	}{
		{name: "yaml", fileFormat: "yaml"},
		{name: "json", fileFormat: "json"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			result := parseCloudFormationTemplate(document, "/test/stack."+tc.name, 1, tc.fileFormat)

			if got, want := result.params[0]["file_format"], tc.fileFormat; got != want {
				t.Fatalf("parameter file_format = %#v, want %#v", got, want)
			}
			if got, want := result.resources[0]["file_format"], tc.fileFormat; got != want {
				t.Fatalf("resource file_format = %#v, want %#v", got, want)
			}
			if got, want := result.outputs[0]["file_format"], tc.fileFormat; got != want {
				t.Fatalf("output file_format = %#v, want %#v", got, want)
			}
			if got, want := result.imports, []map[string]any{}; len(got) != len(want) {
				t.Fatalf("imports len = %d, want %d", len(got), len(want))
			}
			if got, want := result.exports[0]["file_format"], tc.fileFormat; got != want {
				t.Fatalf("export file_format = %#v, want %#v", got, want)
			}
		})
	}
}
