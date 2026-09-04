import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.context import Actor, ActorType, ExecutionContext, Product
from app.core.errors import ToolExecutionFailed
from app.integrations.wasla.adapter import WaslaAdapter
from app.services import wasla_project_store as store


def context(tenant_id: str = "merchant_1") -> ExecutionContext:
    return ExecutionContext(
        tenant_id=tenant_id,
        product=Product.WASLA,
        actor=Actor(type=ActorType.SERVICE, id="wasla-user"),
    )


def test_patch_creates_a_new_version_without_mutating_the_source(monkeypatch):
    monkeypatch.setattr(store, "get_project", AsyncMock(return_value={"id": "project_1", "current_version": 1}))
    monkeypatch.setattr(store, "get_latest_version", AsyncMock(return_value={
        "id": "version_1", "version_number": 1, "payload": {"name": "Old", "primaryColor": "#000000", "categories": []},
        "prompt": "store prompt", "generation_model": "test-model",
    }))
    create_version = AsyncMock(return_value="version_2")
    add_patch = AsyncMock(return_value="patch_1")
    monkeypatch.setattr(store, "create_version", create_version)
    monkeypatch.setattr(store, "add_patch", add_patch)

    result = asyncio.run(WaslaAdapter().apply_patch(context(), "project_1", "edit_style", {"primaryColor": "#123456"}))

    assert result["version_id"] == "version_2"
    assert result["version_number"] == 2
    assert result["payload"]["primaryColor"] == "#123456"
    assert create_version.await_args.kwargs["version_number"] == 2
    assert add_patch.await_args.kwargs["version_id"] == "version_2"


def test_restore_copies_only_a_version_owned_by_the_same_project(monkeypatch):
    monkeypatch.setattr(store, "get_project", AsyncMock(return_value={"id": "project_1", "current_version": 3}))
    monkeypatch.setattr(store, "get_version", AsyncMock(return_value={
        "id": "version_1", "project_id": "project_1", "payload": {"name": "Original"},
        "prompt": "initial", "generation_model": "test-model", "validation_errors": [],
    }))
    create_version = AsyncMock(return_value="version_4")
    monkeypatch.setattr(store, "create_version", create_version)
    monkeypatch.setattr(store, "add_patch", AsyncMock(return_value="patch_restore"))

    result = asyncio.run(WaslaAdapter().restore_version(context(), "project_1", "version_1"))

    assert result["version_id"] == "version_4"
    assert result["version_number"] == 4
    assert result["restored_from_version_id"] == "version_1"
    assert create_version.await_args.kwargs["payload"] == {"name": "Original"}


def test_restore_rejects_a_version_from_another_project(monkeypatch):
    monkeypatch.setattr(store, "get_project", AsyncMock(return_value={"id": "project_1", "current_version": 3}))
    monkeypatch.setattr(store, "get_version", AsyncMock(return_value={"id": "version_x", "project_id": "project_2", "payload": {}}))

    with pytest.raises(ToolExecutionFailed):
        asyncio.run(WaslaAdapter().restore_version(context(), "project_1", "version_x"))
