"""Compatibility facade for YAML infrastructure parsing."""

from pathlib import Path
from typing import Any, Callable

from ...utils.debug_log import warning_logger
from .cloudformation import is_cloudformation_template, parse_cloudformation_template
from .argocd import (
    is_argocd_application,
    is_argocd_applicationset,
    parse_argocd_application,
    parse_argocd_applicationset,
)
from .crossplane import (
    is_crossplane_claim,
    is_crossplane_composition,
    is_crossplane_xrd,
    parse_crossplane_claim,
    parse_crossplane_composition,
    parse_crossplane_xrd,
)
from .helm import (
    is_helm_chart,
    is_helm_template_manifest,
    is_helm_values,
    parse_helm_chart,
    parse_helm_values,
)
from .kubernetes_manifest import has_k8s_api_version, parse_k8s_resource
from .kustomize import is_kustomization, parse_kustomization
from .yaml_infra_support import (
    build_empty_result,
    compute_doc_line_offsets,
    safe_load_all,
)

ResourcePredicate = Callable[[str, str], bool]
ResourceParser = Callable[..., dict[str, Any]]
_DOCUMENT_PARSERS: tuple[tuple[str, ResourcePredicate, ResourceParser], ...] = (
    ("argocd_applications", is_argocd_application, parse_argocd_application),
    ("argocd_applicationsets", is_argocd_applicationset, parse_argocd_applicationset),
    ("crossplane_xrds", is_crossplane_xrd, parse_crossplane_xrd),
    (
        "crossplane_compositions",
        is_crossplane_composition,
        parse_crossplane_composition,
    ),
)


class InfraYAMLParser:
    """Parse infrastructure YAML files into graph-friendly resource buckets."""

    def __init__(self, language_name: str) -> None:
        """Store the language name used in parse results.

        Args:
            language_name: Language identifier, typically ``"yaml"``.
        """
        self.language_name = language_name

    def parse(
        self,
        path: str,
        is_dependency: bool = False,
        index_source: bool = True,
    ) -> dict[str, Any]:
        """Parse YAML infrastructure resources using semantic dispatchers.

        Args:
            path: Absolute path to the YAML file.
            is_dependency: Whether the file belongs to dependency code.
            index_source: Compatibility argument preserved for callers.

        Returns:
            Parsed infrastructure resources and standard parser metadata.
        """
        del index_source
        result = build_empty_result(path, self.language_name, is_dependency)
        file_path = Path(path)
        filename = file_path.name

        if is_helm_chart(filename):
            chart = parse_helm_chart(file_path, self.language_name)
            if chart is not None:
                result["helm_charts"].append(chart)
            return result

        if is_helm_values(filename):
            values = parse_helm_values(file_path, self.language_name)
            if values is not None:
                result["helm_values"].append(values)
            return result

        if is_helm_template_manifest(file_path):
            return result

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warning_logger(f"Cannot read {path}: {exc}")
            return result

        documents = safe_load_all(content)
        if not documents:
            return result

        line_offsets = compute_doc_line_offsets(content)
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                continue
            line_number = line_offsets[index] if index < len(line_offsets) else 1
            self._append_document_result(
                result=result,
                document=document,
                path=path,
                filename=filename,
                line_number=line_number,
            )

        return result

    def _append_document_result(
        self,
        *,
        result: dict[str, Any],
        document: dict[str, Any],
        path: str,
        filename: str,
        line_number: int,
    ) -> None:
        """Append one parsed YAML document into the correct result bucket.

        Args:
            result: Mutable parse result to populate.
            document: Parsed YAML document.
            path: Source file path.
            filename: Basename of the YAML file.
            line_number: 1-based document start line.
        """
        # CloudFormation detection — must run before apiVersion/kind checks
        # because CFN templates use AWSTemplateFormatVersion/Resources instead.
        if is_cloudformation_template(document):
            cfn_data = parse_cloudformation_template(
                document, path, line_number, self.language_name
            )
            result["cloudformation_resources"].extend(
                cfn_data.get("cloudformation_resources", [])
            )
            result["cloudformation_parameters"].extend(
                cfn_data.get("cloudformation_parameters", [])
            )
            result["cloudformation_outputs"].extend(
                cfn_data.get("cloudformation_outputs", [])
            )
            return

        api_version = document.get("apiVersion", "")
        kind = document.get("kind", "")
        metadata = document.get("metadata", {}) or {}

        if is_kustomization(api_version, kind, filename):
            result["kustomize_overlays"].append(
                parse_kustomization(document, path, line_number, self.language_name)
            )
            return

        if not api_version or not kind:
            return

        for bucket_name, predicate, parser in _DOCUMENT_PARSERS:
            if predicate(api_version, kind):
                result[bucket_name].append(
                    parser(document, metadata, path, line_number, self.language_name)
                )
                return

        if is_crossplane_claim(api_version, kind):
            result["crossplane_claims"].append(
                parse_crossplane_claim(
                    metadata,
                    api_version,
                    kind,
                    path,
                    line_number,
                    self.language_name,
                )
            )
            return

        if has_k8s_api_version(api_version):
            result["k8s_resources"].append(
                parse_k8s_resource(
                    document,
                    metadata,
                    api_version,
                    kind,
                    path,
                    line_number,
                    self.language_name,
                )
            )
