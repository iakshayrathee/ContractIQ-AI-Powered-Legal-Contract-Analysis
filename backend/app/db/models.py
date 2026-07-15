import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    collection_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    # Optional user scoping (nullable for backward compat with existing projects)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    analyses: Mapped[list["AnalysisRow"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessageRow"]] = relationship(
        back_populates="project", 
        cascade="all, delete-orphan", 
        order_by=lambda: ChatMessageRow.created_at.asc(),
    )


class QueryCacheRow(Base):
    __tablename__ = "query_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    chunks_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AnalysisRow(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    overall_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Judge / quality fields
    judge_json: Mapped[str] = mapped_column(Text, default="{}")
    guardrail_warnings_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)  # Judge overall score 0.0-1.0
    flagged_for_review: Mapped[bool] = mapped_column(default=False)  # True if judge flagged for human review

    # Optional user scoping (nullable for backward compat with existing analyses)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    project: Mapped["ProjectRow"] = relationship(back_populates="analyses")


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["ProjectRow"] = relationship(back_populates="chat_messages")


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    base_model: Mapped[str] = mapped_column(String(100), nullable=False)
    job_id: Mapped[str] = mapped_column(String(100), nullable=True)
    training_file_id: Mapped[str] = mapped_column(String(100), nullable=True)
    val_file_id: Mapped[str] = mapped_column(String(100), nullable=True)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    n_examples: Mapped[int] = mapped_column(Integer, nullable=True)
    n_epochs: Mapped[int] = mapped_column(Integer, nullable=True)
    train_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clause_f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    clause_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    clause_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|validating_files|ready|failed|active
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
