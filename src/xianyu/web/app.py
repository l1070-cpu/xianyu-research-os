from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
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

def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else "暂无内容"

def list_md(folder):
    base = ROOT / folder
    if not base.exists():
        return []
    return sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

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
    items = []
    for p in files[:30]:
        items.append({
            "name": p.name,
            "path": str(p.relative_to(ROOT)),
            "content": read(p)[:400]
        })

    template = env.get_template("module.html")
    return template.render(title=title, items=items, modules=MODULES)

@app.get("/file", response_class=HTMLResponse)
def file_page(path: str):
    p = ROOT / path
    template = env.get_template("file.html")
    return template.render(path=path, content=read(p), modules=MODULES)
