from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency until API key is set
    genai = None


@dataclass
class GeminiResult:
    prompt: str
    idea: str
    image_data_url: Optional[str] = None


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if api_key and genai:
            genai.configure(api_key=api_key)

    async def propose_new_thumbnail(
        self,
        title: str,
        description: str,
        original_thumbnail: Optional[str] = None,
    ) -> GeminiResult:
        base_prompt = (
            "Ты — продюсер YouTube. Проанализируй заголовок и описание ролика,"
            " предложи три сильных визуальных концепции превью и короткое CTA."  # CTA - call to action
        )
        content_prompt = (
            f"Заголовок: {title}\nОписание: {description[:500]}\n"
            f"Текущее превью: {original_thumbnail or 'нет ссылки'}"
        )
        idea_text = "Используйте GEMINI_API_KEY, чтобы получить идеи на основе контента." if not self.api_key else ""
        data_url = self._placeholder_image(title)

        if self.api_key and genai:
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
            response = model.generate_content([base_prompt, content_prompt])
            idea_text = response.text.strip()

            # Если доступна генерация изображений, пробуем запросить эскиз.
            try:
                image_model = genai.GenerativeModel("imagen-3.0-generate-001")
                image_response = image_model.generate_images(
                    prompt=f"YouTube thumbnail, {title}, cinematic, high contrast, eye-catching"
                )
                if image_response and image_response.generated_images:
                    data_url = self._image_to_data_url(image_response.generated_images[0])
            except Exception:
                pass

        return GeminiResult(prompt=content_prompt, idea=idea_text, image_data_url=data_url)

    def _placeholder_image(self, text: str) -> str:
        import textwrap
        from PIL import Image, ImageDraw, ImageFont
        import io

        width, height = 1280, 720
        image = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(image)

        wrapped = textwrap.fill(text, width=30) or "Новая идея превью"
        draw.text((60, 320), wrapped, fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    def _image_to_data_url(self, image_bytes: bytes) -> str:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
