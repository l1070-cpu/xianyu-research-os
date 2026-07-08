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
