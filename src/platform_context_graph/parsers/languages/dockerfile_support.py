"""Helpers for extracting structured metadata from Dockerfiles."""

from __future__ import annotations

from typing import Any


def parse_dockerfile_tree(root_node: Any, source_bytes: bytes) -> dict[str, Any]:
    """Return structured Dockerfile entities extracted from one syntax tree."""

    stages: list[dict[str, Any]] = []
    ports: list[dict[str, Any]] = []
    args: list[dict[str, Any]] = []
    envs: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    current_stage: dict[str, Any] | None = None

    for node in root_node.children:
        if node.type == "from_instruction":
            current_stage = _parse_stage(node, source_bytes, len(stages))
            stages.append(current_stage)
            continue
        if node.type == "arg_instruction":
            args.extend(_parse_arg_instruction(node, source_bytes, current_stage))
            continue
        if node.type == "env_instruction":
            envs.extend(_parse_env_instruction(node, source_bytes, current_stage))
            continue
        if node.type == "expose_instruction":
            ports.extend(_parse_expose_instruction(node, source_bytes, current_stage))
            continue
        if node.type == "label_instruction":
            labels.extend(_parse_label_instruction(node, source_bytes, current_stage))
            continue
        if current_stage is None:
            continue
        if node.type == "copy_instruction":
            _annotate_copy_from(node, source_bytes, current_stage)
        elif node.type == "workdir_instruction":
            current_stage["workdir"] = _last_non_keyword_child_text(node, source_bytes)
        elif node.type == "entrypoint_instruction":
            current_stage["entrypoint"] = _last_non_keyword_child_text(
                node, source_bytes
            )
        elif node.type == "cmd_instruction":
            current_stage["cmd"] = _last_non_keyword_child_text(node, source_bytes)
        elif node.type == "user_instruction":
            current_stage["user"] = _last_non_keyword_child_text(node, source_bytes)
        elif node.type == "healthcheck_instruction":
            current_stage["healthcheck"] = " ".join(
                _node_text(source_bytes, child).strip()
                for child in node.children
                if child.is_named
            ).strip()

    return {
        "dockerfile_stages": stages,
        "dockerfile_ports": ports,
        "dockerfile_args": args,
        "dockerfile_envs": envs,
        "dockerfile_labels": labels,
    }


def _parse_stage(node: Any, source_bytes: bytes, stage_index: int) -> dict[str, Any]:
    """Parse one Dockerfile FROM instruction into a stage row."""

    image_name = ""
    base_tag = ""
    alias = ""
    for child in node.children:
        if child.type == "image_spec":
            for image_child in child.children:
                if image_child.type == "image_name":
                    image_name = _node_text(source_bytes, image_child)
                elif image_child.type == "image_tag":
                    base_tag = _node_text(source_bytes, image_child).lstrip(":")
        elif child.type == "image_alias":
            alias = _node_text(source_bytes, child)

    name = alias or image_name or f"stage_{stage_index}"
    return {
        "name": name,
        "line_number": node.start_point.row + 1,
        "stage_index": stage_index,
        "base_image": image_name,
        "base_tag": base_tag,
        "alias": alias,
    }


def _parse_arg_instruction(
    node: Any,
    source_bytes: bytes,
    current_stage: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Parse one Dockerfile ARG instruction."""

    values = [
        _node_text(source_bytes, child) for child in node.children if child.is_named
    ]
    if not values:
        return []
    result = {
        "name": values[0],
        "line_number": node.start_point.row + 1,
        "default_value": values[1] if len(values) > 1 else "",
    }
    if current_stage is not None:
        result["stage"] = str(current_stage["name"])
    return [result]


def _parse_env_instruction(
    node: Any,
    source_bytes: bytes,
    current_stage: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Parse one Dockerfile ENV instruction into env pairs."""

    rows: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "env_pair":
            continue
        values = [
            _node_text(source_bytes, grandchild)
            for grandchild in child.children
            if grandchild.is_named
        ]
        if len(values) < 2:
            continue
        row = {
            "name": values[0],
            "value": values[1],
            "line_number": child.start_point.row + 1,
        }
        if current_stage is not None:
            row["stage"] = str(current_stage["name"])
        rows.append(row)
    return rows


def _parse_expose_instruction(
    node: Any,
    source_bytes: bytes,
    current_stage: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Parse one Dockerfile EXPOSE instruction into port rows."""

    stage_name = str(current_stage["name"]) if current_stage is not None else "global"
    rows: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "expose_port":
            continue
        raw_value = _node_text(source_bytes, child).strip()
        port, _, protocol = raw_value.partition("/")
        rows.append(
            {
                "name": f"{stage_name}:{port}",
                "port": port,
                "protocol": protocol or "tcp",
                "line_number": child.start_point.row + 1,
                "stage": stage_name,
            }
        )
    return rows


def _parse_label_instruction(
    node: Any,
    source_bytes: bytes,
    current_stage: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Parse one Dockerfile LABEL instruction into label rows."""

    rows: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "label_pair":
            continue
        values = [
            _strip_wrapping_quotes(_node_text(source_bytes, grandchild))
            for grandchild in child.children
            if grandchild.is_named
        ]
        if len(values) < 2:
            continue
        row = {
            "name": values[0],
            "value": values[1],
            "line_number": child.start_point.row + 1,
        }
        if current_stage is not None:
            row["stage"] = str(current_stage["name"])
        rows.append(row)
    return rows


def _annotate_copy_from(
    node: Any,
    source_bytes: bytes,
    current_stage: dict[str, Any],
) -> None:
    """Capture COPY --from metadata on the current stage row."""

    for child in node.children:
        if child.type != "param":
            continue
        raw_value = _node_text(source_bytes, child).strip()
        if raw_value.startswith("--from="):
            current_stage["copies_from"] = raw_value.split("=", 1)[1]
            return


def _last_non_keyword_child_text(node: Any, source_bytes: bytes) -> str:
    """Return the last meaningful child text from one instruction node."""

    texts = [
        _node_text(source_bytes, child).strip()
        for child in node.children
        if child.is_named
    ]
    return texts[-1] if texts else ""


def _node_text(source_bytes: bytes, node: Any) -> str:
    """Return the exact source text for one syntax node."""

    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", "ignore")


def _strip_wrapping_quotes(value: str) -> str:
    """Remove one pair of wrapping quotes from a string literal."""

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


__all__ = ["parse_dockerfile_tree"]
