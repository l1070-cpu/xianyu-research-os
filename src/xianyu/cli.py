import sys
from pathlib import Path
from .main import main as show_main
from .engines.project_engine import ProjectEngine
from .engines.review_engine import ReviewEngine
from .engines.experiment_engine import ExperimentEngine
from .engines.failure_engine import FailureEngine
from .engines.writing_engine import WritingEngine
from .engines.template_engine import TemplateEngine

def make_template(command, name):
    templates = {
        "lit": (
            "04_文献笔记",
            "文献笔记",
            """# 文献笔记｜{name}

## 日期
{today}

## 主题
{name}

## 检索关键词

## 核心文献

## 研究背景

## 关键发现

## 实验方法摘录

## 可借鉴之处

## 与本课题关系

## 下一步
"""
        ),
        "data": (
            "05_数据分析",
            "数据分析记录",
            """# 数据分析｜{name}

## 日期
{today}

## 数据名称
{name}

## 原始数据位置

## 分组信息

## 统计方法

## 图表类型

## 初步结果

## 异常值 / 注意事项

## 下一步
"""
        ),
        "figure": (
            "05_数据分析/科研作图",
            "科研作图记录",
            """# 科研作图｜{name}

## 日期
{today}

## 图名
{name}

## 图类型
统计图 / 机制图 / 网络图 / 分子对接图 / Graphical Abstract

## 数据来源

## 软件
GraphPad / ImageJ / Cytoscape / PyMOL / Illustrator / PowerPoint

## 图注草稿

## 修改记录

## 待优化
"""
        ),
        "sop": (
            "07_常用Prompt/SOP中心",
            "SOP记录",
            """# SOP｜{name}

## 日期
{today}

## SOP名称
{name}

## 目的

## 适用范围

## 材料与试剂

## 仪器

## 操作步骤

## 关键参数

## 质控点

## 常见失败

## 优化经验

## 版本记录
"""
        ),
        "plan": (
            "02_项目管理/课题计划",
            "课题计划",
            """# 课题计划｜{name}

## 日期
{today}

## 课题名称
{name}

## 科学问题

## 研究假设

## 技术路线

## 阶段目标

## 本周任务

## 本月任务

## 风险点

## 需要补充的资源
"""
        ),
        "network": (
            "02_项目管理/网络药理学",
            "网络药理学记录",
            """# 网络药理学｜{name}

## 日期
{today}

## 任务名称
{name}

## 输入
- 成分表：
- 疾病：
- 数据库：

## 靶点预测

## 疾病靶点

## 交集靶点

## PPI

## GO富集

## KEGG富集

## Cytoscape网络

## 核心靶点

## 下一步
"""
        ),
        "screen": (
            "02_项目管理/虚拟筛选",
            "虚拟筛选记录",
            """# 虚拟筛选｜{name}

## 日期
{today}

## 任务名称
{name}

## 输入化合物

## 输入靶点

## 筛选规则
- Lipinski：
- PAINS：
- QED：
- ADMET：

## Top候选化合物

## 筛选理由

## 下一步：分子对接 / MD / 实验验证
"""
        ),
        "docking": (
            "02_项目管理/分子对接",
            "分子对接记录",
            """# 分子对接｜{name}

## 日期
{today}

## 任务名称
{name}

## 配体

## 靶点蛋白

## PDB ID

## 软件
AutoDock Vina / OpenBabel / PyMOL

## 对接参数

## Binding Energy

## 相互作用

## 图片位置

## 下一步
"""
        ),
        "md": (
            "02_项目管理/分子动力学",
            "分子动力学记录",
            """# 分子动力学｜{name}

## 日期
{today}

## 任务名称
{name}

## 复合物来源

## 软件
GROMACS / AMBER / MDAnalysis

## 模拟时间

## RMSD

## RMSF

## Rg

## H-bond

## MM-PBSA

## 结论
"""
        ),
        "admet": (
            "02_项目管理/ADMET",
            "ADMET记录",
            """# ADMET评价｜{name}

## 日期
{today}

## 化合物
{name}

## SwissADME

## pkCSM

## ADMETlab

## 吸收

## 分布

## 代谢

## 毒性

## 综合评价
"""
        )
    }

    folder, title, template = templates[command]
    return TemplateEngine(folder, command, title, template).create(name)

def main():
    args = sys.argv[1:]

    if not args:
        show_main()
        return

    command = args[0]

    if command == "web":
        import subprocess
        project_root = Path(__file__).resolve().parents[2]
        subprocess.run(
            [
                "uvicorn",
                "xianyu.web.app:app",
                "--reload",
                "--port",
                "8001",
                "--reload-dir",
                str(project_root / "src"),
            ],
            cwd=project_root,
        )
    elif command == "today":
        print(ProjectEngine().today())
    elif command == "end":
        print(ReviewEngine().create_daily_review())
    elif command == "new-exp":
        if len(args) < 2:
            print("用法：xianyu new-exp 实验名称")
            return
        print(ExperimentEngine().create_experiment(" ".join(args[1:])))
    elif command == "fail":
        if len(args) < 2:
            print("用法：xianyu fail 问题名称")
            return
        print(FailureEngine().create_failure(" ".join(args[1:])))
    elif command == "paper":
        if len(args) < 2:
            print("用法：xianyu paper 写作部分")
            return
        print(WritingEngine().create_paper_section(" ".join(args[1:])))
    elif command in ["lit", "data", "figure", "sop", "plan", "network", "screen", "docking", "md", "admet"]:
        if len(args) < 2:
            print(f"用法：xianyu {command} 名称")
            return
        print(make_template(command, " ".join(args[1:])))
    else:
        print(f"未知命令：{command}")
        print("可用命令：")
        print("xianyu today")
        print("xianyu end")
        print("xianyu plan 课题名称")
        print("xianyu lit 文献主题")
        print("xianyu new-exp 实验名称")
        print("xianyu data 数据名称")
        print("xianyu figure 图名")
        print("xianyu network 任务名")
        print("xianyu screen 任务名")
        print("xianyu docking 任务名")
        print("xianyu md 任务名")
        print("xianyu admet 化合物名")
        print("xianyu paper 写作部分")
        print("xianyu sop SOP名称")
        print("xianyu fail 问题名称")
