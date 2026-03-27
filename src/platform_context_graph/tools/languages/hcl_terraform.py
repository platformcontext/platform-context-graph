"""Tree-sitter HCL/Terraform parser facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...utils.tree_sitter_manager import get_tree_sitter_manager
from .hcl_terraform_support import parse_hcl_document


class HCLTerraformParser:
    """Parse Terraform and Terragrunt files using the HCL tree-sitter grammar."""

    def __init__(self, generic_parser_wrapper: Any) -> None:
        """Bind to a shared wrapper or create a standalone HCL parser.

        Args:
            generic_parser_wrapper: Either a tree-sitter wrapper instance or the
                string language name used for direct construction in tests.
        """

        if isinstance(generic_parser_wrapper, str):
            manager = get_tree_sitter_manager()
            self.language_name = generic_parser_wrapper
            self.language = manager.get_language_safe(self.language_name)
            self.parser = manager.create_parser(self.language_name)
            self.generic_parser_wrapper = None
            return

        self.generic_parser_wrapper = generic_parser_wrapper
        self.language_name = generic_parser_wrapper.language_name
        self.language = generic_parser_wrapper.language
        self.parser = generic_parser_wrapper.parser

    def parse(
        self,
        path: Path | str,
        is_dependency: bool = False,
        *,
        index_source: bool = False,
    ) -> dict[str, Any]:
        """Parse one HCL file into Terraform or Terragrunt graph payloads."""

        file_path = Path(path)
        source_bytes = file_path.read_bytes()
        tree = self.parser.parse(source_bytes)
        result = parse_hcl_document(
            tree.root_node,
            source_bytes,
            path=str(file_path),
            is_terragrunt=file_path.name.lower() == "terragrunt.hcl",
        )
        result["is_dependency"] = is_dependency
        if index_source:
            result["source"] = source_bytes.decode("utf-8", "ignore")
        return result


__all__ = ["HCLTerraformParser"]
