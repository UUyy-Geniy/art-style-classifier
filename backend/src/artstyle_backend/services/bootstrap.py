from __future__ import annotations

import json
from importlib import resources

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.core.config import get_settings
from artstyle_backend.db.models import ModelRegistryState, Style


def load_seed_styles() -> list[dict]:
    resource = resources.files("artstyle_backend.data").joinpath("styles.seed.json")
    raw = resource.read_text(encoding="utf-8")
    return json.loads(raw)


async def ensure_seed_data(session: AsyncSession) -> None:
    seed_styles = load_seed_styles()
    existing_styles = (await session.execute(select(Style))).scalars().all()
    existing_by_code = {style.code: style for style in existing_styles}

    for item in seed_styles:
        style = existing_by_code.get(item["code"])
        if style is None:
            session.add(Style(**item))
        else:
            style.name = item["name"]
            style.description = item.get("description")

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
