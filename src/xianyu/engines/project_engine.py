from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]

class ProjectEngine:
    def __init__(self, project_name: str = "cibotium_is"):
        self.project_path = ROOT / "projects" / project_name
        self.project_file = self.project_path / "project.json"

    def load_project(self) -> dict:
        if not self.project_file.exists():
            raise FileNotFoundError(f"Project file not found: {self.project_file}")
        return json.loads(self.project_file.read_text(encoding="utf-8"))

    def today(self) -> str:
        project = self.load_project()

        lines = []
        lines.append("🐟 咸鱼日常打工 OS")
        lines.append("")
        lines.append(f"项目：{project['name']}")
        lines.append(f"当前阶段：{project['stage']}")
        lines.append("")
        lines.append("今日优先任务：")

        for i, task in enumerate(project.get("today_tasks", []), start=1):
            lines.append(f"{i}. {task}")

        lines.append("")
        lines.append("证据链状态：")
        for item in project.get("evidence", []):
            lines.append(f"- {item['name']}：{item['status']}")

        return "\n".join(lines)
