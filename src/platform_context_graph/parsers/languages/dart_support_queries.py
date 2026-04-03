"""Shared tree-sitter query strings for the Dart parser."""

from __future__ import annotations

DART_QUERIES = {
    "functions": """
        (function_signature
            name: (identifier) @name
            (formal_parameter_list) @params
        ) @function_node
        (constructor_signature
            name: (identifier) @name
            (formal_parameter_list) @params
        ) @function_node
    """,
    "classes": """
        [
            (class_definition name: (identifier) @name)
            (mixin_declaration (identifier) @name)
            (extension_declaration name: (identifier) @name)
            (enum_declaration name: (identifier) @name)
        ] @class
    """,
    "imports": """
        (library_import) @import
        (library_export) @import
    """,
    "calls": """
        (expression_statement
            (identifier) @name
        ) @call
        (selector
            (argument_part (arguments))
        ) @call
    """,
    "variables": """
        (local_variable_declaration
            (initialized_variable_definition
                name: (identifier) @name
            )
        ) @variable
        (declaration
            (initialized_identifier_list
                (initialized_identifier
                    (identifier) @name
                )
            )
        ) @variable
        (initialized_variable_definition
            name: (identifier) @name
        ) @variable
        (static_final_declaration_list
            (static_final_declaration) @variable
        )
        (initialized_identifier_list
            (initialized_identifier
                (identifier) @name
            )
        ) @variable
    """,
}

PRESCAN_QUERY = """
    [
        (class_definition name: (identifier) @name)
        (mixin_declaration name: (identifier) @name)
        (extension_declaration name: (identifier) @name)
        (function_signature name: (identifier) @name)
    ]
"""
