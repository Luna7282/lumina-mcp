import ast

from lumina_app.parser.base import FileNode

_MODEL_BASE_NAMES = {"Base", "DeclarativeBase", "BaseModel"}
_ROUTE_DECORATOR_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _decorator_name(decorator: ast.expr) -> str | None:
    """Return e.g. 'app.get' for @app.get(...) or 'app.get' for @app.get."""
    node = decorator
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        base = node.value
        if isinstance(base, ast.Name):
            return f"{base.id}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_route_decorator(decorator: ast.expr) -> bool:
    name = _decorator_name(decorator)
    if not name or "." not in name:
        return False
    method = name.rsplit(".", 1)[-1]
    return method in _ROUTE_DECORATOR_METHODS


def _base_class_names(class_def: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for base in class_def.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _function_length(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end = getattr(node, "end_lineno", None) or node.lineno
    return max(end - node.lineno + 1, 1)


class PythonParser:
    def parse(self, path: str, content: str) -> FileNode:
        node = FileNode(path=path, language="python")

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return node

        exported_all: list[str] | None = None
        function_lengths: list[int] = []

        for item in ast.walk(tree):
            if isinstance(item, ast.ClassDef):
                node.classes.append(item.name)
                bases = _base_class_names(item)
                if _MODEL_BASE_NAMES.intersection(bases):
                    node.models.append(item.name)
                for decorator in item.decorator_list:
                    if _is_route_decorator(decorator):
                        node.routes.append(f"{item.name}.{_decorator_name(decorator)}")

            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.functions.append(item.name)
                function_lengths.append(_function_length(item))
                for decorator in item.decorator_list:
                    if _is_route_decorator(decorator):
                        node.routes.append(f"{item.name}:{_decorator_name(decorator)}")

            elif isinstance(item, ast.Import):
                for alias in item.names:
                    node.imports.append(alias.name)

            elif isinstance(item, ast.ImportFrom):
                module = item.module or ""
                for alias in item.names:
                    node.imports.append(f"{module}.{alias.name}" if module else alias.name)

            elif isinstance(item, ast.Assign):
                targets = item.targets
                if (
                    len(targets) == 1
                    and isinstance(targets[0], ast.Name)
                    and targets[0].id == "__all__"
                    and isinstance(item.value, (ast.List, ast.Tuple))
                ):
                    exported_all = [
                        elt.value
                        for elt in item.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]

        if exported_all is not None:
            node.exports = exported_all
        else:
            node.exports = [
                name
                for name in [*node.classes, *node.functions]
                if not name.startswith("_")
            ]

        num_functions = len(function_lengths)
        avg_length = sum(function_lengths) / num_functions if num_functions else 0.0
        node.complexity_score = num_functions * avg_length

        return node
