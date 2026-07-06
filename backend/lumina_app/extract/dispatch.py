from lumina_app.extract.detect import detect_files
from lumina_app.extract.extractors import (
    CCppExtractor,
    CSharpExtractor,
    GenericExtractor,
    GoExtractor,
    JavaExtractor,
    JavaScriptExtractor,
    KotlinExtractor,
    PhpExtractor,
    PythonExtractor,
    RubyExtractor,
    RustExtractor,
    ScalaExtractor,
    TypeScriptExtractor,
)
from lumina_app.extract.schema import ExtractionResult

LANGUAGE_TO_EXTRACTOR = {
    "python": PythonExtractor(),
    "typescript": TypeScriptExtractor(),
    "javascript": JavaScriptExtractor(),
    "go": GoExtractor(),
    "rust": RustExtractor(),
    "java": JavaExtractor(),
    "c": CCppExtractor(lang="c"),
    "cpp": CCppExtractor(lang="cpp"),
    "ruby": RubyExtractor(),
    "csharp": CSharpExtractor(),
    "kotlin": KotlinExtractor(),
    "scala": ScalaExtractor(),
    "php": PhpExtractor(),
    # others fall through to generic
}


def extract_file(filepath: str, content: str, language: str) -> ExtractionResult:
    extractor = LANGUAGE_TO_EXTRACTOR.get(language, GenericExtractor())
    try:
        return extractor.extract(filepath, content)
    except Exception:
        # Never crash on a single file
        return ExtractionResult(language=language)


def extract_all(files: dict[str, str]) -> dict[str, ExtractionResult]:
    """Extract all files, return {filepath: ExtractionResult}"""
    detected = detect_files(files)
    results = {}
    for filepath, (language, content) in detected.items():
        results[filepath] = extract_file(filepath, content, language)
    return results
