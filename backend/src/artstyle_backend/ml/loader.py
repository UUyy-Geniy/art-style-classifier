from __future__ import annotations

import asyncio
from dataclasses import dataclass

import mlflow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from artstyle_backend.db.models import ModelRegistryState, Style
from artstyle_backend.domain import ModelSource
from artstyle_backend.ml.contracts import ModelPrediction
from artstyle_backend.ml.internal_stub import InternalStubModel


def build_mlflow_model_uri(model_name: str, model_version: str) -> str:
    if model_version.isdigit():
        return f"models:/{model_name}/{model_version}"
    return f"models:/{model_name}@{model_version}"


class MlflowPyfuncAdapter:
    def __init__(self, model_name: str, model_version: str, tracking_uri: str) -> None:
        mlflow.set_tracking_uri(tracking_uri)
        self._model = mlflow.pyfunc.load_model(build_mlflow_model_uri(model_name, model_version))

    def predict(self, image_bytes: bytes, top_k: int) -> list[dict]:
        raw_output = self._model.predict({"image_bytes": image_bytes, "top_k": top_k})
        if isinstance(raw_output, dict) and "top_k" in raw_output:
            raw_output = raw_output["top_k"]
        if not isinstance(raw_output, list):
            raise ValueError("MLflow model returned unsupported prediction payload.")
        return [ModelPrediction.model_validate(item).model_dump() for item in raw_output]


@dataclass
class LoadedModel:
    model_name: str
    model_version: str
    model_source: str
    revision: int
    predictor: object

    def predict(self, image_bytes: bytes, top_k: int) -> list[dict]:
        return self.predictor.predict(image_bytes, top_k)


class ModelManager:
    def __init__(self, settings, session_factory: async_sessionmaker) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._loaded: LoadedModel | None = None
        self._lock = asyncio.Lock()

    async def ensure_current_model(self) -> LoadedModel:
        async with self._lock:
            async with self._session_factory() as session:
                state = await session.get(ModelRegistryState, 1)
                if state is None:
                    raise RuntimeError("Active model state is not initialized.")
                if self._loaded is None or self._loaded.revision != state.revision:
                    self._loaded = await self._load_from_state(session, state)
                return self._loaded

    async def _load_from_state(
        self,
        session,
        state: ModelRegistryState,
    ) -> LoadedModel:
        if state.model_source == ModelSource.INTERNAL_STUB.value:
            style_codes = (
                await session.execute(select(Style.code).order_by(Style.id.asc()))
            ).scalars().all()
            predictor = InternalStubModel(style_codes)
        elif state.model_source == ModelSource.MLFLOW.value:
            predictor = await asyncio.to_thread(
                MlflowPyfuncAdapter,
                state.model_name,
                state.model_version,
                self._settings.mlflow_tracking_uri,
            )
        else:
            raise RuntimeError(f"Unsupported model source '{state.model_source}'.")

        return LoadedModel(
            model_name=state.model_name,
            model_version=state.model_version,
            model_source=state.model_source,
            revision=state.revision,
            predictor=predictor,
        )

