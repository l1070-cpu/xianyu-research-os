from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]

class ProjectEngine:
    def __init__(self, project_name: str = "cibotium_is"):
        self.project_path = ROOT / "projects" / project_name
        self.project_file = self.project_path / "project.json"
        self.today_file = ROOT / "01_今日打工" / "今日任务.md"
        self.overview_file = ROOT / "02_项目管理" / "金毛狗脊_IS_项目总览.md"

    def load_project(self) -> dict:
        if not self.project_file.exists():
            raise FileNotFoundError(f"Project file not found: {self.project_file}")
        return json.loads(self.project_file.read_text(encoding="utf-8"))

    def read_text_file(self, path: Path) -> str:
        if not path.exists():
            return "未找到文件"
        return path.read_text(encoding="utf-8")

    def today(self) -> str:
        project = self.load_project()
        today_text = self.read_text_file(self.today_file)
        overview_text = self.read_text_file(self.overview_file)

        done_count = overview_text.count("- [x]")
        todo_count = overview_text.count("- [ ]")
        total = done_count + todo_count
        progress = int(done_count / total * 100) if total else 0

        lines = []
        lines.append("🐟 咸鱼日常打工 OS")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"📌 当前项目：{project['name']}")
        lines.append(f"📍 当前阶段：{project['stage']}")
        lines.append("")
        lines.append(f"📈 项目进度：{progress}%")
        lines.append("█" * max(1, progress // 10) + "░" * (10 - progress // 10))
        lines.append("")
        lines.append("✅ 今日优先任务")
        for i, task in enumerate(project.get("today_tasks", []), start=1):
            lines.append(f"{i}. {task}")

        lines.append("")
        lines.append("🧪 证据链状态")
        for item in project.get("evidence", []):
            lines.append(f"- {item['name']}：{item['status']}")

        lines.append("")
        lines.append("📒 今日任务文件")
        lines.append(str(self.today_file))

        lines.append("")
        lines.append("📁 项目总览文件")
        lines.append(str(self.overview_file))

        return "\n".join(lines)
