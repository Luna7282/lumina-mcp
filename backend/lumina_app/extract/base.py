from typing import Protocol

from lumina_app.extract.schema import ExtractionResult


class BaseExtractor(Protocol):
    def extract(self, filepath: str, content: str) -> ExtractionResult: ...
