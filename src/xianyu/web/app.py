from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT / "src" / "xianyu" / "web" / "templates"

app = FastAPI(title="咸鱼日常打工 OS")
app.mount("/static", StaticFiles(directory=ROOT / "src" / "xianyu" / "web" / "static"), name="static")

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def read_file(path):
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "暂无内容"

@app.get("/", response_class=HTMLResponse)
def dashboard():
    today = read_file(ROOT / "01_今日打工" / "今日任务.md")
    overview = read_file(ROOT / "02_项目管理" / "金毛狗脊_IS_项目总览.md")

    done = overview.count("- [x]")
    todo = overview.count("- [ ]")
    total = done + todo
    progress = int(done / total * 100) if total else 0

    template = env.get_template("dashboard.html")
    return template.render(
        today=today,
        overview=overview,
        progress=progress
    )
