from pathlib import Path
from datetime import date
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
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
    "natural_product": ("02_项目管理/天然产物", "🌿 天然产物"),
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
    recent = []
    for key, item in MODULES.items():
        folder, title = item
        files = list_md(folder)
        if files:
            f = files[0]
            recent.append({
                "title": title,
                "name": f.name,
                "path": str(f.relative_to(ROOT)),
                "content": read(f)[:200]
            })

    template = env.get_template("index.html")
    return template.render(today=today, overview=overview, modules=MODULES, recent=recent)

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


@app.get("/data", response_class=HTMLResponse)
def data_index():
    files = list_md("05_数据分析")
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("data/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/data/new")
def data_new(title: str = Form(...), data_type: str = Form("general")):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    type_map = {
        "cck8": "CCK-8",
        "wb": "Western Blot 灰度",
        "qpcr": "RT-qPCR",
        "flow": "流式细胞术",
        "image": "ImageJ 图像定量",
        "prism": "GraphPad Prism",
        "general": "通用数据"
    }

    if not file_path.exists():
        content = f"""# 数据分析记录｜{title}

## 日期
{today}

## 数据类型
{type_map.get(data_type, "通用数据")}

## 原始数据位置

## 实验对应记录

## 分组信息
- Control：
- Model：
- Treatment：
- Positive control：

## 重复数

## 数据整理规则

## 统计方法
- t test：
- One-way ANOVA：
- Two-way ANOVA：
- 非参数检验：
- 多重比较：

## 作图方式
- 柱状图：
- 折线图：
- 散点图：
- 热图：
- 其他：

## 初步结果

## 异常值 / 排除标准

## 统计结论

## 可用于论文 Results 的表达

## 下一步
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/figure", response_class=HTMLResponse)
def figure_index():
    files = list_md("05_数据分析/科研作图")
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("figure/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/figure/new")
def figure_new(title: str = Form(...), figure_type: str = Form("general")):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "科研作图"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    type_map = {
        "stat": "统计图 / GraphPad",
        "imagej": "ImageJ 定量图",
        "network": "网络图 / Cytoscape",
        "docking": "分子对接图 / PyMOL",
        "mechanism": "机制图",
        "abstract": "Graphical Abstract",
        "general": "通用 Figure"
    }

    if not file_path.exists():
        content = f"""# 科研作图记录｜{title}

## 日期
{today}

## 图类型
{type_map.get(figure_type, "通用 Figure")}

## 对应项目

## 对应实验 / 数据

## 图的核心结论

## 数据来源

## 使用软件
- GraphPad Prism：
- ImageJ：
- Cytoscape：
- PyMOL：
- PowerPoint / Illustrator：

## 图组成
- A：
- B：
- C：
- D：

## 图注草稿

## 统计标注
- n =
- mean ± SD / SEM：
- 统计方法：
- 显著性：

## 当前问题

## 修改记录

## 最终文件位置

## 是否可进入论文
- [ ] 是
- [ ] 否
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/writing", response_class=HTMLResponse)
def writing_index():
    files = list_md("06_论文写作")
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("writing/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/writing/new")
def writing_new(title: str = Form(...), section_type: str = Form("discussion")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    section_map = {
        "introduction": "Introduction",
        "methods": "Materials and Methods",
        "results": "Results",
        "discussion": "Discussion",
        "abstract": "Abstract",
        "cover": "Cover Letter",
        "response": "Response Letter"
    }

    if not file_path.exists():
        content = f"""# 论文写作｜{title}

## 日期
{today}

## 写作部分
{section_map.get(section_type, "Discussion")}

## 本部分目的

## 已有数据 / 图表

## 核心结论

## 需要引用的文献

## 初稿

## 逻辑检查
- [ ] 是否区分预测结果与实验验证结果
- [ ] 是否避免结论过度
- [ ] 是否与 Figure 对应
- [ ] 是否说明机制证据链

## 需要补充的数据

## 修改意见

## 最终版本
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/network", response_class=HTMLResponse)
def network_index():
    files = list_md("02_项目管理/网络药理学")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("network/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/network/new")
def network_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "网络药理学"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 网络药理学任务｜{title}

## 日期
{today}

## 研究对象
- 中药 / 提取物：
- 疾病：
- 目标机制：

## 输入文件
- 成分表：
- 疾病靶点表：
- 交集靶点表：

## Step 1 成分整理

## Step 2 靶点预测
- SwissTargetPrediction：
- TCMSP / BATMAN / SEA：
- UniProt 标准化：

## Step 3 疾病靶点
- GeneCards：
- OMIM：
- DisGeNET：
- DrugBank：

## Step 4 交集靶点

## Step 5 PPI
- STRING 参数：
- 物种：
- 置信度：
- 导出文件：

## Step 6 GO 富集

## Step 7 KEGG 富集

## Step 8 Cytoscape 网络
- 成分-靶点网络：
- PPI 网络：
- 靶点-通路网络：

## 核心成分

## 核心靶点

## 核心通路

## 可进入分子对接的组合

## 论文 Results 草稿

## 待补充 / 风险点
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/screen", response_class=HTMLResponse)
def screen_index():
    files = list_md("02_项目管理/虚拟筛选")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("screen/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/screen/new")
def screen_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "虚拟筛选"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 虚拟筛选任务｜{title}

## 日期
{today}

## 筛选目的

## 输入化合物
- 成分表：
- SMILES：
- SDF：

## 输入靶点
- 靶点名称：
- PDB ID：
- 来源：

## 筛选规则
- Lipinski：
- PAINS：
- QED：
- OB：
- DL：
- GI absorption：
- BBB：
- Toxicity：

## ADMET 初筛
- SwissADME：
- pkCSM：
- ADMETlab：

## Top 候选化合物

## 排除化合物及原因

## 推荐进入分子对接的组合

## 结果解释

## 风险点
- 是否结构明确：
- 是否数据库预测可靠：
- 是否需要实验验证：

## 下一步
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/md", response_class=HTMLResponse)
def md_index():
    files = list_md("02_项目管理/分子动力学")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("md/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/md/new")
def md_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "分子动力学"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 分子动力学任务｜{title}

## 日期
{today}

## MD 目的

## 复合物来源
- Docking 任务：
- 配体：
- 蛋白：
- PDB ID：

## 软件与环境
- GROMACS：
- AMBER：
- CHARMM：
- MDAnalysis：
- 服务器 / 本地：

## 前处理
- 蛋白处理：
- 配体参数：
- 力场：
- 水模型：
- 离子浓度：
- 盒子大小：

## 模拟流程
- 能量最小化：
- NVT：
- NPT：
- Production MD：
- 模拟时长：

## 分析指标
- RMSD：
- RMSF：
- Rg：
- SASA：
- H-bond：
- PCA：
- MM-PBSA / MM-GBSA：

## 结果文件位置

## 图表位置
- RMSD 图：
- RMSF 图：
- H-bond 图：
- MM-PBSA 图：

## 结果解释

## 论文 Results 草稿

## 风险点
- 体系是否稳定：
- 配体参数是否可靠：
- 模拟时间是否足够：
- 是否存在过度解释：
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/admet", response_class=HTMLResponse)
def admet_index():
    files = list_md("02_项目管理/ADMET")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("admet/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/admet/new")
def admet_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "ADMET"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# ADMET评价任务｜{title}

## 日期
{today}

## 评价目的

## 化合物信息
- 化合物名称：
- PubChem CID：
- SMILES：
- 分子式：
- 分子量：

## 使用平台
- SwissADME：
- pkCSM：
- ADMETlab：
- ProTox-II：
- 其他：

## 药物相似性
- Lipinski：
- Veber：
- Ghose：
- Egan：
- Muegge：

## 吸收 Absorption
- GI absorption：
- Caco-2 permeability：
- P-gp substrate：
- Bioavailability：

## 分布 Distribution
- BBB permeability：
- Plasma protein binding：
- VDss：

## 代谢 Metabolism
- CYP450 inhibition：
- CYP450 substrate：

## 排泄 Excretion
- Total clearance：
- Renal OCT2 substrate：

## 毒性 Toxicity
- AMES：
- hERG：
- Hepatotoxicity：
- LD50：
- Skin sensitization：

## 综合评价
- 是否建议进入分子对接：
- 是否建议进入细胞实验：
- 主要优势：
- 主要风险：

## 论文可用表述

## 下一步
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/memory", response_class=HTMLResponse)
def memory_index():
    files = list_md("08_失败经验库")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("memory/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/memory/new")
def memory_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "08_失败经验库"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 科研记忆｜{title}

## 日期
{today}

## 类型
失败经验 / SOP优化 / 实验技巧 / 数据分析经验 / 写作经验

## 发生场景

## 出现的问题

## 当时条件

## 可能原因

## 解决办法

## 最终有效方案

## 下次避免方法

## 可复用经验

## 关联项目

## 关联实验 / 数据 / 文献

## 标签
- 
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/natural-product", response_class=HTMLResponse)
def natural_product_index():
    files = list_md("02_项目管理/天然产物")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("natural_product/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/natural-product/new")
def natural_product_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "天然产物"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 天然产物 / UPLC-QTOF-MS 成分分析｜{title}

## 日期
{today}

## 样品信息
- 样品名称：
- 来源：
- 处理方式：
- 批次：
- 保存条件：

## 提取方法
- 提取溶剂：
- 料液比：
- 温度：
- 时间：
- 超声 / 回流 / 浸提：
- 浓缩方式：

## UPLC-QTOF/MS 条件
- 仪器：
- 色谱柱：
- 流动相：
- 梯度：
- 流速：
- 柱温：
- 进样量：
- 电离模式：
- 扫描范围：

## 原始数据位置

## 数据处理
- Peak picking：
- 去噪：
- 对齐：
- 归一化：
- 数据库匹配：

## 数据库比对
- PubChem：
- MassBank：
- GNPS：
- HMDB：
- ChemSpider：
- 文献比对：

## 候选成分表
| 序号 | 成分名称 | 分子式 | m/z | RT | MS/MS特征 | 匹配来源 | 可信度 |
|---|---|---|---|---|---|---|---|

## 成分类别
- 黄酮类：
- 酚酸类：
- 三萜类：
- 其他：

## 拟进入后续分析的成分

## 与网络药理学衔接
- 是否有结构：
- 是否有 SMILES：
- 是否可进行靶点预测：

## 风险点
- 是否同分异构体混淆：
- 是否需要标准品验证：
- 是否定性过度：

## 下一步
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/sop", response_class=HTMLResponse)
def sop_index():
    files = list_md("07_常用Prompt/SOP中心")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("sop/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/sop/new")
def sop_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "07_常用Prompt" / "SOP中心"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# SOP｜{title}

## 日期
{today}

## SOP 目的

## 适用场景

## 材料与试剂

## 仪器设备

## 实验前准备

## 标准操作步骤

## 关键参数

## 质控点

## 常见失败

## 故障排查

## 我的优化经验

## 数据记录模板

## 安全注意事项

## 版本记录
- v1.0：
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/capability", response_class=HTMLResponse)
def capability_index():
    files = list_md("capabilities")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:50]]
    template = env.get_template("capability/index.html")
    return template.render(items=items, modules=MODULES)


@app.get("/edit", response_class=HTMLResponse)
def edit_file_page(path: str):
    p = ROOT / path
    template = env.get_template("edit.html")
    return template.render(path=path, content=read(p), modules=MODULES)

@app.post("/edit")
def save_file(path: str = Form(...), content: str = Form(...)):
    p = ROOT / path
    p.write_text(content, encoding="utf-8")
    return RedirectResponse(url=f"/file?path={path}", status_code=303)


@app.post("/end")
def end_review_page():
    today = date.today().isoformat()
    folder = ROOT / "01_今日打工" / "下班复盘"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_下班复盘.md"

    if not file_path.exists():
        content = f"""# 下班复盘｜{today}

## 今天完成了什么？
- 

## 今天遇到了什么问题？
- 

## 今天失败 / 异常的地方
- 

## 可能原因
- 

## 明天最重要的 3 件事
- [ ] 
- [ ] 
- [ ] 

## 需要沉淀到科研记忆的内容
- 

## 备注
- 
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/delete")
def delete_file(path: str = Form(...)):
    allowed_prefixes = [
        "01_今日打工",
        "02_项目管理",
        "03_实验记录",
        "04_文献笔记",
        "05_数据分析",
        "06_论文写作",
        "07_常用Prompt",
        "08_失败经验库",
        "capabilities"
    ]

    if not any(path.startswith(prefix) for prefix in allowed_prefixes):
        return HTMLResponse("禁止删除系统核心文件", status_code=403)

    p = ROOT / path
    if p.exists() and p.is_file() and p.suffix == ".md":
        p.unlink()

    return RedirectResponse(url="/", status_code=303)


@app.post("/snapshot")
def git_snapshot():
    import subprocess
    from datetime import datetime

    msg = "web snapshot " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subprocess.run(["git", "add", "."], cwd=ROOT)
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT)
    subprocess.run(["git", "push"], cwd=ROOT)

    return RedirectResponse(url="/", status_code=303)


@app.get("/help", response_class=HTMLResponse)
def help_index():
    template = env.get_template("help/index.html")
    return template.render(modules=MODULES)


@app.post("/backup")
def backup_project():
    import zipfile
    from datetime import datetime

    archive_dir = ROOT / "99_Archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = archive_dir / f"xianyu_backup_{timestamp}.zip"

    include_dirs = [
        "01_今日打工",
        "02_项目管理",
        "03_实验记录",
        "04_文献笔记",
        "05_数据分析",
        "06_论文写作",
        "07_常用Prompt",
        "08_失败经验库",
        "capabilities",
        "projects"
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in include_dirs:
            base = ROOT / folder
            if not base.exists():
                continue
            for file in base.rglob("*"):
                if file.is_file():
                    z.write(file, file.relative_to(ROOT))

    return RedirectResponse(url=f"/file?path={zip_path.relative_to(ROOT)}", status_code=303)


@app.get("/upload-pdf", response_class=HTMLResponse)
def upload_pdf_page():
    template = env.get_template("upload_pdf.html")
    return template.render(modules=MODULES)

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    folder = ROOT / "04_文献笔记" / "PDF库"
    folder.mkdir(parents=True, exist_ok=True)

    filename = file.filename.replace(" ", "_")
    out_path = folder / filename

    content = await file.read()
    out_path.write_bytes(content)

    return RedirectResponse(url="/literature", status_code=303)


@app.get("/pdf-library", response_class=HTMLResponse)
def pdf_library():
    folder = ROOT / "04_文献笔记" / "PDF库"
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(folder.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = [{"name": f.name, "path": str(f.relative_to(ROOT))} for f in files]
    template = env.get_template("pdf_library.html")
    return template.render(items=items, modules=MODULES)


@app.get("/pdf")
def open_pdf(path: str):
    p = ROOT / path
    if p.exists() and p.is_file() and p.suffix.lower() == ".pdf":
        return FileResponse(p, media_type="application/pdf", filename=p.name)
    return HTMLResponse("PDF 不存在", status_code=404)
