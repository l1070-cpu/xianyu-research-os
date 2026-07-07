import sys
from .main import main as show_main
from .engines.project_engine import ProjectEngine

def main():
    args = sys.argv[1:]

    if not args:
        show_main()
        return

    command = args[0]

    if command == "today":
        engine = ProjectEngine()
        print(engine.today())
    else:
        print(f"未知命令：{command}")
        print("可用命令：xianyu, xianyu today")
