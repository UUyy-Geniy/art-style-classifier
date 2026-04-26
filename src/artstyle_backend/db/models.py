from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from artstyle_backend.core.database import Base
from artstyle_backend.domain import AdminActionType, TaskStatus


class Style(Base):
    __tablename__ = "styles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InferenceTask(Base):
    __tablename__ = "inference_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.QUEUED.value, index=True)
    s3_key: Mapped[str] = mapped_column(String(512), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prediction: Mapped["Prediction | None"] = relationship(back_populates="task", uselist=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("inference_tasks.id"), unique=True, index=True)
    top_style_id: Mapped[int] = mapped_column(ForeignKey("styles.id"))
    top_confidence: Mapped[float] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String(255))
    model_version: Mapped[str] = mapped_column(String(255))
    model_source: Mapped[str] = mapped_column(String(64))
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[InferenceTask] = relationship(back_populates="prediction")
    top_style: Mapped[Style] = relationship(foreign_keys=[top_style_id])
    candidates: Mapped[list["PredictionCandidate"]] = relationship(
        back_populates="prediction",
        cascade="all, delete-orphan",
        order_by="PredictionCandidate.rank",
    )


class PredictionCandidate(Base):
    __tablename__ = "prediction_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    style_id: Mapped[int] = mapped_column(ForeignKey("styles.id"))
    rank: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)

    prediction: Mapped[Prediction] = relationship(back_populates="candidates")
    style: Mapped[Style] = relationship()


class ModelRegistryState(Base):
    __tablename__ = "model_registry_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    model_name: Mapped[str] = mapped_column(String(255))
    model_version: Mapped[str] = mapped_column(String(255))
    model_source: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RetrainExport(Base):
    __tablename__ = "retrain_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_key: Mapped[str] = mapped_column(String(512), unique=True)
    records_count: Mapped[int] = mapped_column(Integer)
    payload_preview: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminActionLog(Base):
    __tablename__ = "admin_actions_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_type: Mapped[str] = mapped_column(String(64), default=AdminActionType.RELOAD_WORKERS.value)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

