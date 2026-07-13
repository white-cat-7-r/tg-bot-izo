STYLES = {
    "anime": {
        "name": "Аниме",
        "description": "Стиль японской анимации",
        "prompt_template": "anime style, detailed, vibrant colors, {prompt}",
    },
    "cartoon": {
        "name": "Мультфильм",
        "description": "Яркий мультяшный стиль",
        "prompt_template": "cartoon style, colorful, fun, {prompt}",
    },
    "oil_painting": {
        "name": "Масляная живопись",
        "description": "Классическая картина маслом",
        "prompt_template": "oil painting, classical art, detailed brushstrokes, {prompt}",
    },
    "cyberpunk": {
        "name": "Киберпанк",
        "description": "Футуристический неоновый стиль",
        "prompt_template": "cyberpunk style, neon lights, futuristic, {prompt}",
    },
    "watercolor": {
        "name": "Акварель",
        "description": "Нежная акварельная живопись",
        "prompt_template": "watercolor painting, soft colors, artistic, {prompt}",
    },
    "pixel": {
        "name": "Пиксель-арт",
        "description": "Ретро 8-битный стиль",
        "prompt_template": "pixel art, 8-bit style, retro gaming, {prompt}",
    },
}


def get_style_prompt(style_key: str, user_prompt: str = "") -> str:
    style = STYLES.get(style_key)
    if not style:
        raise ValueError(f"Style '{style_key}' not found")
    prompt = style["prompt_template"].format(prompt=user_prompt or "portrait")
    return prompt


def get_styles_keyboard_text() -> str:
    lines = ["Выбери стиль обработки:\n"]
    for key, style in STYLES.items():
        lines.append(f"• {style['name']} — {style['description']}")
    return "\n".join(lines)
