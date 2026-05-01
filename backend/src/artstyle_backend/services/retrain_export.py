from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.db.models import Prediction, PredictionCandidate, RetrainExport
from artstyle_backend.services.storage import StorageService


async def create_retrain_export(
    session: AsyncSession,
    storage: StorageService,
) -> RetrainExport:
    query = (
        select(Prediction)
        .options(
            selectinload(Prediction.task),
            selectinload(Prediction.top_style),
            selectinload(Prediction.candidates).selectinload(PredictionCandidate.style),
        )
        .order_by(Prediction.created_at.desc())
    )
    predictions = (await session.execute(query)).scalars().all()

    rows: list[dict] = []
    for prediction in predictions:
        rows.append(
            {
                "task_id": prediction.task_id,
                "s3_key": prediction.task.s3_key,
                "model_name": prediction.model_name,
                "model_version": prediction.model_version,
                "model_source": prediction.model_source,
                "top_style_code": prediction.top_style.code,
                "top_confidence": prediction.top_confidence,
                "candidates": [
                    {
                        "style_code": candidate.style.code,
                        "confidence": candidate.confidence,
                        "rank": candidate.rank,
                    }
                    for candidate in prediction.candidates
                ],
                "future_feedback": None,
                "created_at": prediction.created_at.isoformat(),
            }
        )

    export_key = f"exports/retrain-export-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")
    await storage.upload_bytes(export_key, payload, "application/x-ndjson")

    export = RetrainExport(
        export_key=export_key,
        records_count=len(rows),
        payload_preview={"rows": rows[:3]},
    )
    session.add(export)
    await session.commit()
    await session.refresh(export)
    return export
