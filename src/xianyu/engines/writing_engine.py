from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]

class WritingEngine:
    def __init__(self):
        self.paper_dir = ROOT / "06_论文写作"
        self.paper_dir.mkdir(parents=True, exist_ok=True)

    def create_paper_section(self, section: str) -> str:
        today = date.today().isoformat()
        safe_section = section.replace(" ", "_").replace("/", "_")
        file_path = self.paper_dir / f"{today}_{safe_section}.md"

        if file_path.exists():
            return f"论文写作模板已存在：{file_path}"

        content = f"""# 论文写作｜{section}

## 日期
{today}

## 写作部分
{section}

## 本部分目的

## 已有结果 / 数据

## 需要表达的核心结论

## 可用图表

## 初稿

## 需要补充的数据

## 需要查找的文献

## 修改意见
"""
        file_path.write_text(content, encoding="utf-8")
        return f"已生成论文写作模板：{file_path}"
