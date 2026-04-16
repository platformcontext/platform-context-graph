package reducer

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestExtractCodeCallRowsResolvesKotlinFunctionReturnReceiverChainsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "Usage.kt")
	if err := os.WriteFile(callerPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun usage(): String {
    val factory = Factory()
    return factory.createService().info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", callerPath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	callerPayload, err := engine.ParsePath(repoRoot, callerPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", callerPath, err)
	}
	if functions, ok := callerPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "usage":
				function["end_line"] = 15
				function["uid"] = "content-entity:kotlin-usage"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Usage.kt",
				"parsed_file_data": callerPayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1; rows=%#v; function_calls=%#v", len(rows), rows, callerPayload["function_calls"])
	}

	if got, want := rows[0]["callee_entity_id"], "content-entity:kotlin-service-info"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["full_name"], "factory.createService().info"; got != want {
		t.Fatalf("full_name = %#v, want %#v", got, want)
	}
}

func TestExtractCodeCallRowsResolvesKotlinNestedFunctionReturnAssignmentReceiverCallsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "Usage.kt")
	if err := os.WriteFile(callerPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", callerPath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	callerPayload, err := engine.ParsePath(repoRoot, callerPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", callerPath, err)
	}
	if functions, ok := callerPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "usage":
				function["end_line"] = 15
				function["uid"] = "content-entity:kotlin-usage"
			case name == "createFactory":
				function["uid"] = "content-entity:kotlin-create-factory"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Usage.kt",
				"parsed_file_data": callerPayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v; function_calls=%#v", len(rows), rows, callerPayload["function_calls"])
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "service.info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		fullName, _ := row["full_name"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if fullName != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", fullName, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}

func TestExtractCodeCallRowsResolvesKotlinSiblingFileFunctionReturnTypeAliasCallsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "Api.kt")
	usagePath := filepath.Join(repoRoot, "Usage.kt")
	if err := os.WriteFile(apiPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", apiPath, err)
	}
	if err := os.WriteFile(usagePath, []byte(`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", usagePath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	apiPayload, err := engine.ParsePath(repoRoot, apiPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", apiPath, err)
	}
	usagePayload, err := engine.ParsePath(repoRoot, usagePath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", usagePath, err)
	}
	if functions, ok := apiPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "createFactory":
				function["uid"] = "content-entity:kotlin-create-factory"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}
	if functions, ok := usagePayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			if name == "usage" {
				function["end_line"] = 6
				function["uid"] = "content-entity:kotlin-usage"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Api.kt",
				"parsed_file_data": apiPayload,
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Usage.kt",
				"parsed_file_data": usagePayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v", len(rows), rows)
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "service.info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if got := row["full_name"]; got != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", got, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}

func TestExtractCodeCallRowsResolvesKotlinParentDirectorySiblingFunctionReturnTypeAliasCallsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "Api.kt")
	usageDir := filepath.Join(repoRoot, "nested")
	usagePath := filepath.Join(usageDir, "Usage.kt")
	if err := os.WriteFile(apiPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", apiPath, err)
	}
	if err := os.MkdirAll(usageDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v, want nil", usageDir, err)
	}
	if err := os.WriteFile(usagePath, []byte(`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", usagePath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	apiPayload, err := engine.ParsePath(repoRoot, apiPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", apiPath, err)
	}
	usagePayload, err := engine.ParsePath(repoRoot, usagePath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", usagePath, err)
	}
	if functions, ok := apiPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "createFactory":
				function["uid"] = "content-entity:kotlin-create-factory"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}
	if functions, ok := usagePayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			if name == "usage" {
				function["end_line"] = 6
				function["uid"] = "content-entity:kotlin-usage"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "nested/Usage.kt",
				"parsed_file_data": usagePayload,
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Api.kt",
				"parsed_file_data": apiPayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v; function_calls=%#v", len(rows), rows, usagePayload["function_calls"])
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "service.info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		fullName, _ := row["full_name"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if fullName != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", fullName, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}

func TestExtractCodeCallRowsResolvesKotlinPackageAwareSiblingFunctionReturnTypeAliasCallsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "Api.kt")
	otherPath := filepath.Join(repoRoot, "Other.kt")
	usagePath := filepath.Join(repoRoot, "Usage.kt")
	if err := os.WriteFile(apiPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", apiPath, err)
	}
	if err := os.WriteFile(otherPath, []byte(`package otherpkg

class OtherFactory {
    fun createService(): String = "wrong"
}

fun createFactory(): OtherFactory = OtherFactory()
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", otherPath, err)
	}
	if err := os.WriteFile(usagePath, []byte(`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", usagePath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	apiPayload, err := engine.ParsePath(repoRoot, apiPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", apiPath, err)
	}
	usagePayload, err := engine.ParsePath(repoRoot, usagePath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", usagePath, err)
	}
	if functions, ok := apiPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "createFactory":
				function["uid"] = "content-entity:kotlin-create-factory"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}
	if functions, ok := usagePayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			if name == "usage" {
				function["end_line"] = 6
				function["uid"] = "content-entity:kotlin-usage"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Api.kt",
				"parsed_file_data": apiPayload,
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Usage.kt",
				"parsed_file_data": usagePayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v", len(rows), rows)
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "service.info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if got := row["full_name"]; got != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", got, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}

func TestExtractCodeCallRowsResolvesKotlinPackageAwareSiblingFunctionReturnTypesAcrossGrandparentDirectoriesUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "src", "main", "kotlin", "common", "Api.kt")
	usagePath := filepath.Join(repoRoot, "src", "main", "kotlin", "feature", "module", "Usage.kt")
	if err := os.MkdirAll(filepath.Dir(apiPath), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v, want nil", filepath.Dir(apiPath), err)
	}
	if err := os.MkdirAll(filepath.Dir(usagePath), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v, want nil", filepath.Dir(usagePath), err)
	}
	if err := os.WriteFile(apiPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", apiPath, err)
	}
	if err := os.WriteFile(usagePath, []byte(`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", usagePath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	apiPayload, err := engine.ParsePath(repoRoot, apiPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", apiPath, err)
	}
	usagePayload, err := engine.ParsePath(repoRoot, usagePath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", usagePath, err)
	}
	if functions, ok := apiPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "createFactory":
				function["uid"] = "content-entity:kotlin-create-factory"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}
	if functions, ok := usagePayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			if name == "usage" {
				function["end_line"] = 6
				function["uid"] = "content-entity:kotlin-usage"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "src/main/kotlin/feature/module/Usage.kt",
				"parsed_file_data": usagePayload,
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "src/main/kotlin/common/Api.kt",
				"parsed_file_data": apiPayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v", len(rows), rows)
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "service.info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if got := row["full_name"]; got != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", got, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}

func TestExtractCodeCallRowsResolvesKotlinParenthesizedFunctionReturnReceiverChainsUsingInferredObjectType(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "Usage.kt")
	if err := os.WriteFile(callerPath, []byte(`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()

fun usage(): String {
    return (createFactory().createService()).info()
}
`), 0o600); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", callerPath, err)
	}

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	callerPayload, err := engine.ParsePath(repoRoot, callerPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", callerPath, err)
	}
	if functions, ok := callerPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "usage":
				function["end_line"] = 15
				function["uid"] = "content-entity:kotlin-usage"
			case name == "createService" && classContext == "Factory":
				function["uid"] = "content-entity:kotlin-factory-create-service"
			case name == "info" && classContext == "Service":
				function["uid"] = "content-entity:kotlin-service-info"
			}
		}
	}

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Usage.kt",
				"parsed_file_data": callerPayload,
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2; rows=%#v; function_calls=%#v", len(rows), rows, callerPayload["function_calls"])
	}

	want := map[string]string{
		"content-entity:kotlin-factory-create-service": "createFactory().createService",
		"content-entity:kotlin-service-info":           "createFactory().createService().info",
	}
	for _, row := range rows {
		calleeID, _ := row["callee_entity_id"].(string)
		fullName, _ := row["full_name"].(string)
		if expectedFullName, ok := want[calleeID]; ok {
			if fullName != expectedFullName {
				t.Fatalf("full_name = %#v, want %#v for callee %#v", fullName, expectedFullName, calleeID)
			}
			delete(want, calleeID)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing expected callee rows: %#v; rows=%#v", want, rows)
	}
}
