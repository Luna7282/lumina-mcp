import hashlib


def file_hash(content: str) -> str:
    """SHA256 hash of file content."""
    return hashlib.sha256(content.encode()).hexdigest()


def codebase_hash(files: dict[str, str]) -> str:
    """Deterministic hash of entire file set."""
    sorted_content = "".join(f"{k}:{v}" for k, v in sorted(files.items()))
    return hashlib.sha256(sorted_content.encode()).hexdigest()


def changed_files(files: dict[str, str], cached_hashes: dict[str, str]) -> dict[str, str]:
    """
    Return only files that changed since last extraction.
    cached_hashes: {filepath: sha256_hash}
    """
    return {
        filepath: content
        for filepath, content in files.items()
        if file_hash(content) != cached_hashes.get(filepath)
    }


def compute_hashes(files: dict[str, str]) -> dict[str, str]:
    """Compute {filepath: hash} for all files."""
    return {fp: file_hash(content) for fp, content in files.items()}
