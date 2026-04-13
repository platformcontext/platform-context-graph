package parser

import (
	"path/filepath"
	"testing"
)

func TestInferContentMetadata(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name           string
		relativePath   string
		content        string
		wantArtifact   string
		wantDialect    string
		wantIACRelated bool
	}{
		{
			name:         "jinja config template",
			relativePath: filepath.Join("templates", "config.cfg.j2"),
			content: `apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}
`,
			wantArtifact:   "generic_config_template",
			wantDialect:    "jinja",
			wantIACRelated: true,
		},
		{
			name:         "terraform hcl with markers",
			relativePath: filepath.Join("infra", "main.tf"),
			content: `terraform {
  required_version = ">= 1.5"
}

value = ${var.name}
`,
			wantArtifact:   "terraform_hcl",
			wantDialect:    "terraform_template",
			wantIACRelated: true,
		},
		{
			name:           "plain yaml stays metadata light",
			relativePath:   filepath.Join("k8s", "deployment.yaml"),
			content:        "apiVersion: v1\nkind: ConfigMap\n",
			wantArtifact:   "",
			wantDialect:    "",
			wantIACRelated: false,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			got := inferContentMetadata(filepath.FromSlash(tt.relativePath), tt.content)
			if got.ArtifactType != tt.wantArtifact {
				t.Fatalf("ArtifactType = %q, want %q", got.ArtifactType, tt.wantArtifact)
			}
			if got.TemplateDialect != tt.wantDialect {
				t.Fatalf("TemplateDialect = %q, want %q", got.TemplateDialect, tt.wantDialect)
			}
			if got.IACRelevant != tt.wantIACRelated {
				t.Fatalf("IACRelevant = %t, want %t", got.IACRelevant, tt.wantIACRelated)
			}
		})
	}
}
