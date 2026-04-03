"""Call extraction helpers for the Dart parser."""

from __future__ import annotations

from typing import Any, Callable

RecordCall = Callable[..., None]


def find_calls(
    *,
    root_node: Any,
    language_name: str,
    get_node_text: Callable[[Any], str],
    get_parent_context: Callable[[Any], tuple[str | None, str | None, int | None]],
    get_declaration_name: Callable[[Any], Any],
) -> list[dict[str, Any]]:
    """Find Dart call expressions."""

    calls = []
    seen_calls = set()

    def maybe_record_call(
        name_node: Any, *, full_name: str, selector_node: Any
    ) -> None:
        """Record one Dart call if it has not been seen yet."""

        name = get_node_text(name_node)
        line_number = name_node.start_point[0] + 1
        call_key = (name, full_name, line_number)
        if call_key in seen_calls:
            return
        seen_calls.add(call_key)

        context, context_type, context_line = get_parent_context(name_node)
        calls.append(
            {
                "name": name,
                "full_name": full_name,
                "line_number": line_number,
                "args": extract_arguments(selector_node, get_node_text),
                "context": (context, context_type, context_line),
                "class_context": find_enclosing_class_context(
                    name_node,
                    get_node_text=get_node_text,
                    get_declaration_name=get_declaration_name,
                ),
                "lang": language_name,
                "is_dependency": False,
            }
        )

    def walk(node: Any) -> None:
        """Traverse the Dart tree and collect function-style calls."""

        children = [child for child in node.children if child.is_named]
        for idx, child in enumerate(children):
            if child.type == "identifier":
                maybe_record_direct_call(
                    children,
                    idx,
                    child,
                    maybe_record_call,
                    get_node_text=get_node_text,
                )
                maybe_record_member_call(
                    children,
                    idx,
                    child,
                    maybe_record_call,
                    get_node_text=get_node_text,
                )
            walk(child)

    walk(root_node)
    return calls


def extract_arguments(
    selector_node: Any, get_node_text: Callable[[Any], str]
) -> list[str]:
    """Return argument texts from a selector that carries call arguments."""

    argument_part = next(
        (child for child in selector_node.children if child.type == "argument_part"),
        None,
    )
    arguments_node = None
    if argument_part is not None:
        arguments_node = next(
            (child for child in argument_part.children if child.type == "arguments"),
            None,
        )
    elif selector_node.type == "arguments":
        arguments_node = selector_node

    if arguments_node is None:
        return []

    return [
        get_node_text(child)
        for child in arguments_node.children
        if child.type not in ("(", ")", ",")
    ]


def selector_member_name(selector_node: Any):
    """Return the member name from a dotted selector like `.map`."""

    for child in selector_node.children:
        if child.type != "unconditional_assignable_selector":
            continue
        for sub in child.children:
            if sub.type == "identifier":
                return sub
    return None


def selector_has_arguments(
    selector_node: Any, get_node_text: Callable[[Any], str]
) -> bool:
    """Return whether one selector carries an argument list."""

    if extract_arguments(selector_node, get_node_text):
        return True
    return any(child.type == "arguments" for child in selector_node.children)


def maybe_record_direct_call(
    children: list[Any],
    idx: int,
    child: Any,
    maybe_record_call: RecordCall,
    *,
    get_node_text: Callable[[Any], str],
) -> None:
    """Record one direct call like `foo()` when present."""

    if idx + 1 >= len(children) or children[idx + 1].type != "selector":
        return
    selector_node = children[idx + 1]
    if not selector_has_arguments(selector_node, get_node_text):
        return
    maybe_record_call(
        child,
        full_name=get_node_text(child),
        selector_node=selector_node,
    )


def maybe_record_member_call(
    children: list[Any],
    idx: int,
    child: Any,
    maybe_record_call: RecordCall,
    *,
    get_node_text: Callable[[Any], str],
) -> None:
    """Record one member call like `foo.bar()` when present."""

    if idx + 2 >= len(children):
        return
    first_selector = children[idx + 1]
    second_selector = children[idx + 2]
    member_name_node = selector_member_name(first_selector)
    if (
        first_selector.type != "selector"
        or member_name_node is None
        or second_selector.type != "selector"
        or not selector_has_arguments(second_selector, get_node_text)
    ):
        return
    maybe_record_call(
        member_name_node,
        full_name=f"{get_node_text(child)}.{get_node_text(member_name_node)}",
        selector_node=second_selector,
    )


def find_enclosing_class_context(
    node: Any,
    *,
    get_node_text: Callable[[Any], str],
    get_declaration_name: Callable[[Any], Any],
) -> str | None:
    """Return the nearest enclosing class, mixin, or extension name."""

    curr = node.parent
    while curr:
        if curr.type in (
            "class_definition",
            "mixin_declaration",
            "extension_declaration",
        ):
            class_name_node = get_declaration_name(curr)
            return get_node_text(class_name_node) if class_name_node else None
        curr = curr.parent
    return None
