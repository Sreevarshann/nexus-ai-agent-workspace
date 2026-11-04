"""SQLAlchemy ORM models. Every user-owned table carries ``user_id`` for row-level authorization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIM = 768


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created()


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApiToken(Base):
    """Bearer tokens for programmatic access (MCP clients)."""

    __tablename__ = "api_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.created_at", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # complete | streaming | error | cancelled
    status: Mapped[str] = mapped_column(String(16), default="complete")
    mode: Mapped[str] = mapped_column(String(16), default="chat")  # chat | research | analysis | agent
    # citations: [{label, kind, chunk_id|source_id, title, page, url, excerpt}]
    citations: Mapped[list[Any]] = mapped_column(default=list)
    # attachments: [{kind: document|dataset, id, name}]
    attachments: Mapped[list[Any]] = mapped_column(default=list)
    # meta: model, latency_ms, tokens, error, task_id, tool_results, suggestions
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)


class Task(Base):
    """A durable unit of background work: an agent mission, a workflow run, or an ingestion."""

    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))  # mission | workflow | ingest
    mode: Mapped[str] = mapped_column(String(16), default="deep")
    title: Mapped[str] = mapped_column(String(240))
    prompt: Mapped[str] = mapped_column(Text, default="")
    # queued | running | paused | waiting_approval | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    options: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_tasks_user_created", "user_id", "created_at"),)


class TaskEvent(Base):
    """Append-only, ordered event log for a task. Clients replay it to rebuild state after reconnecting."""

    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(48))
    node: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (Index("ix_task_events_task_id_id", "task_id", "id"),)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    node: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="running")
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    tool: Mapped[str] = mapped_column(String(64), index=True)
    origin: Mapped[str] = mapped_column(String(16))  # agent | mcp | workflow | chat | api
    args: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))  # ok | error | denied
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(127))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(512))
    # queued | processing | ready | failed
    status: Mapped[str] = mapped_column(String(16), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="uq_documents_user_sha256"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Source(Base):
    """A web page or PDF that was actually retrieved during research."""

    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))  # retrieved | failed | blocked
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(127))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str | None] = mapped_column(String(64))
    search_query: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = _created()


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))  # chunk | source
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    supported: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _created()


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(BigInteger)
    columns: Mapped[list[Any]] = mapped_column(default=list)
    profile: Mapped[dict[str, Any]] = mapped_column(default=dict)
    parquet_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = _created()


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(24))  # report | markdown | table | chart | analysis | json | csv
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="artifact", order_by="ArtifactVersion.version", cascade="all, delete-orphan"
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")  # markdown body
    # structured payload: charts, tables, citations
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = _created()
    artifact: Mapped[Artifact] = relationship(back_populates="versions")
    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),)


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str | None] = mapped_column(String(64))
    graph: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {nodes: [...], edges: [...]}
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(default=dict)
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()
