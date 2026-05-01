from __future__ import annotations

import asyncio

from artstyle_backend.core.database import SessionLocal, engine
from artstyle_backend.services.bootstrap import ensure_seed_data


async def _run() -> None:
    async with SessionLocal() as session:
        await ensure_seed_data(session)
    await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

