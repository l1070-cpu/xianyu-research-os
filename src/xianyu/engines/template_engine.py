from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]

class TemplateEngine:
    def __init__(self, folder: str, prefix: str, title: str, template: str):
        self.dir = ROOT / folder
        self.prefix = prefix
        self.title = title
        self.template = template
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str) -> str:
        today = date.today().isoformat()
        safe = name.replace(" ", "_").replace("/", "_")
        file_path = self.dir / f"{today}_{safe}.md"

        if file_path.exists():
            return f"{self.title}已存在：{file_path}"

        content = self.template.format(today=today, name=name)
        file_path.write_text(content, encoding="utf-8")
        return f"已生成{self.title}：{file_path}"
