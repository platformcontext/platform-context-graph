"""Foundational plugin registry for data-intelligence adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DataIntelligencePlugin(Protocol):
    """Contract implemented by warehouse, BI, and semantic replay adapters."""

    name: str
    category: str
    replay_fixture_groups: tuple[str, ...]

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one adapter payload into the generic PCG data model."""


@dataclass(frozen=True)
class _RegisteredPlugin:
    """Immutable plugin snapshot returned by the registry."""

    name: str
    category: str
    replay_fixture_groups: tuple[str, ...]
    normalize: Any


class DataIntelligenceRegistry:
    """In-memory registry for vendor-neutral data-intelligence plugins."""

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""

        self._plugins: dict[str, _RegisteredPlugin] = {}

    def register(self, plugin: DataIntelligencePlugin) -> None:
        """Register one plugin by unique public name.

        Args:
            plugin: Plugin implementation to store.

        Raises:
            ValueError: If another plugin with the same name already exists.
        """

        if plugin.name in self._plugins:
            raise ValueError(
                f"Data-intelligence plugin '{plugin.name}' is already registered"
            )
        self._plugins[plugin.name] = _RegisteredPlugin(
            name=plugin.name,
            category=plugin.category,
            replay_fixture_groups=tuple(plugin.replay_fixture_groups),
            normalize=plugin.normalize,
        )

    def list_plugins(self) -> list[DataIntelligencePlugin]:
        """Return registered plugins in stable registration order."""

        return list(self._plugins.values())
