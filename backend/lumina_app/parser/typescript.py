from pathlib import Path

import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

from lumina_app.parser.base import FileNode

_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "use"}
_LANGUAGE_CACHE: dict[str, Language] = {}


def _get_language(ext: str) -> Language:
    if ext not in _LANGUAGE_CACHE:
        if ext == ".tsx":
            _LANGUAGE_CACHE[ext] = Language(tstypescript.language_tsx())
        elif ext == ".ts":
            _LANGUAGE_CACHE[ext] = Language(tstypescript.language_typescript())
        else:  # .js, .jsx
            _LANGUAGE_CACHE[ext] = Language(tsjavascript.language())
    return _LANGUAGE_CACHE[ext]


class TypeScriptParser:
    def parse(self, path: str, content: str) -> FileNode:
        ext = Path(path).suffix.lower()
        language_name = "typescript" if ext in (".ts", ".tsx") else "javascript"
        node = FileNode(path=path, language=language_name)

        source = content.encode("utf-8")

        try:
            ts_language = _get_language(ext)
            parser = Parser(ts_language)
            tree = parser.parse(source)
        except Exception:
            return node

        function_count = 0

        def text(n: Node) -> str:
            return source[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

        def visit(n: Node) -> None:
            nonlocal function_count
            kind = n.type

            if kind == "class_declaration":
                name_node = n.child_by_field_name("name")
                if name_node:
                    node.classes.append(text(name_node))

            elif kind in ("function_declaration", "method_definition"):
                name_node = n.child_by_field_name("name")
                if name_node:
                    node.functions.append(text(name_node))
                function_count += 1

            elif kind == "arrow_function":
                function_count += 1

            elif kind == "variable_declarator":
                value = n.child_by_field_name("value")
                if value is not None and value.type == "arrow_function":
                    name_node = n.child_by_field_name("name")
                    if name_node:
                        node.functions.append(text(name_node))

            elif kind == "import_statement":
                for c in n.children:
                    if c.type == "string":
                        node.imports.append(text(c).strip("'\""))

            elif kind == "call_expression":
                func = n.child_by_field_name("function")
                if func is not None and func.type == "identifier" and text(func) == "require":
                    args = n.child_by_field_name("arguments")
                    if args is not None:
                        for c in args.children:
                            if c.type == "string":
                                node.imports.append(text(c).strip("'\""))
                elif func is not None and func.type == "member_expression":
                    obj = func.child_by_field_name("object")
                    prop = func.child_by_field_name("property")
                    if obj is not None and prop is not None:
                        method = text(prop)
                        if method in _ROUTE_METHODS:
                            node.routes.append(f"{text(obj)}.{method}")

            elif kind in ("interface_declaration", "type_alias_declaration"):
                name_node = n.child_by_field_name("name")
                if name_node:
                    node.models.append(text(name_node))

            elif kind == "export_statement":
                for decl in n.named_children:
                    name_node = decl.child_by_field_name("name")
                    if name_node:
                        node.exports.append(text(name_node))
                    elif decl.type in ("lexical_declaration", "variable_declaration"):
                        for declarator in decl.named_children:
                            if declarator.type == "variable_declarator":
                                dn = declarator.child_by_field_name("name")
                                if dn:
                                    node.exports.append(text(dn))

            for child in n.children:
                visit(child)

        visit(tree.root_node)

        node.complexity_score = float(function_count)
        return node
