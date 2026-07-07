from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]

class ReviewEngine:
    def __init__(self):
        self.review_dir = ROOT / "01_今日打工" / "下班复盘"
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def create_daily_review(self) -> str:
        today = date.today().isoformat()
        file_path = self.review_dir / f"{today}_下班复盘.md"

        if file_path.exists():
            return f"今天的复盘已经存在：{file_path}"

        content = f"""# 下班复盘｜{today}

## 今天完成了什么？
- 

## 今天遇到了什么问题？
- 

## 今天失败/异常的地方
- 

## 可能原因
- 

## 明天最重要的 3 件事
- [ ] 
- [ ] 
- [ ] 

## 需要沉淀到失败经验库的内容
- 

## 备注
- 
"""
        file_path.write_text(content, encoding="utf-8")
        return f"已生成下班复盘：{file_path}"
