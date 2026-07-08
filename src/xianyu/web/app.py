from pathlib import Path
from datetime import date
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT / "src" / "xianyu" / "web" / "templates"
STATIC_DIR = ROOT / "src" / "xianyu" / "web" / "static"

app = FastAPI(title="咸鱼日常打工 OS")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

MODULES = {
    "today": ("01_今日打工", "📋 今日打工"),
    "project": ("02_项目管理", "📁 项目管理"),
    "literature": ("04_文献笔记", "📚 文献中心"),
    "network": ("02_项目管理/网络药理学", "🌐 网络药理"),
    "docking": ("02_项目管理/分子对接", "🧲 分子对接"),
    "experiment": ("03_实验记录", "🧪 实验中心"),
    "data": ("05_数据分析", "📊 数据分析"),
    "figure": ("05_数据分析/科研作图", "🎨 科研作图"),
    "writing": ("06_论文写作", "✍️ 论文写作"),
    "memory": ("08_失败经验库", "🧠 科研记忆"),
    "capability": ("capabilities", "🧩 能力包中心"),
}

CREATE_MAP = {
    "lit": ("04_文献笔记", "文献笔记"),
    "new-exp": ("03_实验记录", "实验记录"),
    "data": ("05_数据分析", "数据分析"),
    "figure": ("05_数据分析/科研作图", "科研作图"),
    "paper": ("06_论文写作", "论文写作"),
    "sop": ("07_常用Prompt/SOP中心", "SOP"),
    "fail": ("08_失败经验库", "失败经验"),
    "network": ("02_项目管理/网络药理学", "网络药理学"),
    "docking": ("02_项目管理/分子对接", "分子对接"),
}

TEMPLATE = """# {title}｜{name}

## 日期
{today}

## 目的

## 输入 / 材料 / 数据

## 操作流程

## 关键参数

## 结果记录

## 异常 / 问题

## 下一步
"""

def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else "暂无内容"

def list_md(folder):
    base = ROOT / folder
    if not base.exists():
        return []
    return sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

def safe_name(name):
    return name.replace(" ", "_").replace("/", "_")

@app.get("/", response_class=HTMLResponse)
def index():
    today = read(ROOT / "01_今日打工" / "今日任务.md")
    overview = read(ROOT / "02_项目管理" / "金毛狗脊_IS_项目总览.md")
    template = env.get_template("index.html")
    return template.render(today=today, overview=overview, modules=MODULES)

@app.get("/module/{key}", response_class=HTMLResponse)
def module_page(key: str):
    if key not in MODULES:
        return HTMLResponse("模块不存在", status_code=404)

    folder, title = MODULES[key]
    files = list_md(folder)
    items = [{"name": p.name, "path": str(p.relative_to(ROOT)), "content": read(p)[:400]} for p in files[:30]]
    template = env.get_template("module.html")
    return template.render(title=title, items=items, modules=MODULES)

@app.get("/file", response_class=HTMLResponse)
def file_page(path: str):
    p = ROOT / path
    template = env.get_template("file.html")
    return template.render(path=path, content=read(p), modules=MODULES)

@app.get("/new", response_class=HTMLResponse)
def new_page():
    template = env.get_template("new.html")
    return template.render(modules=MODULES, create_map=CREATE_MAP)

@app.post("/new")
def create_record(record_type: str = Form(...), name: str = Form(...)):
    folder, title = CREATE_MAP[record_type]
    today = date.today().isoformat()
    out_dir = ROOT / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{today}_{safe_name(name)}.md"
    if not file_path.exists():
        file_path.write_text(TEMPLATE.format(title=title, name=name, today=today), encoding="utf-8")
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)

@app.get("/project", response_class=HTMLResponse)
def project_page():
    overview_path = ROOT / "02_项目管理" / "金毛狗脊_IS_项目总览.md"
    overview = read(overview_path)
    done = overview.count("- [x]")
    todo = overview.count("- [ ]")
    total = done + todo
    progress = int(done / total * 100) if total else 0
    template = env.get_template("project.html")
    return template.render(overview=overview, progress=progress, modules=MODULES)


@app.get("/search", response_class=HTMLResponse)
def search_page(q: str = ""):
    results = []
    if q:
        for folder in [
            "01_今日打工",
            "02_项目管理",
            "03_实验记录",
            "04_文献笔记",
            "05_数据分析",
            "06_论文写作",
            "07_常用Prompt",
            "08_失败经验库",
            "capabilities"
        ]:
            base = ROOT / folder
            if not base.exists():
                continue
            for file in base.rglob("*.md"):
                content = read(file)
                if q.lower() in content.lower() or q.lower() in file.name.lower():
                    results.append({
                        "name": file.name,
                        "path": str(file.relative_to(ROOT)),
                        "content": content[:300]
                    })

    template = env.get_template("search.html")
    return template.render(q=q, results=results, modules=MODULES)


@app.get("/literature", response_class=HTMLResponse)
def literature_index():
    files = list_md("04_文献笔记")
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("literature/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/literature/new")
def literature_new(title: str = Form(...), keywords: str = Form("")):
    today = date.today().isoformat()
    folder = ROOT / "04_文献笔记"
    folder.mkdir(parents=True, exist_ok=True)
    filename = safe_name(title)
    file_path = folder / f"{today}_{filename}.md"

    if not file_path.exists():
        content = f"""# 文献笔记｜{title}

## 日期
{today}

## 关键词
{keywords}

## 文献信息
- 标题：
- 作者：
- 期刊：
- 年份：
- DOI：

## 一句话总结

## 研究背景

## 研究目的

## 实验设计 / 方法

## 主要结果

## 创新点

## 不足与局限

## Research Gap

## 与我的课题关系

## 可用于 Introduction 的内容

## 可用于 Discussion 的内容

## 下一步需要追踪的文献
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/experiment", response_class=HTMLResponse)
def experiment_index():
    files = list_md("03_实验记录")
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("experiment/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/experiment/new")
def experiment_new(title: str = Form(...), exp_type: str = Form("general")):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    type_map = {
        "cell": "细胞实验",
        "wb": "Western Blot",
        "qpcr": "RT-qPCR",
        "flow": "流式细胞术",
        "image": "成像 / IF / ROS / JC-1",
        "column": "柱层析 / 提取纯化",
        "general": "通用实验"
    }

    if not file_path.exists():
        content = f"""# 实验记录｜{title}

## 日期
{today}

## 实验类型
{type_map.get(exp_type, "通用实验")}

## 实验目的

## 样品 / 细胞 / 试剂

## 分组设计
- Control：
- Model：
- Treatment：
- Positive control：

## 操作步骤

## 关键参数
- 细胞密度：
- 处理浓度：
- 处理时间：
- 检测时间：
- 重复数：

## 原始数据位置

## 结果观察

## 异常情况

## 原因分析

## 下一步优化

## 是否需要沉淀为 SOP
- [ ] 是
- [ ] 否
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)
