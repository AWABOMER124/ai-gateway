import pytest

from app.api.v1.wasla_router import _require_permission
from app.core.context import Actor, ActorType, ExecutionContext, Product
from app.core.errors import ToolPermissionDenied


def _ctx(permissions: list[str]) -> ExecutionContext:
    return ExecutionContext(
        tenant_id="merchant_1",
        product=Product.WASLA,
        actor=Actor(
            type=ActorType.USER,
            id="user_1",
            permissions=tuple(permissions),
        ),
        request_id="req_1",
    )


def test_allows_exact_permission():
    _require_permission(
        _ctx(["store.generate"]),
        "store.generate",
    )


def test_allows_wildcard_permission():
    _require_permission(_ctx(["*"]), "store.generate")


def test_denies_missing_permission():
    with pytest.raises(ToolPermissionDenied) as exc:
        _require_permission(
            _ctx(["store.view"]),
            "store.generate",
        )

    assert exc.value.http_status == 403
    assert exc.value.request_id == "req_1"
    assert exc.value.details["tool"] == "store.generate"
