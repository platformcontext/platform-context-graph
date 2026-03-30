"""Schema-driven Terraform resource extractor.

Registers extractors for every resource type found in provider schema JSON
files.  Resource types that already have a hand-written extractor (registered
by the provider modules) are skipped — the hand-written logic is treated as
an override with richer extraction for that specific type.

The schema is the single source of truth for which resource types exist in a
given provider version.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ._base import (
    ExtractionContext,
    ResourceExtractorFn,
    ResourceRelationship,
    first_quoted_value,
    get_registered_resource_types,
    register_resource_extractor,
)
from .provider_schema import (
    classify_resource_category,
    infer_identity_keys,
    load_provider_schema,
)

logger = logging.getLogger(__name__)

# Terraform resource names that are too generic to be useful as candidates.
_GENERIC_RESOURCE_NAMES = frozenset(
    {
        "main",
        "this",
        "default",
        "primary",
        "example",
        "test",
        "temp",
        "tmp",
    }
)

# Confidence when a named identity attribute is found in the resource body
# (e.g. name = "my-service").  On par with manual extractors for similar
# extraction quality.
_IDENTITY_KEY_CONFIDENCE = 0.78

# Confidence when falling back to the Terraform resource label
# (e.g. resource "aws_foo" "my_service" — "my_service" used as candidate).
_RESOURCE_NAME_FALLBACK_CONFIDENCE = 0.55

# Default location: bundled schemas alongside this package.
_DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


def make_generic_extractor(
    identity_keys: list[str],
    category: str,
) -> ResourceExtractorFn:
    """Create an extractor closure for a resource type.

    Args:
        identity_keys: Attribute names to try when extracting a resource name.
        category: Service category (compute, storage, etc.) for rationale text.

    Returns:
        An extractor function compatible with the registry interface.
    """

    def _extract(
        ctx: ExtractionContext,
        resource_type: str,
        resource_name: str,
        body: str,
    ) -> list[ResourceRelationship]:
        """Extract a candidate name from the resource body using identity keys."""
        # Try each identity key in preference order.
        candidate = None
        matched_key = None
        confidence = _IDENTITY_KEY_CONFIDENCE
        for key in identity_keys:
            value = first_quoted_value(body, key)
            if value:
                candidate = value
                matched_key = key
                break

        # Fall back to resource_name if it looks meaningful.
        if not candidate:
            if resource_name and resource_name.lower() not in _GENERIC_RESOURCE_NAMES:
                candidate = resource_name
                matched_key = "resource_name"
                confidence = _RESOURCE_NAME_FALLBACK_CONFIDENCE

        if not candidate:
            return []

        # Build evidence kind: aws_wafv2_web_acl → TERRAFORM_WAFV2_WEB_ACL
        _, _, suffix = resource_type.partition("_")
        evidence_kind = "TERRAFORM_" + suffix.upper()

        return [
            ResourceRelationship(
                evidence_kind=evidence_kind,
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=confidence,
                rationale=(
                    f"Terraform {resource_type} provisions "
                    f"{category} infrastructure"
                ),
                candidate_name=candidate,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "identity_key": matched_key,
                    "category": category,
                    "schema_driven": True,
                },
            )
        ]

    return _extract


def register_schema_driven_extractors(
    schemas_dir: Path | None = None,
) -> dict[str, int]:
    """Register extractors for all resource types in provider schemas.

    Scans ``schemas_dir`` for provider schema JSON files.  For each resource
    type that has at least one inferable identity key, an extractor is
    registered.  Types that already have a hand-written extractor (from the
    provider modules) are skipped — those serve as overrides with richer
    extraction logic.

    Args:
        schemas_dir: Directory containing provider schema JSON files.
            Falls back to ``PCG_TERRAFORM_SCHEMA_DIR`` env var, then
            ``{project_root}/schemas/``.

    Returns:
        Mapping of provider name → count of newly registered types.
    """

    if schemas_dir is None:
        env_dir = os.environ.get("PCG_TERRAFORM_SCHEMA_DIR")
        schemas_dir = Path(env_dir) if env_dir else _DEFAULT_SCHEMAS_DIR

    if not schemas_dir.is_dir():
        logger.debug("No terraform schemas directory at %s, skipping", schemas_dir)
        return {}

    already_registered = get_registered_resource_types()
    summary: dict[str, int] = {}

    for schema_file in sorted(schemas_dir.glob("*.json*")):
        schema = load_provider_schema(schema_file)
        if schema is None:
            continue

        registered_count = 0
        for resource_type, attributes in schema.resource_types.items():
            if resource_type in already_registered:
                continue

            identity_keys = infer_identity_keys(attributes)
            category = classify_resource_category(resource_type)
            extractor = make_generic_extractor(identity_keys, category)
            register_resource_extractor([resource_type], extractor)
            already_registered.add(resource_type)
            registered_count += 1

        if registered_count:
            logger.info(
                "Registered %d schema-driven extractors from %s (%s)",
                registered_count,
                schema_file.name,
                schema.provider_name,
            )
        summary[schema.provider_name] = registered_count

    return summary


__all__ = [
    "make_generic_extractor",
    "register_schema_driven_extractors",
]
