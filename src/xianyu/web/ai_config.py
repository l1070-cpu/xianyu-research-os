from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import datetime


AI_CONFIG_RELATIVE = Path("09_AI中台") / "ai_model_config.json"


def infer_ai_provider(base: str) -> str:
    low = (base or "").lower()
    if "deepseek" in low:
        return "DeepSeek"
    if "api.openai.com" in low or "openai" in low:
        return "OpenAI Compatible"
    if "siliconflow" in low:
        return "SiliconFlow"
    if "openrouter" in low:
        return "OpenRouter"
    if "localhost" in low or "127.0.0.1" in low or "ollama" in low:
        return "Local / Ollama Compatible"
    return "Custom Compatible"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def ai_config_path(root: Path) -> Path:
    return root / AI_CONFIG_RELATIVE


def provider_presets() -> dict[str, dict[str, str]]:
    return {
        "deepseek": {
            "label": "DeepSeek",
            "base": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-flash",
        },
        "openai": {
            "label": "OpenAI",
            "base": "https://api.openai.com/v1",
            "model": "gpt-5",
        },
        "openrouter": {
            "label": "OpenRouter",
            "base": "https://openrouter.ai/api/v1",
            "model": "",
        },
        "ollama": {
            "label": "Ollama / Local",
            "base": "http://127.0.0.1:11434/v1",
            "model": "",
        },
        "custom": {
            "label": "Custom Compatible",
            "base": "",
            "model": "",
        },
    }


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_ai_config(root: Path) -> dict:
    env_base = os.getenv("AI_API_BASE", "").rstrip("/")
    env_key = os.getenv("AI_API_KEY", "")
    env_model = os.getenv("AI_MODEL", "")
    override = _read_json_if_exists(ai_config_path(root))

    base = (override.get("base") or env_base).rstrip("/")
    key = override.get("key") or env_key
    model = override.get("model") or env_model
    provider_preset = override.get("provider_preset", "")
    provider_label = override.get("provider_label", "")

    if provider_preset and provider_preset in provider_presets():
        preset = provider_presets()[provider_preset]
        provider_label = provider_label or preset["label"]

    source = "override" if override else "env"
    return {
        "configured": bool(base and key and model),
        "provider": provider_label or infer_ai_provider(base),
        "provider_preset": provider_preset or "",
        "provider_label": provider_label or infer_ai_provider(base),
        "base": base,
        "model": model,
        "key": key,
        "key_masked": mask_secret(key),
        "source": source,
        "config_path": str(ai_config_path(root)),
        "updated_at": override.get("updated_at", ""),
    }


def save_ai_config(
    root: Path,
    provider_preset: str,
    provider_label: str,
    base: str,
    model: str,
    key: str,
) -> Path:
    config_dir = ai_config_path(root).parent
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider_preset": provider_preset,
        "provider_label": provider_label,
        "base": base.rstrip("/"),
        "model": model,
        "key": key,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    ai_config_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ai_config_path(root)


def reset_ai_config(root: Path) -> None:
    path = ai_config_path(root)
    if path.exists():
        path.unlink()
