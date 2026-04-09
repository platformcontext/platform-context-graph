"""Strategy helpers for provider SDK semantic packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import FrameworkPackSpec


def build_provider_sdk_semantics(
    _path: Path,
    _source_code: str,
    *,
    imports: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    pack_spec: FrameworkPackSpec,
) -> dict[str, Any] | None:
    """Build bounded provider SDK semantics from import and constructor facts."""

    config = pack_spec.get("config", {})
    import_source_prefixes = _config_string_list(config, "import_source_prefixes")
    client_name_suffixes = _config_string_list(config, "client_name_suffixes")

    services: list[str] = []
    direct_client_symbols: set[str] = set()
    namespace_aliases: set[str] = set()
    for item in imports:
        source = _normalized_string(item.get("source") or item.get("name"))
        if not source:
            continue
        for prefix in import_source_prefixes:
            if not source.startswith(prefix):
                continue
            service = _normalized_string(source.removeprefix(prefix))
            if service and service not in services:
                services.append(service)
            direct_name = _normalized_string(item.get("name"))
            alias = _normalized_string(item.get("alias"))
            for candidate in _imported_client_candidates(item):
                if _has_suffix(candidate, client_name_suffixes):
                    direct_client_symbols.add(candidate)
            if direct_name == "*":
                if alias:
                    namespace_aliases.add(alias)
                continue
            if alias and direct_name and direct_name not in {"default", "*"}:
                namespace_aliases.add(alias)

    client_symbols: list[str] = []
    if services:
        for call in function_calls:
            name = _normalized_string(call.get("name"))
            full_name = _normalized_string(call.get("full_name"))
            if not name:
                continue
            if (
                (
                    name in direct_client_symbols
                    or (
                        _has_suffix(name, client_name_suffixes)
                        and full_name
                        and any(
                            full_name.startswith(f"new {alias}.")
                            for alias in namespace_aliases
                        )
                    )
                )
                and full_name
                and full_name.startswith("new ")
                and name not in client_symbols
            ):
                client_symbols.append(name)

    if not services and not client_symbols:
        return None

    return {
        "services": services,
        "client_symbols": client_symbols,
    }


def _config_string_list(config: object, key: str) -> list[str]:
    """Return one config string list with empty items removed."""

    if not isinstance(config, dict):
        return []
    value = config.get(key)
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        normalized = _normalized_string(item)
        if normalized:
            items.append(normalized)
    return items


def _normalized_string(value: object) -> str | None:
    """Return one stripped string when available."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _has_suffix(value: str, suffixes: list[str]) -> bool:
    """Return whether the value ends with one of the configured suffixes."""

    return any(value.endswith(suffix) for suffix in suffixes)


def _imported_client_candidates(item: dict[str, Any]) -> list[str]:
    """Return imported binding names that may represent provider clients."""

    candidates: list[str] = []
    name = _normalized_string(item.get("name"))
    alias = _normalized_string(item.get("alias"))
    if name and name not in {"default", "*"} and not name.startswith("@"):
        candidates.append(name)
    if alias:
        candidates.extend(_parse_import_alias_bindings(alias))
    return list(dict.fromkeys(candidates))


def _parse_import_alias_bindings(alias: str) -> list[str]:
    """Return binding names from one import alias field."""

    normalized = alias.strip()
    if not normalized:
        return []
    if normalized.startswith("{") and normalized.endswith("}"):
        bindings: list[str] = []
        inner = normalized[1:-1]
        for raw_part in inner.split(","):
            part = raw_part.strip()
            if not part:
                continue
            if " as " in part:
                _original, local_alias = part.split(" as ", 1)
                bindings.append(local_alias.strip())
            else:
                bindings.append(part)
        return bindings
    return [normalized]


__all__ = ["build_provider_sdk_semantics"]
