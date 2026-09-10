from writing_agent.config import get_settings
from writing_agent.models import ImagePlanItem
from writing_agent.services.image_generation import generate_images


def _item() -> ImagePlanItem:
    return ImagePlanItem(
        image_id="cover-main",
        purpose="封面图",
        placement_hint="文章开头",
        prompt="生成一张关于写作工作流的编辑插图",
        style="editorial illustration",
        alt_text="写作工作流示意图",
    )


def test_generate_images_uses_configured_model(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("IMAGE_MODEL_NAME", "gpt-image-2")
    monkeypatch.setenv("IMAGE_API_KEY", "local-test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "writing_agent.services.image_generation._request_image",
        lambda _prompt: b"\x89PNG\r\n\x1a\nmock-image",
    )

    images, warnings = generate_images([_item()], "run-001")

    assert warnings == []
    assert images[0].public_url.endswith("/cover-main.png")
    assert (tmp_path / "run-001" / "cover-main.png").read_bytes().startswith(b"\x89PNG")


def test_generate_images_falls_back_to_svg_on_provider_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("IMAGE_MODEL_NAME", "gpt-image-2")
    monkeypatch.setenv("IMAGE_API_KEY", "local-test-key")
    get_settings.cache_clear()

    def fail(_prompt: str) -> bytes:
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("writing_agent.services.image_generation._request_image", fail)

    images, warnings = generate_images([_item()], "run-002")

    assert images[0].public_url.endswith("/cover-main.svg")
    assert (tmp_path / "run-002" / "cover-main.svg").exists()
    assert warnings and "已回退 SVG" in warnings[0]
