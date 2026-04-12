from __future__ import annotations

import html
from pathlib import Path
from textwrap import wrap

from writing_agent.config import get_settings
from writing_agent.schemas.blocks import GeneratedImage, ImagePlanItem
from writing_agent.services.tracing import traceable


def _svg_markup(title: str, body: str) -> str:
    body_lines = wrap(body, width=18)[:4]
    body_svg = "".join(
        f'<text x="40" y="{170 + index * 42}" font-size="28" fill="#F3F4F6">{html.escape(line)}</text>'
        for index, line in enumerate(body_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#111827" />
      <stop offset="100%" stop-color="#7C3AED" />
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="48" fill="url(#bg)" />
  <circle cx="830" cy="220" r="160" fill="#F59E0B" fill-opacity="0.2" />
  <circle cx="180" cy="860" r="220" fill="#10B981" fill-opacity="0.14" />
  <text x="40" y="90" font-size="32" fill="#F9FAFB" opacity="0.8">Writing Agent Visual</text>
  <text x="40" y="145" font-size="54" font-weight="700" fill="#FFFFFF">{html.escape(title[:24])}</text>
  {body_svg}
</svg>"""


@traceable(name="generate_images")
def generate_images(items: list[ImagePlanItem]) -> list[GeneratedImage]:
    settings = get_settings()
    generated: list[GeneratedImage] = []
    output_dir: Path = settings.image_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        filename = f"{item.image_id}.svg"
        file_path = output_dir / filename
        file_path.write_text(
            _svg_markup(item.purpose, item.prompt),
            encoding="utf-8",
        )
        generated.append(
            GeneratedImage(
                image_id=item.image_id,
                purpose=item.purpose,
                prompt=item.prompt,
                alt_text=item.alt_text,
                file_path=str(file_path),
                public_url=f"/generated_images/{filename}",
            )
        )
    return generated
