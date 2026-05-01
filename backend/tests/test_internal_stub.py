from __future__ import annotations

from artstyle_backend.ml.internal_stub import InternalStubModel


def test_internal_stub_is_deterministic() -> None:
    model = InternalStubModel(["impressionism", "cubism", "baroque"])
    image = b"sample-image"

    first = model.predict(image, top_k=2)
    second = model.predict(image, top_k=2)

    assert first == second
    assert len(first) == 2
    assert first[0]["rank"] == 1
    assert first[1]["rank"] == 2

