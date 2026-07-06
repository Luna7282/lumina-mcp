from lumina_app.parser.graph import _detect_layers, build_graph
from lumina_app.parser.python import PythonParser


class TestPythonParser:
    def setup_method(self):
        self.parser = PythonParser()

    def test_detects_class_names(self):
        code = """
class Foo:
    pass


class Bar:
    pass
"""
        node = self.parser.parse("foo.py", code)
        assert node.classes == ["Foo", "Bar"]

    def test_detects_function_names(self):
        code = """
def alpha():
    pass


async def beta():
    pass
"""
        node = self.parser.parse("foo.py", code)
        assert "alpha" in node.functions
        assert "beta" in node.functions

    def test_detects_fastapi_routes(self):
        code = """
from fastapi import APIRouter

router = APIRouter()


@router.post("/items")
async def create_item():
    pass


@app.get("/health")
async def health():
    pass
"""
        node = self.parser.parse("routes.py", code)
        assert any("router.post" in r for r in node.routes)
        assert any("app.get" in r for r in node.routes)

    def test_detects_sqlalchemy_models(self):
        code = """
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
"""
        node = self.parser.parse("models.py", code)
        assert "User" in node.models
        # Base itself inherits from DeclarativeBase, so it also qualifies
        assert "Base" in node.models

    def test_detects_pydantic_models(self):
        code = """
from pydantic import BaseModel


class UserSchema(BaseModel):
    name: str
"""
        node = self.parser.parse("schemas.py", code)
        assert "UserSchema" in node.models

    def test_detects_import_statements(self):
        code = """
import os
import json as j
from pathlib import Path
from collections import OrderedDict, defaultdict
"""
        node = self.parser.parse("imports.py", code)
        assert "os" in node.imports
        assert "json" in node.imports
        assert "pathlib.Path" in node.imports
        assert "collections.OrderedDict" in node.imports
        assert "collections.defaultdict" in node.imports

    def test_handles_syntax_errors_gracefully(self):
        code = "def broken(:\n    this is not valid python +++ ///"
        node = self.parser.parse("broken.py", code)
        assert node.path == "broken.py"
        assert node.language == "python"
        assert node.classes == []
        assert node.functions == []
        assert node.imports == []
        assert node.complexity_score == 0.0

    def test_exports_all_when_defined(self):
        code = """
__all__ = ["public_fn"]


def public_fn():
    pass


def _private_fn():
    pass
"""
        node = self.parser.parse("mod.py", code)
        assert node.exports == ["public_fn"]

    def test_exports_public_names_when_no_all(self):
        code = """
def public_fn():
    pass


def _private_fn():
    pass
"""
        node = self.parser.parse("mod.py", code)
        assert "public_fn" in node.exports
        assert "_private_fn" not in node.exports


class TestBuildGraph:
    def test_language_summary_for_three_python_files(self):
        files = {
            "a.py": "def a():\n    pass\n",
            "b.py": "def b():\n    pass\n",
            "c.py": "def c():\n    pass\n",
        }
        graph = build_graph(files)
        assert graph.language_summary == {"py": 3}
        assert set(graph.files.keys()) == {"a.py", "b.py", "c.py"}

    def test_unknown_extensions_are_skipped(self):
        files = {
            "a.py": "def a():\n    pass\n",
            "notes.txt": "just some notes",
            "image.png": "binary-ish content",
        }
        graph = build_graph(files)
        assert set(graph.files.keys()) == {"a.py"}
        assert graph.language_summary == {"py": 1}

    def test_detect_layers_categorizes_by_path_pattern(self):
        files = {
            "app/routes/users.py": "def get_users():\n    pass\n",
            "app/models/user.py": "class User:\n    pass\n",
            "app/services/email_service.py": "def send():\n    pass\n",
            "app/tests/test_users.py": "def test_x():\n    pass\n",
            "app/config/settings.py": "DEBUG = True\n",
            "frontend/src/components/Button.tsx": "export const Button = () => null;\n",
            "app/misc/helpers.py": "def helper():\n    pass\n",
        }
        graph = build_graph(files)
        assert "app/routes/users.py" in graph.layers["api"]
        assert "app/models/user.py" in graph.layers["models"]
        assert "app/services/email_service.py" in graph.layers["services"]
        assert "app/tests/test_users.py" in graph.layers["tests"]
        assert "app/config/settings.py" in graph.layers["config"]
        assert "frontend/src/components/Button.tsx" in graph.layers["frontend"]
        assert "app/misc/helpers.py" in graph.layers["utils"]

    def test_detect_layers_helper_directly(self):
        from lumina_app.parser.base import CodebaseGraph, FileNode

        graph = CodebaseGraph()
        graph.files = {
            "controllers/handler.py": FileNode(path="controllers/handler.py", language="python"),
            "unclassified/thing.py": FileNode(path="unclassified/thing.py", language="python"),
        }
        _detect_layers(graph)
        assert "controllers/handler.py" in graph.layers["api"]
        assert "unclassified/thing.py" in graph.layers["utils"]
