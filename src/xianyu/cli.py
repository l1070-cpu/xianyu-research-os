import sys
from .main import main as show_main
from .engines.project_engine import ProjectEngine
from .engines.review_engine import ReviewEngine
from .engines.experiment_engine import ExperimentEngine
from .engines.failure_engine import FailureEngine
from .engines.writing_engine import WritingEngine

def main():
    args = sys.argv[1:]

    if not args:
        show_main()
        return

    command = args[0]

    if command == "today":
        print(ProjectEngine().today())
    elif command == "end":
        print(ReviewEngine().create_daily_review())
    elif command == "new-exp":
        if len(args) < 2:
            print("用法：xianyu new-exp 实验名称")
            return
        name = " ".join(args[1:])
        print(ExperimentEngine().create_experiment(name))
    elif command == "fail":
        if len(args) < 2:
            print("用法：xianyu fail 问题名称")
            return
        title = " ".join(args[1:])
        print(FailureEngine().create_failure(title))
    elif command == "paper":
        if len(args) < 2:
            print("用法：xianyu paper 写作部分")
            return
        section = " ".join(args[1:])
        print(WritingEngine().create_paper_section(section))
    else:
        print(f"未知命令：{command}")
        print("可用命令：xianyu today | end | new-exp 实验名称 | fail 问题名称 | paper 写作部分")
