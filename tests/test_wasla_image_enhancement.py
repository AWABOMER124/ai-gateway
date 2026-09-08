from app.api.v1.wasla_router import _product_image_prompt


def test_product_image_prompt_preserves_identity_for_every_mode():
    for mode in ("TRANSPARENT", "CLEAN_WHITE", "LIFESTYLE"):
        prompt = _product_image_prompt(mode, "a clean kitchen")
        assert "Preserve the exact product identity" in prompt
        assert "watermark" in prompt


def test_lifestyle_prompt_uses_the_merchant_scene():
    assert "a clean kitchen" in _product_image_prompt("LIFESTYLE", "a clean kitchen")
