from pathlib import Path
from datetime import date
import sys

ROOT = Path(__file__).resolve().parents[3]

class ExperimentEngine:
    def __init__(self):
        self.exp_dir = ROOT / "03_实验记录"
        self.exp_dir.mkdir(parents=True, exist_ok=True)

    def create_experiment(self, name: str) -> str:
        today = date.today().isoformat()
        safe_name = name.replace(" ", "_").replace("/", "_")
        file_path = self.exp_dir / f"{today}_{safe_name}.md"

        if file_path.exists():
            return f"实验记录已存在：{file_path}"

        content = f"""# 实验记录｜{name}

## 日期
{today}

## 实验名称
{name}

## 实验目的

## 样品 / 细胞 / 试剂

## 分组设计

## 操作步骤

## 关键参数

## 结果观察

## 异常情况

## 原因分析

## 下一步优化
"""
        file_path.write_text(content, encoding="utf-8")
        return f"已生成实验记录：{file_path}"
