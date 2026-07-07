import sys
from .main import main as show_main
from .engines.project_engine import ProjectEngine
from .engines.review_engine import ReviewEngine

def main():
    args = sys.argv[1:]

    if not args:
        show_main()
        return

    command = args[0]

    if command == "today":
        engine = ProjectEngine()
        print(engine.today())
    elif command == "end":
        engine = ReviewEngine()
        print(engine.create_daily_review())
    else:
        print(f"未知命令：{command}")
        print("可用命令：xianyu, xianyu today, xianyu end")
