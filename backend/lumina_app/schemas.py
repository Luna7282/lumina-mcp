import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileNodeSchema(BaseModel):
    path: str
    language: str
    exports: list[str] = []
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    routes: list[str] = []
    models: list[str] = []
    complexity_score: float = 0.0


class EdgeSchema(BaseModel):
    source: str
    target: str
    kind: str


class CodebaseGraphSchema(BaseModel):
    files: dict[str, FileNodeSchema] = {}
    edges: list[EdgeSchema] = []
    layers: dict[str, list[str]] = {}
    language_summary: dict[str, int] = {}


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
    name: str
    source: str = "upload"
    files: dict[str, str]  # path -> content


class ExplainRequest(BaseModel):
    codebase_id: uuid.UUID
    focus: str = "overview"


class DocsRequest(BaseModel):
    codebase_id: uuid.UUID
