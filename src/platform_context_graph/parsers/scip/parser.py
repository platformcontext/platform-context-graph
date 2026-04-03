"""SCIP protobuf parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...utils.debug_log import error_logger, info_logger


class ScipIndexParser:
    """Parse a SCIP protobuf index into PCG file and edge structures."""

    def parse(self, index_scip_path: Path, project_path: Path) -> Dict[str, Any]:
        """Parse ``index.scip`` and return file-level graph structures.

        Args:
            index_scip_path: Path to the generated ``index.scip`` file.
            project_path: Root project path used to resolve document paths.

        Returns:
            Parsed file and symbol table payload, or an empty mapping on failure.
        """

        try:
            from ...tools import scip_pb2  # type: ignore
        except ImportError:
            error_logger("scip_pb2.py not found in tools directory.")
            return {}

        try:
            with index_scip_path.open("rb") as handle:
                index = scip_pb2.Index()
                index.ParseFromString(handle.read())
        except Exception as exc:
            error_logger(f"Failed to parse SCIP index at {index_scip_path}: {exc}")
            return {}

        symbol_def_table: Dict[str, Dict[str, Any]] = {}
        for doc in index.documents:
            for occ in doc.occurrences:
                if occ.symbol.startswith("local "):
                    continue
                role = getattr(occ, "symbol_roles", getattr(occ, "role", 0))
                if role & 1:
                    symbol_def_table[occ.symbol] = {
                        "file": doc.relative_path,
                        "line": occ.range[0] + 1 if occ.range else 0,
                    }

        self._enrich_with_document_symbols(index, symbol_def_table)
        self._enrich_with_external_symbols(index, symbol_def_table)
        files_data = self._build_files_data(index, project_path, symbol_def_table)
        info_logger(
            "SCIP parse complete: "
            f"{len(files_data)} files, "
            f"{sum(len(v.get('function_calls_scip', [])) for v in files_data.values())} "
            "reference edges"
        )
        return {"files": files_data, "symbol_table": symbol_def_table}

    def _enrich_with_document_symbols(
        self,
        index: Any,
        symbol_def_table: Dict[str, Dict[str, Any]],
    ) -> None:
        """Populate definition metadata from document-local symbol tables.

        Args:
            index: Parsed SCIP index protobuf.
            symbol_def_table: Mutable symbol definition lookup table.
        """

        for doc in index.documents:
            for sym_info in doc.symbols:
                if sym_info.symbol in symbol_def_table:
                    symbol_def_table[sym_info.symbol][
                        "display_name"
                    ] = sym_info.display_name
                    symbol_def_table[sym_info.symbol]["documentation"] = "\n".join(
                        sym_info.documentation
                    )
                    symbol_def_table[sym_info.symbol]["kind"] = sym_info.kind

    def _enrich_with_external_symbols(
        self,
        index: Any,
        symbol_def_table: Dict[str, Dict[str, Any]],
    ) -> None:
        """Populate definition metadata from external symbols.

        Args:
            index: Parsed SCIP index protobuf.
            symbol_def_table: Mutable symbol definition lookup table.
        """

        for sym_info in index.external_symbols:
            if sym_info.symbol in symbol_def_table:
                symbol_def_table[sym_info.symbol][
                    "display_name"
                ] = sym_info.display_name
                symbol_def_table[sym_info.symbol]["documentation"] = "\n".join(
                    sym_info.documentation
                )
                symbol_def_table[sym_info.symbol]["kind"] = sym_info.kind

    def _build_files_data(
        self,
        index: Any,
        project_path: Path,
        symbol_def_table: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Build the final file payloads from SCIP documents.

        Args:
            index: Parsed SCIP index protobuf.
            project_path: Root project path used to resolve document paths.
            symbol_def_table: Symbol definition lookup table.

        Returns:
            File payloads keyed by absolute path.
        """

        files_data: Dict[str, Dict[str, Any]] = {}
        for doc in index.documents:
            rel_path = doc.relative_path
            abs_path = str((project_path / rel_path).resolve())
            file_data: Dict[str, Any] = {
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "function_calls_scip": [],
                "path": abs_path,
                "lang": self._lang_from_path(rel_path),
                "is_dependency": False,
            }

            definition_symbols_in_doc = []
            for occ in doc.occurrences:
                role = getattr(occ, "symbol_roles", getattr(occ, "role", 0))
                if role & 1:
                    definition_symbols_in_doc.append(occ)

            for occ in doc.occurrences:
                sym = occ.symbol
                if sym.startswith("local "):
                    continue
                line = occ.range[0] + 1 if occ.range else 0
                role = getattr(occ, "symbol_roles", getattr(occ, "role", 0))

                if role & 1:
                    self._append_definition_node(
                        file_data=file_data,
                        symbol=sym,
                        line=line,
                        definition=symbol_def_table.get(sym, {}),
                    )
                    continue

                self._append_reference_edge(
                    file_data=file_data,
                    symbol=sym,
                    line=line,
                    project_path=project_path,
                    symbol_def_table=symbol_def_table,
                    definition_symbols_in_doc=definition_symbols_in_doc,
                )

            files_data[abs_path] = file_data
        return files_data

    def _append_definition_node(
        self,
        *,
        file_data: Dict[str, Any],
        symbol: str,
        line: int,
        definition: Dict[str, Any],
    ) -> None:
        """Append a symbol definition node to the current file payload.

        Args:
            file_data: Mutable file payload.
            symbol: SCIP symbol identifier.
            line: Definition line number.
            definition: Symbol definition metadata.
        """

        kind = definition.get("kind", 0)
        if kind == 0:
            if symbol.endswith("()."):
                kind = 17
            elif "#" in symbol and symbol.endswith("#"):
                kind = 7
            elif "#" in symbol and symbol.endswith("()."):
                kind = 26

        display = definition.get("display_name", "")
        doc_str = definition.get("documentation", "")
        name = self._name_from_symbol(symbol)
        args, return_type = self._parse_signature(display)
        node = {
            "name": name,
            "line_number": line,
            "end_line": line,
            "docstring": doc_str or None,
            "lang": file_data["lang"],
            "is_dependency": False,
            "return_type": return_type,
            "args": args,
        }

        if kind in (26, 17):
            node["cyclomatic_complexity"] = 1
            node["decorators"] = []
            node["context"] = None
            node["class_context"] = None
            file_data["functions"].append(node)
        elif kind == 7:
            node["bases"] = []
            node["context"] = None
            file_data["classes"].append(node)
        elif kind in (61, 15):
            node["value"] = None
            node["type"] = return_type
            node["context"] = None
            node["class_context"] = None
            file_data["variables"].append(node)

    def _append_reference_edge(
        self,
        *,
        file_data: Dict[str, Any],
        symbol: str,
        line: int,
        project_path: Path,
        symbol_def_table: Dict[str, Dict[str, Any]],
        definition_symbols_in_doc: list[Any],
    ) -> None:
        """Append a reference edge when a symbol resolves to a known definition.

        Args:
            file_data: Mutable file payload.
            symbol: Referenced SCIP symbol identifier.
            line: Reference line number.
            project_path: Root project path used to resolve document paths.
            symbol_def_table: Symbol definition lookup table.
            definition_symbols_in_doc: Definition occurrences in the current document.
        """

        if symbol not in symbol_def_table:
            return
        callee_info = symbol_def_table[symbol]
        caller_sym = self._find_enclosing_definition(line, definition_symbols_in_doc)
        if not caller_sym:
            return
        caller_info = symbol_def_table.get(caller_sym, {})
        file_data["function_calls_scip"].append(
            {
                "caller_symbol": caller_sym,
                "caller_file": file_data["path"],
                "caller_line": caller_info.get("line", 0),
                "callee_symbol": symbol,
                "callee_file": str((project_path / callee_info["file"]).resolve()),
                "callee_line": callee_info["line"],
                "callee_name": self._name_from_symbol(symbol),
                "ref_line": line,
            }
        )

    def _name_from_symbol(self, symbol: str) -> str:
        """Extract a display name from a SCIP symbol identifier.

        Args:
            symbol: SCIP symbol identifier.

        Returns:
            Human-readable symbol name.
        """

        stripped = symbol.rstrip(".#")
        stripped = re.sub(r"\(\)\.?$", "", stripped)
        parts = re.split(r"[/#]", stripped)
        last = parts[-1] if parts else symbol
        return last or symbol

    def _lang_from_path(self, rel_path: str) -> str:
        """Infer a language name from a relative file path.

        Args:
            rel_path: Relative file path from the SCIP document.

        Returns:
            Inferred language name.
        """

        ext_map = {
            ".py": "python",
            ".ipynb": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "cpp",
        }
        return ext_map.get(Path(rel_path).suffix, "unknown")

    def _parse_signature(self, display_name: str) -> Tuple[List[str], Optional[str]]:
        """Extract argument names and return type from a display signature.

        Args:
            display_name: SCIP display-name or signature string.

        Returns:
            Tuple of argument names and optional return type.
        """

        args: List[str] = []
        return_type: Optional[str] = None
        if not display_name:
            return args, return_type

        if "->" in display_name:
            parts = display_name.rsplit("->", 1)
            return_type = parts[1].strip().rstrip(":")

        param_match = re.search(r"\(([^)]*)\)", display_name)
        if param_match:
            for param in param_match.group(1).split(","):
                param = param.strip()
                if not param:
                    continue
                name = param.split(":")[0].split("=")[0].strip()
                name = name.lstrip("*")
                if name:
                    args.append(name)
        return args, return_type

    def _find_enclosing_definition(
        self,
        ref_line: int,
        definition_occurrences: list[Any],
    ) -> Optional[str]:
        """Return the nearest enclosing definition symbol for a reference line.

        Args:
            ref_line: Reference line number.
            definition_occurrences: Definition occurrences in the current document.

        Returns:
            Enclosing caller symbol when one is available.
        """

        best = None
        best_line = -1
        for occ in definition_occurrences:
            occ_line = occ.range[0] + 1 if occ.range else 0
            if occ_line <= ref_line and occ_line > best_line:
                best = occ.symbol
                best_line = occ_line
        return best
