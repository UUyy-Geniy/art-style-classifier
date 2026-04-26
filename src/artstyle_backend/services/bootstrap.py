from __future__ import annotations

import json
from importlib import resources

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.core.config import get_settings
from artstyle_backend.db.models import ModelRegistryState, Style


async def ensure_seed_data(session: AsyncSession) -> None:
    styles_count = await session.scalar(select(Style.id).limit(1))
    if styles_count is None:
        resource = resources.files("artstyle_backend.data").joinpath("styles.seed.json")
        raw = resource.read_text(encoding="utf-8")
        styles = json.loads(raw)
        session.add_all([Style(**item) for item in styles])

    state = await session.get(ModelRegistryState, 1)
    if state is None:
        settings = get_settings()
        session.add(
            ModelRegistryState(
                id=1,
                model_name=settings.default_model_name,
                model_version=settings.default_model_version,
                model_source=settings.default_model_source,
                revision=1,
            )
        )
    await session.commit()

