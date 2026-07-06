import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Codebase(Base):
    __tablename__ = "codebases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))  # claude_code|github|upload
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_count: Mapped[int] = mapped_column(Integer)
    language_summary: Mapped[dict] = mapped_column(JSON)  # {"python": 45, "ts": 23}
    graph: Mapped[dict] = mapped_column(JSON)  # full CodebaseGraph
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    files: Mapped[list["CodebaseFile"]] = relationship(
        back_populates="codebase", cascade="all, delete-orphan"
    )
    videos: Mapped[list["CodebaseVideo"]] = relationship(
        back_populates="codebase", cascade="all, delete-orphan"
    )


class CodebaseFile(Base):
    __tablename__ = "codebase_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    codebase_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("codebases.id"), index=True
    )
    path: Mapped[str] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str | None] = mapped_column(Text)
    exports: Mapped[list] = mapped_column(JSON, default=list)
    imports: Mapped[list] = mapped_column(JSON, default=list)
    classes: Mapped[list] = mapped_column(JSON, default=list)
    functions: Mapped[list] = mapped_column(JSON, default=list)
    routes: Mapped[list] = mapped_column(JSON, default=list)
    models: Mapped[list] = mapped_column(JSON, default=list)
    complexity_score: Mapped[float] = mapped_column(default=0.0)
    summary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    codebase: Mapped["Codebase"] = relationship(back_populates="files")


class CodebaseVideo(Base):
    __tablename__ = "codebase_videos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    codebase_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("codebases.id"), index=True
    )
    focus: Mapped[str] = mapped_column(String(500))  # "overview"|"auth flow" etc
    video_url: Mapped[str | None] = mapped_column(String(2000))
    manim_code: Mapped[str | None] = mapped_column(Text)
    render_job_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    codebase: Mapped["Codebase"] = relationship(back_populates="videos")
