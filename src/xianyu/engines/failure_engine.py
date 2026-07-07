from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]

class FailureEngine:
    def __init__(self):
        self.fail_dir = ROOT / "08_失败经验库"
        self.fail_dir.mkdir(parents=True, exist_ok=True)

    def create_failure(self, title: str) -> str:
        today = date.today().isoformat()
        safe_title = title.replace(" ", "_").replace("/", "_")
        file_path = self.fail_dir / f"{today}_{safe_title}.md"

        if file_path.exists():
            return f"失败经验记录已存在：{file_path}"

        content = f"""# 失败经验记录｜{title}

## 日期
{today}

## 实验 / 任务
{title}

## 出现的问题

## 当时条件

## 可能原因

## 解决办法

## 下次避免方法

## 标签
"""
        file_path.write_text(content, encoding="utf-8")
        return f"已生成失败经验记录：{file_path}"
