"""Rendering helpers for ``pcg analyze`` graph commands."""

from __future__ import annotations

from typing import Any


def render_call_chains(console: Any, results: list[dict[str, Any]]) -> None:
    """Render call-chain results to the Rich console.

    Each chain is printed as an indented tree where every level shows the
    function name, file path, and line number.  Intermediate edges display
    the call-site line number and (optionally) truncated argument text.

    Args:
        console: A ``rich.console.Console`` instance used for output.
        results: A list of chain dicts, each containing ``chain_length``,
            ``function_chain``, and ``call_details`` keys.
    """
    for index, chain in enumerate(results, 1):
        console.print(
            f"\n[bold cyan]Call Chain #{index} "
            f"(length: {chain.get('chain_length', 0)}):[/bold cyan]"
        )
        functions = chain.get("function_chain", [])
        call_details = chain.get("call_details", [])

        for position, function_info in enumerate(functions):
            indent = "  " * position
            console.print(
                f"{indent}[cyan]{function_info.get('name', 'Unknown')}[/cyan] "
                f"[dim]({function_info.get('path', '')}:"
                f"{function_info.get('line_number', '')})[/dim]"
            )

            if position < len(functions) - 1 and position < len(call_details):
                detail = call_details[position]
                line = detail.get("call_line", "?")
                args_info = _format_call_args(detail.get("args", []))
                console.print(f"{indent}  ⬇ [dim]calls at line {line}[/dim]{args_info}")


def _format_call_args(args_value: list[str] | str | None) -> str:
    """Format call arguments into a truncated Rich markup string.

    Args:
        args_value: Raw argument data -- either a list of token strings,
            a single string, or ``None`` / empty list.

    Returns:
        A Rich-markup string such as ``" [dim](a, b)[/dim]"`` or ``""``
        when there are no arguments to display.
    """
    if not args_value:
        return ""
    if isinstance(args_value, list):
        clean_args = [str(arg) for arg in args_value if str(arg) not in ("(", ")", ",")]
        args_str = ", ".join(clean_args)
    else:
        args_str = str(args_value)
    if len(args_str) > 50:
        args_str = args_str[:47] + "..."
    return f" [dim]({args_str})[/dim]"
