from __future__ import annotations

from artstyle_backend.ml.loader import build_mlflow_model_uri


def test_build_mlflow_model_uri_for_version() -> None:
    assert build_mlflow_model_uri("art-style-classifier", "12") == "models:/art-style-classifier/12"


def test_build_mlflow_model_uri_for_alias() -> None:
    assert (
        build_mlflow_model_uri("art-style-classifier", "champion")
        == "models:/art-style-classifier@champion"
    )

