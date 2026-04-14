package terraformschema

import (
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"
)

func fixtureSchemaPath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "schemas", "test_aws_provider_schema.json")
}

func TestLoadProviderSchemaLoadsFixture(t *testing.T) {
	schema, err := LoadProviderSchema(fixtureSchemaPath(t))
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}
	if got, want := schema.ProviderName, "aws"; got != want {
		t.Fatalf("ProviderName = %q, want %q", got, want)
	}
	if got, want := schema.FormatVersion, "1.0"; got != want {
		t.Fatalf("FormatVersion = %q, want %q", got, want)
	}
}

func TestLoadProviderSchemaReturnsResourceTypes(t *testing.T) {
	schema, err := LoadProviderSchema(fixtureSchemaPath(t))
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}

	for _, resourceType := range []string{
		"aws_lambda_function",
		"aws_vpc",
		"aws_wafv2_web_acl",
	} {
		if _, ok := schema.ResourceTypes[resourceType]; !ok {
			t.Fatalf("ResourceTypes missing %q", resourceType)
		}
	}
}

func TestLoadProviderSchemaReturnsResourceCount(t *testing.T) {
	schema, err := LoadProviderSchema(fixtureSchemaPath(t))
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}
	if got, want := schema.ResourceCount(), 6; got != want {
		t.Fatalf("ResourceCount() = %d, want %d", got, want)
	}
}

func TestLoadProviderSchemaReturnsNilForMissingFile(t *testing.T) {
	schema, err := LoadProviderSchema(filepath.Join(t.TempDir(), "missing.json"))
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema != nil {
		t.Fatalf("LoadProviderSchema() = %#v, want nil", schema)
	}
}

func TestLoadProviderSchemaReturnsParsedAttributes(t *testing.T) {
	schema, err := LoadProviderSchema(fixtureSchemaPath(t))
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}

	attrs := schema.ResourceTypes["aws_lambda_function"]
	functionName, ok := attrs["function_name"]
	if !ok {
		t.Fatal("function_name attribute missing")
	}
	if got, want := functionName.Type, "string"; got != want {
		t.Fatalf("function_name.Type = %#v, want %#v", got, want)
	}
}

func TestLoadProviderSchemaSupportsGzip(t *testing.T) {
	sourcePath := fixtureSchemaPath(t)
	content, err := os.ReadFile(sourcePath)
	if err != nil {
		t.Fatalf("ReadFile(%q) error = %v", sourcePath, err)
	}

	gzPath := filepath.Join(t.TempDir(), "schema.json.gz")
	file, err := os.Create(gzPath)
	if err != nil {
		t.Fatalf("Create(%q) error = %v", gzPath, err)
	}
	gzipWriter := gzip.NewWriter(file)
	if _, err := gzipWriter.Write(content); err != nil {
		t.Fatalf("gzip.Write() error = %v", err)
	}
	if err := gzipWriter.Close(); err != nil {
		t.Fatalf("gzip.Close() error = %v", err)
	}
	if err := file.Close(); err != nil {
		t.Fatalf("file.Close() error = %v", err)
	}

	schema, err := LoadProviderSchema(gzPath)
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}
	if got, want := schema.ProviderName, "aws"; got != want {
		t.Fatalf("ProviderName = %q, want %q", got, want)
	}
}

func TestLoadProviderSchemaReturnsNilForMalformedJSON(t *testing.T) {
	path := filepath.Join(t.TempDir(), "broken.json")
	if err := os.WriteFile(path, []byte("{not-json"), 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}

	schema, err := LoadProviderSchema(path)
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema != nil {
		t.Fatalf("LoadProviderSchema() = %#v, want nil", schema)
	}
}

func TestLoadProviderSchemaMergesMetadataNestedAttributes(t *testing.T) {
	path := filepath.Join(t.TempDir(), "metadata-schema.json")
	content := []byte(`{
  "format_version": "1.0",
  "provider_schemas": {
    "registry.terraform.io/hashicorp/kubernetes": {
      "resource_schemas": {
        "kubernetes_namespace_v1": {
          "block": {
            "attributes": {
              "wait_for_default_service_account": {"type": "bool"}
            },
            "block_types": {
              "metadata": {
                "block": {
                  "attributes": {
                    "name": {"type": "string"}
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}`)
	if err := os.WriteFile(path, content, 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}

	schema, err := LoadProviderSchema(path)
	if err != nil {
		t.Fatalf("LoadProviderSchema() error = %v", err)
	}
	if schema == nil {
		t.Fatal("LoadProviderSchema() = nil, want schema")
	}

	attrs := schema.ResourceTypes["kubernetes_namespace_v1"]
	if _, ok := attrs["name"]; !ok {
		t.Fatalf("merged metadata attributes missing name: %#v", attrs)
	}
}
