import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class CodebaseFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
    language: str
    summary: str | None = None
    exports: list[str] = []
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    routes: list[str] = []
    models: list[str] = []
    complexity_score: float = 0.0
    summary_generated_at: datetime | None = None


class CodebaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source: str
    content_hash: str
    file_count: int
    language_summary: dict[str, int]
    graph: dict
    created_at: datetime
    last_analyzed_at: datetime


class CodebaseVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codebase_id: uuid.UUID
    focus: str
    video_url: str | None = None
    manim_code: str | None = None
    render_job_id: str | None = None
    status: str
    created_at: datetime


class AnalyzeRequest(BaseModel):
    files: dict[str, str]  # {filepath: content}
    name: str = "unnamed"  # project name
    focus: str | None = None  # optional hint

    @field_validator("files")
    @classmethod
    def validate_files(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("files cannot be empty")
        if len(v) > 500:
            raise ValueError("maximum 500 files per analysis")
        # Cap individual file size at 100KB
        for path, content in v.items():
            if len(content) > 100_000:
                raise ValueError(f"file {path} exceeds 100KB limit")
        return v


class AnalyzeResponse(BaseModel):
    codebase_id: str
    name: str
    file_count: int
    node_count: int
    edge_count: int
    god_nodes: list[dict]
    community_count: int
    language_summary: dict[str, int]
    cached: bool  # True if this content_hash was already analyzed


class ExplainRequest(BaseModel):
    codebase_id: uuid.UUID
    focus: str = "overview"


class DocsRequest(BaseModel):
    codebase_id: uuid.UUID
