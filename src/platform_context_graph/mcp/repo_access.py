"""Repository access handoff helpers for the MCP server."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

_ClientRequestHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class _RepoAccessRuntime(Protocol):
    """Structural type for the server state required by repo-access helpers."""

    client_capabilities: dict[str, Any]
    _client_request_handler: _ClientRequestHandler | None


class ServerRepoAccessMixin:
    """Provide repository access elicitation helpers for ``MCPServer``."""

    def _supported_elicitation_modes(self: _RepoAccessRuntime) -> set[str]:
        """Return the elicitation modes advertised by the connected client.

        Returns:
            The supported elicitation modes. An empty set means the client did
            not advertise elicitation support.
        """
        elicitation = self.client_capabilities.get("elicitation")
        if elicitation is None:
            return set()
        if not isinstance(elicitation, dict) or not elicitation:
            return {"form"}
        return {mode for mode in ("form", "url") if mode in elicitation}

    def _supports_elicitation(
        self: _RepoAccessRuntime, *, transport: str, mode: str = "form"
    ) -> bool:
        """Return whether the current connection can use MCP elicitation.

        Args:
            transport: The active MCP transport identifier.
            mode: The elicitation mode to check.

        Returns:
            ``True`` when the current transport and client support the requested
            elicitation mode.
        """
        return (
            transport == "jsonrpc-stdio"
            and self._client_request_handler is not None
            and mode in self._supported_elicitation_modes()
        )

    async def _request_client(
        self: _RepoAccessRuntime, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send an outbound MCP request to the connected client.

        Args:
            method: The MCP method to invoke on the client.
            params: The request payload to send.

        Returns:
            The client's JSON-RPC result payload.

        Raises:
            RuntimeError: If the server does not have an outbound client request
                handler configured.
        """
        if self._client_request_handler is None:
            raise RuntimeError(
                "No client request handler is configured for outbound MCP requests"
            )
        return await self._client_request_handler(method, params)

    def _iter_repo_access_nodes(
        self: _RepoAccessRuntime, payload: Any
    ) -> list[dict[str, Any]]:
        """Collect every ``repo_access`` payload embedded in a tool result.

        Args:
            payload: Any JSON-serializable tool result payload.

        Returns:
            The list of discovered ``repo_access`` objects.
        """
        nodes: list[dict[str, Any]] = []

        def walk(value: Any) -> None:
            """Walk nested payload values and collect repo access entries."""
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            repo_access = value.get("repo_access")
            if isinstance(repo_access, dict):
                nodes.append(repo_access)
            for child in value.values():
                walk(child)

        walk(payload)
        return nodes

    def _repo_access_elicitation_request(
        self: _RepoAccessRuntime, repo_access: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the elicitation form for resolving local repository access.

        Args:
            repo_access: The repo access metadata emitted by a tool response.

        Returns:
            A JSON schema request payload for ``elicitation/create``.
        """
        repo_slug = (
            repo_access.get("repo_slug") or repo_access.get("repo_id") or "repository"
        )
        remote_url = repo_access.get("remote_url")
        message = (
            f"PlatformContextGraph can see {repo_slug} on the server, but it needs your local checkout details "
            "to help with local file access."
        )
        if remote_url:
            message += f" Remote: {remote_url}"
        return {
            "message": message,
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "title": "How should PCG continue?",
                        "oneOf": [
                            {
                                "const": "use_local_checkout",
                                "title": "Use an existing local checkout",
                            },
                            {
                                "const": "clone_locally",
                                "title": "Clone the repository locally",
                            },
                            {
                                "const": "skip",
                                "title": "Skip local file access for now",
                            },
                        ],
                        "default": "use_local_checkout",
                    },
                    "local_path": {
                        "type": "string",
                        "title": "Local checkout path",
                        "description": "Absolute path to the repository on your machine, if it already exists.",
                    },
                    "clone_base_path": {
                        "type": "string",
                        "title": "Clone base path",
                        "description": "Base directory where the client should clone the repository locally.",
                    },
                },
                "required": ["action"],
            },
        }

    async def _apply_repo_access_handoff(
        self: _RepoAccessRuntime, payload: Any, *, transport: str
    ) -> Any:
        """Annotate repo access payloads and request local checkout details.

        Args:
            payload: The tool result payload to update in place.
            transport: The active MCP transport identifier.

        Returns:
            The updated payload.
        """
        repo_access_nodes = self._iter_repo_access_nodes(payload)
        interaction_mode = (
            "elicitation"
            if self._supports_elicitation(transport=transport)
            else "conversational"
        )
        for repo_access in repo_access_nodes:
            repo_access["interaction_mode"] = interaction_mode

        if interaction_mode != "elicitation":
            return payload

        processed_repo_ids: set[str] = set()
        for repo_access in repo_access_nodes:
            repo_id = repo_access.get("repo_id")
            if not repo_id or repo_id in processed_repo_ids:
                continue
            processed_repo_ids.add(repo_id)
            if repo_access.get("state") != "needs_local_checkout":
                continue
            if repo_access.get("recommended_action") != "ask_user_for_local_path":
                continue

            result = await self._request_client(
                "elicitation/create",
                self._repo_access_elicitation_request(repo_access),
            )
            action = str(result.get("action", "cancel"))
            content = result.get("content") or {}
            repo_access["user_response_action"] = action

            if action != "accept":
                continue

            chosen_action = str(
                content.get("action") or repo_access["recommended_action"]
            )
            if chosen_action == "use_local_checkout" and content.get("local_path"):
                repo_access["recommended_action"] = "use_local_checkout"
                repo_access["state"] = "available"
                repo_access["client_local_path"] = str(content["local_path"])
            elif chosen_action == "clone_locally":
                repo_access["recommended_action"] = "clone_locally"
                if content.get("clone_base_path"):
                    repo_access["clone_base_path"] = str(content["clone_base_path"])

        return payload
