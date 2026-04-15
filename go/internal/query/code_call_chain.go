package query

import (
	"fmt"
	"net/http"
	"strings"
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

	cypher, params := buildCallChainCypher(req)
	rows, err := h.Neo4j.Run(r.Context(), cypher, params)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	chains := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		chains = append(chains, map[string]any{
			"chain": row["chain"],
			"depth": IntVal(row, "depth"),
		})
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"start":           req.Start,
		"end":             req.End,
		"start_entity_id": req.StartEntityID,
		"end_entity_id":   req.EndEntityID,
		"repo_id":         req.RepoID,
		"chains":          chains,
	})
}

func buildCallChainCypher(req callChainRequest) (string, map[string]any) {
	params := map[string]any{}
	predicates := make([]string, 0, 6)

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

	if strings.TrimSpace(req.RepoID) != "" {
		params["repo_id"] = strings.TrimSpace(req.RepoID)
		predicates = append(predicates, "start.repo_id = $repo_id", "end.repo_id = $repo_id")
	}

	cypher := `
		MATCH (start)
		MATCH (end)
		WHERE ` + strings.Join(predicates, " AND ") + `
		MATCH path = shortestPath(
			(start)-[:CALLS*1..` + fmt.Sprintf("%d", req.MaxDepth) + `]->(end)
		)
		RETURN [node IN nodes(path) | {id: node.id, name: node.name, labels: labels(node)}] as chain,
		       length(path) as depth
		LIMIT 5
	`
	return cypher, params
}
