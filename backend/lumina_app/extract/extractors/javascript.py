import tree_sitter_javascript as tsjavascript

from lumina_app.extract.extractors.typescript import JSFamilyExtractor


class JavaScriptExtractor(JSFamilyExtractor):
    """Handles .js/.jsx — the tree-sitter-javascript grammar supports JSX
    natively, so a single grammar covers both extensions."""

    language_name = "javascript"

    def get_language_capsule(self):
        return tsjavascript.language()
