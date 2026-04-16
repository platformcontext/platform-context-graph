package query

import (
	"context"
	"testing"
)

func TestHandleRelationshipsReturnsGraphBackedKotlinSafeCallReceiverChains(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-safe-chain-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(9),
					"end_line":   int64(13),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-safe-chain-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(t, handler, "function-kotlin-safe-chain-1", "kotlin", "info")
}

func TestHandleRelationshipsReturnsGraphBackedKotlinIfSmartCastReceiverCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-smart-if-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(10),
					"end_line":   int64(15),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-smart-if-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(t, handler, "function-kotlin-smart-if-1", "kotlin", "info")
}

func TestHandleRelationshipsReturnsGraphBackedKotlinWhenSmartCastReceiverChains(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-smart-when-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(10),
					"end_line":   int64(16),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-smart-when-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-kotlin-smart-when-1",
		"kotlin",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedKotlinGenericSmartCastReceiverChains(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-smart-generic-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(11),
					"end_line":   int64(17),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-smart-generic-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-kotlin-smart-generic-1",
		"kotlin",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedKotlinPackageAwareDirectFunctionReturnReceiverChains(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-package-direct-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/feature/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(12),
					"end_line":   int64(16),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-package-direct-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-kotlin-package-direct-1",
		"kotlin",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedKotlinParenthesizedCrossFilePackageAwareFunctionReturnReceiverChains(
	t *testing.T,
) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-kotlin-package-parenthesized-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/feature/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(13),
					"end_line":   int64(17),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-kotlin-package-parenthesized-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-kotlin-package-parenthesized-1",
		"kotlin",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedPHPFreeFunctionReturnCallChainReceiverCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-free-chain-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/App.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(6),
					"end_line":   int64(10),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-free-chain-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(t, handler, "function-php-free-chain-1", "php", "info")
}

func TestHandleRelationshipsReturnsGraphBackedPHPParenthesizedMethodReturnCallChainReceiverCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-parenthesized-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/App.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(8),
					"end_line":   int64(12),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-parenthesized-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-php-parenthesized-1",
		"php",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedPHPSelfAndStaticInstantiationReceiverCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-self-static-new-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/Config.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(8),
					"end_line":   int64(12),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-self-static-new-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-php-self-static-new-1",
		"php",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedPHPCrossFileChainedStaticFactoryReturnCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-static-factory-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/App.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(7),
					"end_line":   int64(11),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-static-factory-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-php-static-factory-1",
		"php",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedPHPCrossFileMethodReturnCallChainRows(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-cross-method-chain-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/App.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(9),
					"end_line":   int64(13),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-cross-method-chain-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-php-cross-method-chain-1",
		"php",
		"info",
	)
}

func TestHandleRelationshipsReturnsGraphBackedPHPAnonymousClassReceiverCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-anonymous-class-1",
					"name":       "run",
					"labels":     []any{"Function"},
					"file_path":  "src/App.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(10),
					"end_line":   int64(14),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "info",
							"target_id":   "function-php-anonymous-class-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	assertGraphBackedSingleCallResponse(
		t,
		handler,
		"function-php-anonymous-class-1",
		"php",
		"info",
	)
}
