from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from mlflow.tracking import MlflowClient
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.db.models import AdminActionLog, ModelRegistryState
from artstyle_backend.domain import AdminActionType, ModelSource


@dataclass
class AvailableModel:
    model_name: str
    model_version: str
    model_source: str
    current_stage: str | None
    aliases: list[str]
    is_active: bool


class MlflowRegistryClient:
    def __init__(self, settings) -> None:
        self._client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)

    def list_model_versions(self, model_name: str) -> list[dict]:
        try:
            versions = self._client.search_model_versions(f"name='{model_name}'")
        except Exception:
            return []

        items: list[dict] = []
        for version in versions:
            items.append(
                {
                    "model_name": version.name,
                    "model_version": version.version,
                    "model_source": ModelSource.MLFLOW.value,
                    "current_stage": getattr(version, "current_stage", None),
                    "aliases": list(getattr(version, "aliases", [])),
                }
            )
        return items

    def ensure_version_exists(self, model_name: str, model_version: str) -> None:
        try:
            if model_version.isdigit():
                self._client.get_model_version(model_name, model_version)
            else:
                self._client.get_model_version_by_alias(model_name, model_version)
        except Exception as exc:
            raise ValueError(
                f"MLflow model '{model_name}' with version or alias '{model_version}' is not available."
            ) from exc


async def get_active_model_state(session: AsyncSession) -> ModelRegistryState | None:
    return await session.get(ModelRegistryState, 1)


def list_available_models(
    registry_client: MlflowRegistryClient,
    model_name: str,
    active_version: str,
    active_source: str,
) -> list[dict]:
    models = [
        asdict(
            AvailableModel(
                model_name=model_name,
                model_version="stub-v1",
                model_source=ModelSource.INTERNAL_STUB.value,
                current_stage="BuiltIn",
                aliases=[],
                is_active=active_source == ModelSource.INTERNAL_STUB.value
                and active_version == "stub-v1",
            )
        )
    ]
    for item in registry_client.list_model_versions(model_name):
        item["is_active"] = (
            item["model_source"] == active_source and item["model_version"] == active_version
        )
        models.append(item)
    return models


async def _log_action(session: AsyncSession, action_type: AdminActionType, payload: dict) -> None:
    session.add(AdminActionLog(action_type=action_type.value, payload=payload))


async def switch_active_model(
    session: AsyncSession,
    registry_client: MlflowRegistryClient,
    model_name: str,
    model_version: str,
    model_source: str,
) -> ModelRegistryState:
    if model_source == ModelSource.MLFLOW.value:
        registry_client.ensure_version_exists(model_name, model_version)
    elif model_source != ModelSource.INTERNAL_STUB.value:
        raise ValueError(f"Unsupported model source '{model_source}'.")

    state = await get_active_model_state(session)
    if state is None:
        state = ModelRegistryState(id=1, model_name=model_name, model_version=model_version, model_source=model_source, revision=1)
        session.add(state)
    else:
        state.model_name = model_name
        state.model_version = model_version
        state.model_source = model_source
        state.revision += 1
        state.updated_at = datetime.now(timezone.utc)

    await _log_action(
        session,
        AdminActionType.SWITCH_MODEL,
        {
            "model_name": model_name,
            "model_version": model_version,
            "model_source": model_source,
            "revision": state.revision,
        },
    )
    await session.commit()
    await session.refresh(state)
    return state


async def bump_model_revision(session: AsyncSession) -> ModelRegistryState | None:
    state = await get_active_model_state(session)
    if state is None:
        return None
    state.revision += 1
    state.updated_at = datetime.now(timezone.utc)
    await _log_action(
        session,
        AdminActionType.RELOAD_WORKERS,
        {
            "model_name": state.model_name,
            "model_version": state.model_version,
            "model_source": state.model_source,
            "revision": state.revision,
        },
    )
    await session.commit()
    await session.refresh(state)
    return state

