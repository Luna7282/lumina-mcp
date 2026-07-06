import networkx as nx

from lumina_app.extract.cache import changed_files, codebase_hash, compute_hashes, file_hash
from lumina_app.extract.cluster import detect_communities
from lumina_app.extract.dispatch import extract_all
from lumina_app.extract.extractors.python import PythonExtractor
from lumina_app.extract.extractors.typescript import TypeScriptExtractor
from lumina_app.extract.graph import build_graph, get_god_nodes


class TestPythonExtractor:
    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_detects_class_with_methods(self):
        code = """
class UserService:
    def get_user(self, id):
        pass

    def delete_user(self, id):
        pass
"""
        result = self.extractor.extract("service.py", code)
        types = {n.id: n.type for n in result.nodes}
        assert types["service.py::UserService"] == "class"
        assert types["service.py::UserService::get_user"] == "method"
        assert types["service.py::UserService::delete_user"] == "method"
        contains = [
            (e.source, e.target) for e in result.edges if e.relation == "contains"
        ]
        assert ("service.py::UserService", "service.py::UserService::get_user") in contains
        assert ("service.py::UserService", "service.py::UserService::delete_user") in contains

    def test_detects_fastapi_route(self):
        code = """
@app.get("/users")
async def get_users():
    return []
"""
        result = self.extractor.extract("routes.py", code)
        route_nodes = [n for n in result.nodes if n.type == "route"]
        assert len(route_nodes) == 1
        assert route_nodes[0].label == "/users"

    def test_detects_sqlalchemy_model(self):
        code = """
class Base(DeclarativeBase):
    pass


class User(Base):
    id: int
"""
        result = self.extractor.extract("models.py", code)
        types = {n.id: n.type for n in result.nodes}
        assert types["models.py::User"] == "model"
        assert types["models.py::Base"] == "model"

    def test_detects_imports_with_nodes_and_edges(self):
        code = "from fastapi import FastAPI\nimport os\n"
        result = self.extractor.extract("main.py", code)
        import_nodes = [n for n in result.nodes if n.type == "import"]
        labels = {n.label for n in import_nodes}
        assert "FastAPI" in labels
        assert "os" in labels
        import_edges = [e for e in result.edges if e.relation == "imports"]
        assert any(e.target == "FastAPI" for e in import_edges)

    def test_class_inherits_edge_to_parent(self):
        code = """
class Animal:
    pass


class Dog(Animal):
    pass
"""
        result = self.extractor.extract("animals.py", code)
        inherits = [e for e in result.edges if e.relation == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].source == "animals.py::Dog"
        assert inherits[0].target == "animals.py::Animal"
        assert inherits[0].confidence == "EXTRACTED"

    def test_handles_syntax_errors_gracefully(self):
        code = "def broken(:\n    this is not +++ valid ///"
        result = self.extractor.extract("broken.py", code)
        assert result.nodes != [] or result.nodes == []  # never raises
        # Broken syntax still parses via tree-sitter's error recovery, or
        # yields an empty result — either way it must not crash.
        assert isinstance(result.nodes, list)
        assert isinstance(result.edges, list)

    def test_docstring_extracted_from_class_body(self):
        code = '''
class Widget:
    """A reusable widget."""
    def render(self):
        pass
'''
        result = self.extractor.extract("widget.py", code)
        widget = next(n for n in result.nodes if n.id == "widget.py::Widget")
        assert "reusable widget" in widget.docstring


class TestTypeScriptExtractor:
    def setup_method(self):
        self.extractor = TypeScriptExtractor()

    def test_detects_class_declaration(self):
        code = "export class UserRepository {\n  find(id: number) {}\n}\n"
        result = self.extractor.extract("repo.ts", code)
        classes = [n for n in result.nodes if n.type == "class"]
        assert any(n.label.startswith("UserRepository") for n in classes)

    def test_detects_interface_as_model_node(self):
        code = "interface User {\n  name: string;\n}\n"
        result = self.extractor.extract("types.ts", code)
        models = [n for n in result.nodes if n.type == "model"]
        assert any(n.label.startswith("User") for n in models)

    def test_detects_express_route(self):
        code = 'app.get("/users", (req, res) => res.send("ok"));\n'
        result = self.extractor.extract("server.ts", code)
        routes = [n for n in result.nodes if n.type == "route"]
        assert len(routes) == 1
        assert routes[0].label == "/users"

    def test_detects_import_statement(self):
        code = 'import { Foo } from "./foo";\n'
        result = self.extractor.extract("app.ts", code)
        imports = [n for n in result.nodes if n.type == "import"]
        assert any(n.label == "./foo" for n in imports)

    def test_react_component_detection(self):
        code = "export const App = () => <div>hi</div>;\n"
        result = self.extractor.extract("App.tsx", code)
        functions = [n for n in result.nodes if n.type == "function"]
        assert any("(Component)" in n.label for n in functions)


class TestGraphBuilder:
    def test_merges_two_python_files(self):
        files = {
            "a.py": "def foo():\n    pass\n",
            "b.py": "def bar():\n    pass\n",
        }
        extractions = extract_all(files)
        G = build_graph(extractions)
        assert "a.py::foo" in G.nodes
        assert "b.py::bar" in G.nodes

    def test_cross_file_call_resolution_creates_inferred_edge(self):
        files = {
            "a.py": "def helper():\n    pass\n",
            "b.py": "def caller():\n    helper()\n",
        }
        extractions = extract_all(files)
        G = build_graph(extractions)
        assert G.has_edge("b.py::caller", "a.py::helper")
        assert G["b.py::caller"]["a.py::helper"]["confidence"] == "INFERRED"

    def test_dangling_edges_are_skipped_safely(self):
        files = {"a.py": "import some_unresolvable_external_package\n"}
        extractions = extract_all(files)
        # Should not raise even though the import target never resolves.
        G = build_graph(extractions)
        assert "a.py" in G.nodes

    def test_god_nodes_returns_top_n_by_degree(self):
        G = nx.Graph()
        G.add_node("hub", label="hub", type="module", source_file="x.py")
        for i in range(5):
            leaf = f"leaf{i}"
            G.add_node(leaf, label=leaf, type="function", source_file="x.py")
            G.add_edge("hub", leaf)
        god_nodes = get_god_nodes(G, top_n=1)
        assert len(god_nodes) == 1
        assert god_nodes[0]["id"] == "hub"
        assert god_nodes[0]["degree"] == 5


class TestCommunityDetection:
    def test_two_disconnected_subgraphs_two_communities(self):
        G = nx.Graph()
        G.add_edge("a", "b")
        G.add_edge("c", "d")
        communities = detect_communities(G)
        assert len(set(communities.values())) == 2
        assert communities["a"] == communities["b"]
        assert communities["c"] == communities["d"]
        assert communities["a"] != communities["c"]

    def test_fully_connected_graph_one_community(self):
        G = nx.Graph()
        G.add_edge("x", "y")
        G.add_edge("y", "z")
        G.add_edge("x", "z")
        communities = detect_communities(G)
        assert len(set(communities.values())) == 1

    def test_empty_graph_empty_result(self):
        assert detect_communities(nx.Graph()) == {}


class TestCache:
    def test_same_content_same_hash(self):
        assert file_hash("hello world") == file_hash("hello world")

    def test_different_content_different_hash(self):
        assert file_hash("hello") != file_hash("world")

    def test_changed_files_returns_only_modified(self):
        files = {"a.py": "new content", "b.py": "unchanged"}
        cached_hashes = {"a.py": file_hash("old content"), "b.py": file_hash("unchanged")}
        changed = changed_files(files, cached_hashes)
        assert changed == {"a.py": "new content"}

    def test_codebase_hash_deterministic_regardless_of_order(self):
        files_a = {"a.py": "1", "b.py": "2"}
        files_b = {"b.py": "2", "a.py": "1"}
        assert codebase_hash(files_a) == codebase_hash(files_b)

    def test_compute_hashes_covers_all_files(self):
        files = {"a.py": "1", "b.py": "2"}
        hashes = compute_hashes(files)
        assert set(hashes.keys()) == {"a.py", "b.py"}
        assert hashes["a.py"] == file_hash("1")
