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

def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else "暂无内容"

@app.get("/", response_class=HTMLResponse)
def index():
    today = read(ROOT / "01_今日打工" / "今日任务.md")
    overview = read(ROOT / "02_项目管理" / "金毛狗脊_IS_项目总览.md")
    template = env.get_template("index.html")
    return template.render(today=today, overview=overview)
