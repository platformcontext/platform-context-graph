package collector

import "testing"

func TestMergeSCIPSupplementPreservesDeadCodeRootKinds(t *testing.T) {
	t.Parallel()

	parsed := map[string]any{
		"functions": []map[string]any{
			{
				"name": "ServePayments",
			},
		},
	}
	supplement := map[string]any{
		"functions": []map[string]any{
			{
				"name":                 "ServePayments",
				"dead_code_root_kinds": []string{"go.net_http_handler_registration"},
			},
		},
	}

	mergeSCIPSupplement(parsed, supplement)

	functions, ok := parsed["functions"].([]map[string]any)
	if !ok || len(functions) != 1 {
		t.Fatalf("parsed[functions] = %#v, want one merged function", parsed["functions"])
	}
	got, ok := functions[0]["dead_code_root_kinds"].([]string)
	if !ok {
		t.Fatalf("dead_code_root_kinds = %T, want []string", functions[0]["dead_code_root_kinds"])
	}
	if len(got) != 1 || got[0] != "go.net_http_handler_registration" {
		t.Fatalf("dead_code_root_kinds = %#v, want %#v", got, []string{"go.net_http_handler_registration"})
	}
}
