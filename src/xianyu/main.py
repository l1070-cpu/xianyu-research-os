from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_prompt(name: str) -> str:
    prompt_path = ROOT / "prompts" / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")

def main():
    print("🐟 咸鱼日常打工 OS v0.3-alpha")
    print("已加载 Research Director Prompt：")
    print("-" * 40)
    print(load_prompt("research_director")[:300])

if __name__ == "__main__":
    main()
