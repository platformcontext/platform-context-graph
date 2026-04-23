package query

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j/dbtype"
)

type callChainRequest struct {
	Start         string `json:"start"`
	End           string `json:"end"`
	StartEntityID string `json:"start_entity_id"`
	EndEntityID   string `json:"end_entity_id"`
	RepoID        string `json:"repo_id"`
	MaxDepth      int    `json:"max_depth"`
}

func (h *CodeHandler) handleCallChain(w http.ResponseWriter, r *http.Request) {
	if capabilityUnsupported(h.profile(), "call_graph.call_chain_path") {
		WriteContractError(
			w,
			r,
			http.StatusNotImplemented,
			"call-chain analysis requires authoritative graph mode",
			"unsupported_capability",
			"call_graph.call_chain_path",
			h.profile(),
			requiredProfile("call_graph.call_chain_path"),
		)
		return
	}

	var req callChainRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if strings.TrimSpace(req.StartEntityID) == "" && strings.TrimSpace(req.Start) == "" {
		WriteError(w, http.StatusBadRequest, "start or start_entity_id is required")
		return
	}
	if strings.TrimSpace(req.EndEntityID) == "" && strings.TrimSpace(req.End) == "" {
		WriteError(w, http.StatusBadRequest, "end or end_entity_id is required")
		return
	}
	if req.MaxDepth <= 0 {
		req.MaxDepth = 5
	}
	if req.MaxDepth > 10 {
		req.MaxDepth = 10
	}
	resolvedRepoID, err := h.resolveRepositorySelector(r.Context(), req.RepoID)
	if err != nil && strings.TrimSpace(req.RepoID) != "" {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	req.RepoID = resolvedRepoID

	cypher, params := buildCallChainCypher(req, h.graphBackend())
	rows, err := h.Neo4j.Run(r.Context(), cypher, params)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	chains := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		chain := attachCallChainNodeSemantics(normalizeCallChainNodes(row["chain"]))
		chains = append(chains, map[string]any{
			"chain": chain,
			"depth": IntVal(row, "depth"),
		})
	}

	WriteSuccess(w, r, http.StatusOK, map[string]any{
		"start":           req.Start,
		"end":             req.End,
		"start_entity_id": req.StartEntityID,
		"end_entity_id":   req.EndEntityID,
		"repo_id":         req.RepoID,
		"chains":          chains,
	}, BuildTruthEnvelope(h.profile(), "call_graph.call_chain_path", TruthBasisAuthoritativeGraph, "resolved from authoritative call graph traversal"))
}

func buildCallChainCypher(req callChainRequest, backend GraphBackend) (string, map[string]any) {
	params := map[string]any{}
	startPattern := "(start)"
	endPattern := "(end)"
	predicates := make([]string, 0, 2)

	if backend == GraphBackendNornicDB {
		if strings.TrimSpace(req.StartEntityID) != "" {
			params["start_entity_id"] = strings.TrimSpace(req.StartEntityID)
			startPattern = "(start {id: $start_entity_id})"
		} else {
			params["start"] = strings.TrimSpace(req.Start)
			startPattern = "(start {name: $start})"
		}

		if strings.TrimSpace(req.EndEntityID) != "" {
			params["end_entity_id"] = strings.TrimSpace(req.EndEntityID)
			endPattern = "(end {id: $end_entity_id})"
		} else {
			params["end"] = strings.TrimSpace(req.End)
			endPattern = "(end {name: $end})"
		}
	} else {
		if strings.TrimSpace(req.StartEntityID) != "" {
			params["start_entity_id"] = strings.TrimSpace(req.StartEntityID)
			predicates = append(predicates, "start.id = $start_entity_id")
		} else {
			params["start"] = strings.TrimSpace(req.Start)
			predicates = append(predicates, "start.name = $start")
		}

		if strings.TrimSpace(req.EndEntityID) != "" {
			params["end_entity_id"] = strings.TrimSpace(req.EndEntityID)
			predicates = append(predicates, "end.id = $end_entity_id")
		} else {
			params["end"] = strings.TrimSpace(req.End)
			predicates = append(predicates, "end.name = $end")
		}
	}

	if strings.TrimSpace(req.RepoID) != "" {
		params["repo_id"] = strings.TrimSpace(req.RepoID)
		predicates = append(predicates, "start.repo_id = $repo_id", "end.repo_id = $repo_id")
	}

	var cypher strings.Builder
	cypher.WriteString("\n\t\tMATCH ")
	cypher.WriteString(startPattern)
	if backend == GraphBackendNornicDB {
		cypher.WriteString(", ")
		cypher.WriteString(endPattern)
	} else {
		cypher.WriteString("\n\t\tMATCH ")
		cypher.WriteString(endPattern)
	}
	if len(predicates) > 0 {
		cypher.WriteString("\n\t\tWHERE ")
		cypher.WriteString(strings.Join(predicates, " AND "))
	}
	cypher.WriteString("\n\t\tMATCH path = shortestPath(\n")
	cypher.WriteString("\t\t\t(start)-[:CALLS*1..")
	cypher.WriteString(fmt.Sprintf("%d", req.MaxDepth))
	cypher.WriteString("]->(end)\n")
	cypher.WriteString("\t\t)\n")
	if backend == GraphBackendNornicDB {
		// NornicDB resolves this path correctly with raw nodes(path) results,
		// while its inline list projection returns null today.
		cypher.WriteString("\t\tRETURN nodes(path) as chain,\n")
	} else {
		cypher.WriteString("\t\tRETURN [node IN nodes(path) | {id: node.id, name: node.name, labels: labels(node), language: node.language, docstring: node.docstring, method_kind: node.method_kind}] as chain,\n")
	}
	cypher.WriteString("\t\t       length(path) as depth\n")
	cypher.WriteString("\t\tLIMIT 5\n\t")
	return cypher.String(), params
}

func normalizeCallChainNodes(raw any) []any {
	switch nodes := raw.(type) {
	case []any:
		normalized := make([]any, 0, len(nodes))
		for _, node := range nodes {
			normalized = append(normalized, normalizeCallChainNode(node))
		}
		return normalized
	case []dbtype.Node:
		normalized := make([]any, 0, len(nodes))
		for _, node := range nodes {
			normalized = append(normalized, normalizeCallChainNode(node))
		}
		return normalized
	default:
		return nil
	}
}

func normalizeCallChainNode(raw any) any {
	switch node := raw.(type) {
	case map[string]any:
		return cloneQueryAnyMap(node)
	case dbtype.Node:
		// The shared Bolt driver returns typed nodes for raw nodes(path)
		// results, so the handler normalizes them to the existing map shape.
		labels := make([]any, 0, len(node.Labels))
		for _, label := range node.Labels {
			labels = append(labels, label)
		}
		return map[string]any{
			"id":          fmt.Sprintf("%v", node.Props["id"]),
			"name":        fmt.Sprintf("%v", node.Props["name"]),
			"labels":      labels,
			"language":    node.Props["language"],
			"docstring":   node.Props["docstring"],
			"method_kind": node.Props["method_kind"],
		}
	default:
		return raw
	}
}

func attachCallChainNodeSemantics(nodes []any) []any {
	if len(nodes) == 0 {
		return nodes
	}

	attached := make([]any, 0, len(nodes))
	for _, node := range nodes {
		nodeMap, ok := node.(map[string]any)
		if !ok {
			attached = append(attached, node)
			continue
		}

		normalized := cloneQueryAnyMap(nodeMap)
		if metadata := graphResultMetadata(normalized); len(metadata) > 0 {
			normalized["metadata"] = metadata
			attachSemanticSummary(normalized)
		}
		attached = append(attached, normalized)
	}

	return attached
}
