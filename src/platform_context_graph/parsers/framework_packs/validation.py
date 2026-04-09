"""Validation helpers for declarative framework semantic packs."""

from __future__ import annotations

from .models import FrameworkPackSpec, SUPPORTED_FRAMEWORK_PACK_STRATEGIES


def validate_framework_pack_spec(spec: FrameworkPackSpec) -> list[str]:
    """Validate one framework-pack spec payload."""

    spec_path = str(spec.get("spec_path", "<unknown>"))
    errors: list[str] = []
    for key in (
        "framework",
        "title",
        "strategy",
        "compute_order",
        "surface_order",
        "config",
        "spec_path",
    ):
        if key not in spec:
            errors.append(f"{spec_path}: missing required field '{key}'")

    framework = spec.get("framework")
    if framework is not None and not isinstance(framework, str):
        errors.append(f"{spec_path}: field 'framework' must be a string")
    elif isinstance(framework, str) and not framework.strip():
        errors.append(f"{spec_path}: field 'framework' must not be empty")

    title = spec.get("title")
    if title is not None and not isinstance(title, str):
        errors.append(f"{spec_path}: field 'title' must be a string")
    elif isinstance(title, str) and not title.strip():
        errors.append(f"{spec_path}: field 'title' must not be empty")

    strategy = spec.get("strategy")
    if strategy is not None and not isinstance(strategy, str):
        errors.append(f"{spec_path}: field 'strategy' must be a string")
    elif (
        isinstance(strategy, str)
        and strategy not in SUPPORTED_FRAMEWORK_PACK_STRATEGIES
    ):
        errors.append(f"{spec_path}: unknown strategy '{strategy}'")

    for key in ("compute_order", "surface_order"):
        value = spec.get(key)
        if value is not None and not isinstance(value, int):
            errors.append(f"{spec_path}: field '{key}' must be an integer")

    languages = spec.get("languages")
    if languages is not None and not isinstance(languages, list):
        errors.append(f"{spec_path}: field 'languages' must be a list of strings")
    elif isinstance(languages, list):
        invalid = [item for item in languages if not isinstance(item, str) or not item]
        if invalid:
            errors.append(
                f"{spec_path}: field 'languages' must contain only non-empty strings"
            )

    config = spec.get("config")
    if config is not None and not isinstance(config, dict):
        errors.append(f"{spec_path}: field 'config' must be a mapping")

    return errors
