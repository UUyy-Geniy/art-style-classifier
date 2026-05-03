from __future__ import annotations

from types import SimpleNamespace

import pytest

from artstyle_backend.db.models import ModelRegistryState, Style
from artstyle_backend.services.bootstrap import ensure_seed_data


class _FakeScalarResult:
    def __init__(self, rows: list[Style]) -> None:
        self._rows = rows

    def all(self) -> list[Style]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[Style]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, styles: list[Style]) -> None:
        self.styles = styles
        self.added: list[object] = []
        self.committed = False

    async def execute(self, _statement) -> _FakeResult:
        return _FakeResult(self.styles)

    async def get(self, model, key):
        if model is ModelRegistryState and key == 1:
            return SimpleNamespace(id=1)
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_ensure_seed_data_adds_missing_model_style_codes() -> None:
    existing = [
        Style(code="pop_art", name="Old Pop Art", description="old lowercase code"),
        Style(code="Pop_Art", name="Outdated", description="outdated description"),
    ]
    session = _FakeSession(existing)

    await ensure_seed_data(session)  # type: ignore[arg-type]

    added_codes = {item.code for item in session.added if isinstance(item, Style)}
    assert "Abstract_Expressionism" in added_codes
    assert "Ukiyo_e" in added_codes
    assert "pop_art" not in added_codes
    assert existing[1].name == "Pop Art"
    assert session.committed is True
