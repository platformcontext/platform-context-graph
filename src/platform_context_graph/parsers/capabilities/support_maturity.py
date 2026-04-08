"""Support-maturity rendering helpers for parser capability specs."""

from __future__ import annotations

from .models import AUTO_GENERATED_BANNER, LanguageCapabilitySpec, SupportMaturitySpec


def render_support_maturity_matrix(specs: list[LanguageCapabilitySpec]) -> str:
    """Render the cross-language support-maturity matrix."""

    lines = [
        "# Parser Support Maturity Matrix",
        "",
        AUTO_GENERATED_BANNER,
        "",
        "This matrix tracks the higher-level support bar for each parser beyond",
        "the raw capability checklist. `-` means that maturity dimension has not",
        "yet been explicitly assessed in the parser maturity program.",
        "",
        "| Parser | Parser Class | Grammar Routing | Normalization | Framework Packs | Pack Names | Query Surfacing | Real-Repo Validation | End-to-End Indexing |",
        "|--------|--------------|-----------------|---------------|-----------------|------------|-----------------|----------------------|---------------------|",
    ]
    for spec in specs:
        maturity = spec.get("support_maturity") or {}
        lines.append(
            "| {title} | `{parser}` | {grammar} | {normalization} | {frameworks} | {pack_names} | {query} | {repo_validation} | {end_to_end} |".format(
                title=spec["title"].replace(" Parser", ""),
                parser=spec["parser"],
                grammar=_maturity_value(maturity, "grammar_routing"),
                normalization=_maturity_value(maturity, "normalization"),
                frameworks=_maturity_value(maturity, "framework_packs"),
                pack_names=_pack_names(maturity),
                query=_maturity_value(maturity, "query_surfacing"),
                repo_validation=_maturity_value(maturity, "real_repo_validation"),
                end_to_end=_maturity_value(maturity, "end_to_end_indexing"),
            )
        )
    return "\n".join(lines) + "\n"


def render_support_maturity_section(spec: LanguageCapabilitySpec) -> list[str]:
    """Render the optional support-maturity section for one language doc."""

    maturity = spec.get("support_maturity")
    if not isinstance(maturity, dict) or not maturity:
        return []

    lines = [
        "## Support Maturity",
        f"- Grammar routing: `{_maturity_value(maturity, 'grammar_routing')}`",
        f"- Normalization: `{_maturity_value(maturity, 'normalization')}`",
        f"- Framework pack status: `{_maturity_value(maturity, 'framework_packs')}`",
        f"- Framework packs: {_pack_names(maturity)}",
        f"- Query surfacing: `{_maturity_value(maturity, 'query_surfacing')}`",
        f"- Real-repo validation: `{_maturity_value(maturity, 'real_repo_validation')}`",
        f"- End-to-end indexing: `{_maturity_value(maturity, 'end_to_end_indexing')}`",
    ]
    examples = maturity.get("real_repo_examples") or []
    if examples:
        lines.append("- Local repo validation evidence:")
        lines.extend(f"  - `{example}`" for example in examples if example)
    notes = maturity.get("notes") or []
    if notes:
        lines.append("- Notes:")
        lines.extend(f"  - {note}" for note in notes if note)
    lines.append("")
    return lines


def _maturity_value(maturity: SupportMaturitySpec, key: str) -> str:
    """Return one maturity value or `-` when not declared."""

    value = maturity.get(key)
    if isinstance(value, str) and value:
        return value
    return "-"


def _pack_names(maturity: SupportMaturitySpec) -> str:
    """Return one rendered framework-pack list or `-`."""

    names = [
        str(name).strip()
        for name in maturity.get("framework_pack_names") or []
        if str(name).strip()
    ]
    if not names:
        return "-"
    return ", ".join(f"`{name}`" for name in names)


__all__ = ["render_support_maturity_matrix", "render_support_maturity_section"]
