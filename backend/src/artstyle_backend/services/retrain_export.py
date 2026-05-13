from __future__ import annotations

import json
import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.core.config import Settings
from artstyle_backend.db.models import (
    Prediction,
    PredictionCandidate,
    PredictionFeedback,
    RetrainExport,
)
from artstyle_backend.domain import FeedbackStatus
from artstyle_backend.services.storage import StorageService


async def create_retrain_export(
    session: AsyncSession,
    storage: StorageService,
    settings: Settings,
) -> RetrainExport:
    query = (
        select(PredictionFeedback)
        .options(
            selectinload(PredictionFeedback.task),
            selectinload(PredictionFeedback.correct_style),
            selectinload(PredictionFeedback.prediction).selectinload(Prediction.top_style),
            selectinload(PredictionFeedback.prediction)
            .selectinload(Prediction.candidates)
            .selectinload(PredictionCandidate.style),
        )
        .where(PredictionFeedback.status == FeedbackStatus.APPROVED.value)
        .where(PredictionFeedback.used_in_training.is_(False))
        .order_by(PredictionFeedback.created_at.asc())
    )
    feedback_items = (await session.execute(query)).scalars().all()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_dir = Path(settings.retrain_feedback_export_dir) / timestamp
    images_dir = export_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    csv_rows: list[dict] = []
    for feedback in feedback_items:
        prediction = feedback.prediction
        image_filename = f"{feedback.id}_{Path(feedback.task.original_filename).name.replace(' ', '_')}"
        image_path = images_dir / image_filename
        image_bytes = await storage.download_bytes(feedback.task.s3_key)
        image_path.write_bytes(image_bytes)

        csv_row = {
            "feedback_id": feedback.id,
            "image_path": str(image_path),
            "correct_style_code": feedback.correct_style.code,
            "predicted_style_code": prediction.top_style.code,
            "model_version": prediction.model_version,
            "created_at": feedback.created_at.isoformat(),
        }
        csv_rows.append(csv_row)
        rows.append(
            {
                **csv_row,
                "task_id": prediction.task_id,
                "s3_key": feedback.task.s3_key,
                "model_name": prediction.model_name,
                "model_source": prediction.model_source,
                "top_confidence": prediction.top_confidence,
                "candidates": [
                    {
                        "style_code": candidate.style.code,
                        "confidence": candidate.confidence,
                        "rank": candidate.rank,
                    }
                    for candidate in prediction.candidates
                ],
            }
        )

    csv_path = export_dir / "approved_feedback.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "feedback_id",
                "image_path",
                "correct_style_code",
                "predicted_style_code",
                "model_version",
                "created_at",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    export_key = f"exports/retrain-feedback-{timestamp}.jsonl"
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")
    await storage.upload_bytes(export_key, payload, "application/x-ndjson")

    export = RetrainExport(
        export_key=export_key,
        records_count=len(feedback_items),
        payload_preview={
            "csv_path": str(csv_path),
            "images_dir": str(images_dir),
            "rows": rows[:3],
        },
    )
    session.add(export)
    await session.commit()
    await session.refresh(export)
    return export
