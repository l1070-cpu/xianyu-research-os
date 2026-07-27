from pathlib import Path
from dotenv import load_dotenv
import re
import csv
import os
import json
import httpx
from pypdf import PdfReader
from datetime import date
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from xianyu.web.literature_v2 import router as literature_v2_router

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")
TEMPLATE_DIR = ROOT / "src" / "xianyu" / "web" / "templates"
STATIC_DIR = ROOT / "src" / "xianyu" / "web" / "static"

app = FastAPI(title="咸鱼日常打工 OS")
app.include_router(literature_v2_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


def get_runtime_status():
    runtime_dir = os.getenv("XIANYU_RUNTIME_DIR", "/tmp/xianyu_research_os_runtime")
    return {
        "project_root": str(ROOT),
        "source_root": str(ROOT / "src"),
        "runtime_dir": runtime_dir,
    }

MODULES = {
    "today": ("01_今日打工", "📋 今日打工"),
    "project": ("02_项目管理", "📁 项目管理"),
    "literature": ("04_文献笔记", "📚 文献中心"),
    "natural_product": ("02_项目管理/天然产物", "🌿 天然产物"),
    "network": ("02_项目管理/网络药理学", "🌐 网络药理"),
    "gene": ("02_项目管理/Gene_Omics", "🧬 Gene / Omics"),
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


def list_files(folder, suffixes=None):
    base = ROOT / folder
    if not base.exists():
        return []
    files = [p for p in base.rglob("*") if p.is_file()]
    if suffixes:
        suffixes = {s.lower() for s in suffixes}
        files = [p for p in files if p.suffix.lower() in suffixes]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

def safe_name(name):
    return name.replace(" ", "_").replace("/", "_")


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, flags=re.S)
    return match.group(1).strip() if match else ""


def ai_json_or_prompt(system_prompt: str, user_prompt: str):
    base = os.getenv("AI_API_BASE", "").rstrip("/")
    key = os.getenv("AI_API_KEY", "")
    model = os.getenv("AI_MODEL", "")
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    if not (base and key and model):
        return {
            "status": "not_configured",
            "prompt": full_prompt,
        }

    try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.1,
        }
        response = httpx.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception:
            return {
                "status": "raw",
                "raw": content,
            }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "prompt": full_prompt,
        }


def load_projects_v2():
    import json

    projects_root = ROOT / "projects"
    projects = []

    for project_file in projects_root.glob("*/project.json"):
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
            projects.append(data)
        except Exception:
            continue

    projects.sort(key=lambda x: x.get("name", ""))
    return projects


def get_current_project_id():
    import json

    current_file = ROOT / "projects" / "current_project.json"
    if not current_file.exists():
        return ""

    try:
        data = json.loads(current_file.read_text(encoding="utf-8"))
        return data.get("project_id", "")
    except Exception:
        return ""


def get_current_project():
    current_id = get_current_project_id()
    if not current_id:
        return None

    for project in load_projects_v2():
        if project.get("project_id") == current_id:
            return project
    return None


def get_current_project_root():
    current_id = get_current_project_id()
    if not current_id:
        return None
    project_root = ROOT / "projects" / current_id
    return project_root if project_root.exists() else None


def get_recent_project_imports(limit_per_folder: int = 5):
    project_root = get_current_project_root()
    if not project_root:
        return {}

    folder_labels = {
        "gene_omics": "DEG / Gene",
        "targets": "成分靶点",
        "disease": "疾病靶点",
        "network": "交集 / 网络",
        "enrichment": "富集结果",
        "data": "通用数据",
    }

    result = {}
    for folder, label in folder_labels.items():
        target_dir = project_root / folder
        items = []
        if target_dir.exists():
            for file in sorted(target_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if file.is_file():
                    items.append({
                        "name": file.name,
                        "folder": folder,
                        "label": label,
                        "path": str(file.relative_to(ROOT)),
                    })
                if len(items) >= limit_per_folder:
                    break
        result[folder] = items
    return result


def build_network_intersection_context():
    current_project = get_current_project() or {}
    recent_imports = get_recent_project_imports()
    deg_path = recent_imports.get("gene_omics", [{}])[0].get("path", "") if recent_imports.get("gene_omics") else ""
    target_path = recent_imports.get("targets", [{}])[0].get("path", "") if recent_imports.get("targets") else ""
    disease_path = recent_imports.get("disease", [{}])[0].get("path", "") if recent_imports.get("disease") else ""
    network_path = recent_imports.get("network", [{}])[0].get("path", "") if recent_imports.get("network") else ""

    import_summary = []
    if deg_path:
        import_summary.append(f"- DEG / Gene：{deg_path}")
    if target_path:
        import_summary.append(f"- 成分靶点：{target_path}")
    if disease_path:
        import_summary.append(f"- 疾病靶点：{disease_path}")
    if network_path:
        import_summary.append(f"- 交集 / 网络：{network_path}")

    project_name = current_project.get("short_name") or current_project.get("name") or "当前项目"
    disease_name = current_project.get("disease") or "模型"
    object_name = current_project.get("research_object") or "研究对象"

    auto_title = f"{project_name}_{disease_name}_DEG交集分析"
    if not deg_path and (target_path or disease_path):
        auto_title = f"{project_name}_{object_name}_网络药理交集分析"

    readiness = {
        "has_deg": bool(deg_path),
        "has_target": bool(target_path),
        "has_disease": bool(disease_path),
        "has_network": bool(network_path),
    }
    readiness["can_auto_create"] = readiness["has_deg"] or (
        readiness["has_target"] and readiness["has_disease"]
    )

    if readiness["can_auto_create"]:
        auto_hint = "系统会自动引用当前项目最近导入的 DEG、成分靶点和疾病靶点表。"
    else:
        auto_hint = "当前还缺少可用输入，建议先在“数据入口”上传 DEG、成分靶点或疾病靶点表。"

    return {
        "current_project": current_project,
        "recent_imports": recent_imports,
        "deg_path": deg_path,
        "target_path": target_path,
        "disease_path": disease_path,
        "network_path": network_path,
        "import_summary_text": "\n".join(import_summary) if import_summary else "- 当前还没有可自动引用的输入表，请先去“数据入口”上传。",
        "auto_title": auto_title,
        "auto_hint": auto_hint,
        "readiness": readiness,
    }


def build_network_figure_context():
    current_project = get_current_project() or {}
    recent_imports = get_recent_project_imports()
    intersection_path = recent_imports.get("network", [{}])[0].get("path", "") if recent_imports.get("network") else ""
    enrichment_path = recent_imports.get("enrichment", [{}])[0].get("path", "") if recent_imports.get("enrichment") else ""
    target_path = recent_imports.get("targets", [{}])[0].get("path", "") if recent_imports.get("targets") else ""
    disease_path = recent_imports.get("disease", [{}])[0].get("path", "") if recent_imports.get("disease") else ""

    summary = []
    if intersection_path:
        summary.append(f"- 交集 / 网络：{intersection_path}")
    if enrichment_path:
        summary.append(f"- 富集结果：{enrichment_path}")
    if target_path:
        summary.append(f"- 成分靶点：{target_path}")
    if disease_path:
        summary.append(f"- 疾病靶点：{disease_path}")

    project_name = current_project.get("short_name") or current_project.get("name") or "当前项目"
    disease_name = current_project.get("disease") or "模型"
    auto_title = f"{project_name}_{disease_name}_网络药理图表包"

    readiness = {
        "has_network": bool(intersection_path),
        "has_enrichment": bool(enrichment_path),
        "has_targets": bool(target_path),
        "has_disease": bool(disease_path),
    }
    readiness["can_auto_create"] = (
        readiness["has_network"]
        or readiness["has_enrichment"]
        or (readiness["has_targets"] and readiness["has_disease"])
    )

    if readiness["can_auto_create"]:
        auto_hint = "系统会自动引用当前项目最近的交集表、富集结果和靶点输入。"
    else:
        auto_hint = "当前还缺少可用图表输入，建议先完成交集分析或导入富集结果。"

    recommendations = []
    if readiness["has_targets"] and readiness["has_disease"]:
        recommendations.append({
            "name": "Venn / UpSet 交集图",
            "priority": "高优先级",
            "reason": "已经具备成分靶点和疾病靶点输入，适合先展示交集范围。",
        })
    if readiness["has_network"]:
        recommendations.append({
            "name": "PPI 网络图",
            "priority": "高优先级",
            "reason": "已有交集或网络结果，可直接整理核心靶点关系。",
        })
        recommendations.append({
            "name": "核心靶点柱状图",
            "priority": "中优先级",
            "reason": "适合从交集结果中挑出 degree 更高的核心靶点做排序展示。",
        })
    if readiness["has_targets"]:
        recommendations.append({
            "name": "成分-靶点网络图",
            "priority": "高优先级",
            "reason": "已有成分靶点输入，适合展示主要活性成分与候选靶点的连接关系。",
        })
    if readiness["has_enrichment"]:
        recommendations.append({
            "name": "GO 气泡图",
            "priority": "高优先级",
            "reason": "已有富集结果，可直接展示生物过程和功能条目。",
        })
        recommendations.append({
            "name": "KEGG 气泡图",
            "priority": "高优先级",
            "reason": "已有富集结果，适合展示关键通路并衔接后续机制讨论。",
        })

    if not recommendations:
        recommendations.append({
            "name": "等待输入数据",
            "priority": "准备中",
            "reason": "建议先导入交集分析表、靶点表或富集结果，再自动推荐正式图表。",
        })

    return {
        "current_project": current_project,
        "recent_imports": recent_imports,
        "intersection_path": intersection_path,
        "enrichment_path": enrichment_path,
        "target_path": target_path,
        "disease_path": disease_path,
        "input_summary_text": "\n".join(summary) if summary else "- 当前还没有可自动引用的网络药理输入表。",
        "auto_title": auto_title,
        "auto_hint": auto_hint,
        "readiness": readiness,
        "recommendations": recommendations,
    }


def build_network_legend_checklist(recommendations):
    blocks = []
    mapping = {
        "Venn / UpSet 交集图": """### Venn / UpSet 交集图
- 图号：
- 图标题：活性成分靶点、疾病靶点与差异基因的交集分析
- 应写清：比较对象、交集数量、筛选标准、数据库来源
- 结果句模板：Venn/UpSet analysis identified the shared targets between compound-associated targets, disease-related genes, and differentially expressed genes.
- 待补充：交集基因数、数据库名称、筛选阈值
""",
        "PPI 网络图": """### PPI 网络图
- 图号：
- 图标题：交集靶点的蛋白互作网络
- 应写清：STRING版本、物种、置信度阈值、节点数、边数
- 结果句模板：A PPI network of the shared targets was constructed to identify densely connected hub genes.
- 待补充：节点数、边数、核心靶点名称
""",
        "核心靶点柱状图": """### 核心靶点柱状图
- 图号：
- 图标题：核心靶点排序
- 应写清：排序指标（degree/betweenness/其他）、Top N、筛选依据
- 结果句模板：Hub target ranking highlighted several key genes with higher network centrality.
- 待补充：Top基因列表、排序指标
""",
        "成分-靶点网络图": """### 成分-靶点网络图
- 图号：
- 图标题：活性成分-潜在靶点网络
- 应写清：成分数、靶点数、边数、关键成分筛选标准
- 结果句模板：A component-target network was established to characterize the multi-component and multi-target features of the project.
- 待补充：核心成分名称、节点和边数量
""",
        "GO 气泡图": """### GO 气泡图
- 图号：
- 图标题：GO 富集分析
- 应写清：BP/CC/MF 分类、Top条目数量、显著性标准
- 结果句模板：GO enrichment analysis indicated that the shared targets were mainly involved in biological processes related to oxidative stress, apoptosis, and inflammation.
- 待补充：Top条目、p值或FDR阈值
""",
        "KEGG 气泡图": """### KEGG 气泡图
- 图号：
- 图标题：KEGG 通路富集分析
- 应写清：Top通路数量、显著性标准、代表性通路
- 结果句模板：KEGG pathway analysis suggested that the shared targets were enriched in several signaling pathways associated with the disease mechanism.
- 待补充：代表性通路名称、阈值、Top通路数量
""",
        "等待输入数据": """### 图注准备中
- 当前尚缺少正式输入表。
- 建议先补交集表、靶点表或富集结果，再自动生成正式图注清单。
""",
    }

    for item in recommendations:
        block = mapping.get(item['name'])
        if block:
            blocks.append(block)

    if not blocks:
        blocks.append(mapping['等待输入数据'])

    return "\n".join(blocks)


def build_network_legend_bundle(recommendations, project_name: str):
    figure_1_items = []
    figure_2_items = []
    supplementary_items = []

    for item in recommendations:
        name = item["name"]
        if name == "Venn / UpSet 交集图":
            figure_1_items.append(
                "- Panel A：Venn / UpSet plot showing the overlap among compound-associated targets, disease-related targets, and differentially expressed genes."
            )
        elif name == "成分-靶点网络图":
            figure_1_items.append(
                f"- Panel B：Component-target network illustrating the multi-component and multi-target characteristics of {project_name}."
            )
        elif name == "PPI 网络图":
            figure_2_items.append(
                "- Panel A：Protein-protein interaction network constructed from the shared targets to identify hub genes."
            )
        elif name == "核心靶点柱状图":
            figure_2_items.append(
                "- Panel B：Ranking plot of hub targets based on network centrality metrics."
            )
        elif name == "GO 气泡图":
            supplementary_items.append(
                "- Supplementary Panel A：GO enrichment bubble plot showing the major biological processes, cellular components, or molecular functions."
            )
        elif name == "KEGG 气泡图":
            supplementary_items.append(
                "- Supplementary Panel B：KEGG enrichment bubble plot highlighting the representative signaling pathways."
            )

    if not figure_1_items:
        figure_1_items.append("- Panel A：待补充网络药理主图。")
    if not figure_2_items:
        figure_2_items.append("- Panel A：待补充核心网络关系图。")
    if not supplementary_items:
        supplementary_items.append("- Supplementary Panel A：待补充富集分析或附加网络图。")

    return f"""## 建议图号分配
- Figure 1：交集分析 + 成分-靶点网络主图
- Figure 2：PPI + 核心靶点排序主图
- Supplementary Figure 1：GO / KEGG 富集结果

## Figure Legend 初稿

### Figure 1
**Title**
Integrated network pharmacology overview of {project_name}.

**Legend Draft**
{chr(10).join(figure_1_items)}

### Figure 2
**Title**
Hub target interaction landscape derived from shared targets.

**Legend Draft**
{chr(10).join(figure_2_items)}

### Supplementary Figure 1
**Title**
Functional enrichment profiles of the shared targets.

**Legend Draft**
{chr(10).join(supplementary_items)}
"""


def build_network_results_bundle(recommendations, project_name: str):
    figure_1_lines = []
    figure_2_lines = []
    supplementary_lines = []

    for item in recommendations:
        name = item["name"]
        if name == "Venn / UpSet 交集图":
            figure_1_lines.append(
                "- Figure 1A：交代活性成分靶点、疾病靶点和差异基因之间的交集关系，并写清共享靶点数量。"
            )
        elif name == "成分-靶点网络图":
            figure_1_lines.append(
                f"- Figure 1B：说明 {project_name} 呈现多成分-多靶点作用特征，并指出关键成分或连接度较高的节点。"
            )
        elif name == "PPI 网络图":
            figure_2_lines.append(
                "- Figure 2A：描述共享靶点构建的 PPI 网络特征，并指出网络中连接度较高的核心靶点。"
            )
        elif name == "核心靶点柱状图":
            figure_2_lines.append(
                "- Figure 2B：补充核心靶点排序结果，强调排名靠前的候选关键基因。"
            )
        elif name == "GO 气泡图":
            supplementary_lines.append(
                "- Supplementary Figure 1A：概述 GO 富集主要涉及的生物过程、细胞组分或分子功能。"
            )
        elif name == "KEGG 气泡图":
            supplementary_lines.append(
                "- Supplementary Figure 1B：总结 KEGG 富集到的代表性信号通路，并衔接后续机制验证。"
            )

    if not figure_1_lines:
        figure_1_lines.append("- Figure 1：待补充网络药理主结果。")
    if not figure_2_lines:
        figure_2_lines.append("- Figure 2：待补充 PPI 或核心靶点结果。")
    if not supplementary_lines:
        supplementary_lines.append("- Supplementary Figure 1：待补充富集分析相关结果。")

    return f"""## Results 段落初稿

### Figure 1 结果段
{chr(10).join(figure_1_lines)}

**结果段模板**
Network pharmacology analysis first identified the shared targets among compound-associated targets, disease-related genes, and differentially expressed genes. The component-target network further demonstrated the multi-component and multi-target characteristics of {project_name}.

### Figure 2 结果段
{chr(10).join(figure_2_lines)}

**结果段模板**
To further identify the key regulatory targets, a PPI network was constructed based on the shared targets. Several hub genes with higher centrality were highlighted, suggesting their potential importance in the therapeutic mechanism.

### Supplementary Figure 1 结果段
{chr(10).join(supplementary_lines)}

**结果段模板**
Functional enrichment analyses revealed that the shared targets were mainly involved in biological processes and signaling pathways associated with the disease mechanism, providing a basis for subsequent validation experiments.
"""


def build_network_discussion_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    pathway_terms = []
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        pathway_terms.append("关键信号通路富集结果")
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        pathway_terms.append("生物过程富集结果")
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        pathway_terms.append("核心靶点互作关系")
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        pathway_terms.append("多成分-多靶点调控特征")

    mechanism_summary = "、".join(pathway_terms) if pathway_terms else "网络药理分析结果"

    return f"""## Discussion 过渡与机制解释草稿

### Discussion 过渡句
- The network pharmacology results provided a systems-level overview of the potential therapeutic mechanism of {project_name} against {disease_name}.
- These findings linked the shared targets, hub genes, and enriched pathways into a coherent mechanistic framework for subsequent validation.

### 机制解释句
- The identified hub targets and enriched pathways suggest that {project_name} may exert therapeutic effects through {mechanism_summary}.
- The multi-component and multi-target characteristics are consistent with the pharmacological features commonly observed in complex natural-product interventions.

### 与文献衔接句
- These observations are broadly in line with previous studies reporting that oxidative stress, inflammation, apoptosis, or related signaling pathways are central to the pathogenesis of {disease_name}.
- Therefore, the present network pharmacology results offer a reasonable basis for selecting key targets and pathways for downstream docking and experimental validation.

### 实验验证承接句
- Based on these findings, the next step is to prioritize hub targets and representative pathways for molecular docking and wet-lab verification.
- The enriched pathways and hub genes can be further examined by WB, RT-qPCR, IF, or other functional assays in the selected disease model.
"""


def build_network_validation_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    has_ppi = any(item["name"] == "PPI 网络图" for item in recommendations)
    has_hub = any(item["name"] == "核心靶点柱状图" for item in recommendations)
    has_kegg = any(item["name"] == "KEGG 气泡图" for item in recommendations)
    has_go = any(item["name"] == "GO 气泡图" for item in recommendations)
    has_component = any(item["name"] == "成分-靶点网络图" for item in recommendations)

    docking_lines = []
    wb_lines = []
    qpcr_lines = []
    functional_lines = []

    if has_ppi or has_hub:
        docking_lines.append("- 优先选择 3-5 个核心靶点进入分子对接，优先考虑 PPI 或中心性排序靠前的候选基因。")
        wb_lines.append("- WB：建议先验证核心靶点蛋白及其磷酸化状态或上下游蛋白表达变化。")
        qpcr_lines.append("- qPCR：建议检测核心靶点基因及关键下游效应基因的转录水平。")

    if has_kegg:
        docking_lines.append("- 若 KEGG 富集到代表性通路，优先选择该通路中的关键靶点作为 docking 候选。")
        wb_lines.append("- WB：补充代表性通路蛋白，例如通路总蛋白、活化蛋白和终末效应蛋白。")
        qpcr_lines.append("- qPCR：补充该通路相关基因以及凋亡、炎症或氧化应激相关基因。")

    if has_go:
        functional_lines.append("- 根据 GO 富集结果，补做与氧化应激、炎症、凋亡或线粒体功能相关的功能实验。")

    if has_component:
        docking_lines.append(f"- 从 {project_name} 的关键活性成分中挑选 2-3 个代表性化合物，与核心靶点进行对接。")

    if not docking_lines:
        docking_lines.append("- 当前建议先完成交集靶点和富集结果整理，再筛选 docking 候选。")
    if not wb_lines:
        wb_lines.append("- 当前建议先根据核心靶点和通路结果，确定 2-4 个优先验证蛋白。")
    if not qpcr_lines:
        qpcr_lines.append("- 当前建议先围绕核心靶点和关键通路，选择 3-6 个候选基因进行 qPCR。")
    if not functional_lines:
        functional_lines.append(f"- 围绕 {disease_name} 相关表型，补充 1-2 项功能性验证实验。")

    return f"""## Docking / WB / qPCR 验证建议

### Docking 候选建议
{chr(10).join(docking_lines)}

### WB 验证建议
{chr(10).join(wb_lines)}

### qPCR 验证建议
{chr(10).join(qpcr_lines)}

### 功能实验建议
{chr(10).join(functional_lines)}

### 推荐验证顺序
- 先完成 docking 候选筛选
- 再确定 WB / qPCR 核心指标
- 最后补功能实验，用于支撑机制解释
"""


def build_network_experiment_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    has_kegg = any(item["name"] == "KEGG 气泡图" for item in recommendations)
    has_go = any(item["name"] == "GO 气泡图" for item in recommendations)
    has_ppi = any(item["name"] == "PPI 网络图" for item in recommendations)
    has_component = any(item["name"] == "成分-靶点网络图" for item in recommendations)

    marker_lines = []
    grouping_lines = [
        "- Control 组：正常处理或空白对照。",
        f"- Model 组：{disease_name} 模型组。",
        f"- Treatment-Low 组：{project_name} 低剂量组。",
        f"- Treatment-High 组：{project_name} 高剂量组。",
        "- Positive control 组：阳性药或经典通路抑制剂/激动剂组。",
    ]
    assay_lines = []

    if has_ppi:
        marker_lines.append("- 核心靶点：优先纳入 PPI 中心性较高的 2-4 个候选靶点。")
    if has_component:
        marker_lines.append("- 关键成分：优先围绕网络中连接度较高的代表性活性成分设计验证。")
    if has_kegg:
        marker_lines.append("- 通路蛋白：优先纳入富集到代表性 KEGG 通路的关键蛋白。")
    if has_go:
        marker_lines.append("- 功能指标：根据 GO 结果补充氧化应激、炎症、凋亡或线粒体功能指标。")

    if not marker_lines:
        marker_lines.append("- 建议先确定 2-3 个核心靶点和 1-2 条关键通路，再细化验证指标。")

    assay_lines.extend([
        "- CCK-8 / 活力检测：评估整体保护或抑制效应。",
        "- WB：检测核心靶点蛋白、通路蛋白及活化状态。",
        "- qPCR：检测核心靶点和下游效应基因。",
    ])

    if has_go:
        assay_lines.extend([
            "- ROS / SOD / MDA / GSH-Px：如 GO 指向氧化应激，可优先补这些指标。",
            "- Annexin V 或 TUNEL：如结果指向凋亡，可补细胞凋亡验证。",
        ])

    if has_kegg:
        assay_lines.append("- IF / 免疫荧光：可用于观察关键通路蛋白定位或表达变化。")

    return f"""## 实验分组建议 + 指标清单

### 建议实验分组
{chr(10).join(grouping_lines)}

### 建议优先验证指标
{chr(10).join(marker_lines)}

### 建议实验项目
{chr(10).join(assay_lines)}

### 推荐执行顺序
- 先完成活力或表型初筛
- 再验证核心靶点与关键通路
- 最后补功能性实验，闭合机制证据链
"""




def build_wb_experiment_bundle(project_name: str, disease_name: str):
    return f"""## WB 实验设计总包

### 建议实验分组
- Control 组：正常对照。
- Model 组：{disease_name} 模型组。
- Treatment-Low 组：{project_name} 低剂量组。
- Treatment-High 组：{project_name} 高剂量组。
- Positive control 组：阳性药或经典通路抑制剂 / 激动剂组。

### 建议优先蛋白
- 核心靶点蛋白：
- 通路总蛋白：
- 磷酸化 / 活化蛋白：
- 下游效应蛋白：
- 内参蛋白：GAPDH / beta-actin / Tubulin

### 建议记录信息
- 蛋白提取方式：
- 上样量：
- 胶浓度：
- 一抗孵育条件：
- 二抗孵育条件：
- 曝光参数：

### 灰度分析与统计
- 每组至少 3 个生物重复。
- 先计算目标蛋白 / 内参蛋白比值。
- 磷酸化蛋白建议同时归一化到总蛋白。
- 最终使用均值 ± SD 展示，并记录统计学方法。

### Results 草稿骨架
- Compared with the model group, {project_name} altered the expression of the selected proteins associated with {disease_name}.
- The treatment particularly affected the representative signaling proteins, suggesting regulation of the proposed pathway.
- These WB results provided protein-level evidence supporting the mechanism predicted by the upstream analyses.

### Methods 草稿骨架
Western blot analysis was performed to evaluate the protein-level changes associated with the proposed mechanism of {project_name} against {disease_name}. Total protein was extracted from each group, quantified, separated by SDS-PAGE, and transferred onto PVDF membranes. After blocking, the membranes were incubated with primary antibodies against the selected target proteins and corresponding secondary antibodies. Protein bands were visualized and quantified, and the relative expression levels were normalized to the internal control.
"""


def build_qpcr_experiment_bundle(project_name: str, disease_name: str):
    return f"""## qPCR 实验设计总包

### 建议实验分组
- Control 组：正常对照。
- Model 组：{disease_name} 模型组。
- Treatment-Low 组：{project_name} 低剂量组。
- Treatment-High 组：{project_name} 高剂量组。
- Positive control 组：阳性药或经典通路抑制剂 / 激动剂组。

### 建议优先检测基因
- 核心靶点基因：
- 通路关键基因：
- 凋亡 / 炎症 / 氧化应激相关基因：
- 内参基因：GAPDH / ACTB / 18S rRNA

### 建议记录信息
- RNA 提取试剂：
- RNA 纯度（A260/A280）：
- 逆转录体系：
- 引物序列：
- 扩增体系：
- 反应程序：

### 数据处理与统计
- 建议每组至少 3 个生物重复，技术重复 2-3 次。
- 记录 Ct 值并检查重复孔一致性。
- 使用 2^-ΔΔCt 方法计算相对表达量。
- 最终使用均值 ± SD 展示，并记录统计学方法。

### Results 草稿骨架
- Compared with the model group, {project_name} significantly regulated the mRNA expression of the selected genes related to {disease_name}.
- The transcriptional changes were generally consistent with the predicted targets and pathways.
- These qPCR findings provided gene-level evidence supporting the proposed multi-target mechanism.

### Methods 草稿骨架
RT-qPCR was conducted to determine the transcriptional changes related to the proposed mechanism of {project_name} against {disease_name}. Total RNA was extracted from each group and reverse-transcribed into cDNA. Quantitative PCR was then performed using gene-specific primers, and the relative mRNA expression levels were calculated using the 2^-ΔΔCt method with the selected housekeeping gene as the internal reference.
"""


def build_wb_results_bundle(project_name: str, disease_name: str, target_proteins: str, normalized_data: str):
    return f"""## WB 结果分析总包

### 当前目标蛋白
{target_proteins or "- 待补充目标蛋白"}

### 归一化灰度数据
```text
{normalized_data}
```

### 结果解读骨架
- Compared with the model group, {project_name} altered the protein expression profile associated with {disease_name}.
- The representative targets showed a trend consistent with regulation of the proposed signaling pathway.
- These WB findings provided protein-level support for the hypothesized mechanism.

### Figure Legend 草稿
- Figure X. Effects of {project_name} on the protein expression related to {disease_name}. Representative immunoblots and the corresponding quantitative analysis of normalized gray values are shown for each group. Data are presented as mean ± SD.

### 统计检查清单
- [ ] 是否完成目标蛋白 / 内参蛋白归一化
- [ ] 磷酸化蛋白是否同时归一化到总蛋白
- [ ] 是否至少完成 3 个生物重复
- [ ] 是否补充统计学方法和显著性标记

### Results 可直接扩写句
- The expression of the selected proteins was markedly dysregulated in the model group relative to the control group.
- Treatment with {project_name} partially or significantly reversed these changes, indicating modulation of the corresponding pathway.
"""


def build_qpcr_results_bundle(project_name: str, disease_name: str, target_genes: str, ddct_data: str):
    return f"""## qPCR 结果分析总包

### 当前目标基因
{target_genes or "- 待补充目标基因"}

### 2^-ΔΔCt 数据
```text
{ddct_data}
```

### 结果解读骨架
- Compared with the model group, {project_name} regulated the mRNA expression of the selected genes associated with {disease_name}.
- The transcriptional changes were broadly in line with the predicted targets and pathways.
- These qPCR results provided gene-level support for the proposed mechanism.

### Figure Legend 草稿
- Figure X. Effects of {project_name} on the mRNA expression related to {disease_name}. Relative expression levels were calculated using the 2^-ΔΔCt method and are presented as mean ± SD.

### 统计检查清单
- [ ] 是否完成 Ct 质控
- [ ] 是否完成 2^-ΔΔCt 计算
- [ ] 是否至少完成 3 个生物重复
- [ ] 是否补充统计学方法和显著性标记

### Results 可直接扩写句
- The expression levels of the selected genes were significantly altered in the model group compared with the control group.
- Treatment with {project_name} reversed or attenuated these transcriptional changes, supporting regulation of the proposed pathway.
"""


def build_wb_full_draft_bundle(
    project_name: str,
    disease_name: str,
    sample_type: str,
    target_proteins: str,
    groups: str,
    antibodies: str,
    normalized_data: str,
):
    return f"""# WB Results + Methods 初稿

## 实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- 样本类型：{sample_type or "- 待补充"}

## 目标蛋白
{target_proteins or "- 待补充目标蛋白"}

## 分组信息
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

## 抗体信息
```text
{antibodies or "待补充抗体名称、货号和稀释比例"}
```

## 归一化灰度数据
```text
{normalized_data or "Protein\tControl\tModel\tTreatment-Low\tTreatment-High"}
```

{build_wb_results_bundle(project_name, disease_name, target_proteins, normalized_data)}

## Results 初稿
Western blot analysis was performed to evaluate the protein-level changes associated with {disease_name}. Compared with the control group, the model group showed an abnormal expression pattern of the selected proteins. Treatment with {project_name} partially or markedly reversed these alterations, suggesting that the intervention modulated the corresponding signaling pathway at the protein level.

## Methods 初稿
Protein samples were prepared from {sample_type or "the indicated samples"} in each experimental group. Equal amounts of protein were separated by SDS-PAGE and transferred onto PVDF membranes. After blocking, the membranes were incubated with the primary antibodies against {target_proteins or "the selected targets"} followed by the corresponding secondary antibodies. The protein bands were visualized using a chemiluminescence system, and the gray values were quantified with image analysis software. Relative protein expression levels were normalized to the internal reference protein, and when necessary, phosphorylated proteins were additionally normalized to their corresponding total proteins.

## Figure Legend 初稿
- Figure X. Effects of {project_name} on protein expression associated with {disease_name}. Representative immunoblots and quantitative analysis of normalized gray values are shown for each group.

## 下一步清单
- [ ] 补齐原始条带图
- [ ] 确认统计学检验
- [ ] 写入主文 Results
- [ ] 与 qPCR 结果进行联合讨论
"""


def build_qpcr_full_draft_bundle(
    project_name: str,
    disease_name: str,
    sample_type: str,
    target_genes: str,
    groups: str,
    primers: str,
    ddct_data: str,
):
    return f"""# qPCR Results + Methods 初稿

## 实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- 样本类型：{sample_type or "- 待补充"}

## 目标基因
{target_genes or "- 待补充目标基因"}

## 分组信息
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

## 引物信息
```text
{primers or "待补充引物序列与内参基因"}
```

## 2^-ΔΔCt 数据
```text
{ddct_data or "Gene\tControl\tModel\tTreatment-Low\tTreatment-High"}
```

{build_qpcr_results_bundle(project_name, disease_name, target_genes, ddct_data)}

## Results 初稿
RT-qPCR analysis was conducted to determine the transcriptional changes related to {disease_name}. Relative to the control group, the model group exhibited dysregulated mRNA expression of the selected genes. Treatment with {project_name} reversed or attenuated these transcriptional abnormalities, supporting the involvement of the proposed targets and pathways at the gene-expression level.

## Methods 初稿
Total RNA was extracted from {sample_type or "the indicated samples"} in each group and reverse-transcribed into cDNA according to the manufacturer's protocol. Quantitative PCR was then performed using gene-specific primers for {target_genes or "the selected genes"}, with the designated housekeeping gene as the internal reference. Relative mRNA expression was calculated using the 2^-ΔΔCt method, and the data were presented as mean ± SD.

## Figure Legend 初稿
- Figure X. Effects of {project_name} on mRNA expression associated with {disease_name}. Relative expression levels of the selected genes were calculated using the 2^-ΔΔCt method.

## 下一步清单
- [ ] 补齐 Ct 原始值表
- [ ] 确认引物与内参信息
- [ ] 写入主文 Results
- [ ] 与 WB 结果进行联合讨论
"""


def build_qpcr_ct_qc_bundle(
    project_name: str,
    disease_name: str,
    housekeeping_gene: str,
    raw_ct_data: str,
):
    return f"""## qPCR Ct 质控与 2^-ΔΔCt 计算包

### 内参基因
- {housekeeping_gene or "GAPDH / ACTB / 待补充"}

### 原始 Ct 数据模板
```text
{raw_ct_data or "Gene\tGroup\tRep1\tRep2\tRep3\tMean Ct\tSD\tCV%"}
```

### 质控建议
- 每个基因先检查 3 个重复孔的一致性。
- 一般建议 SD 不明显偏大，异常重复孔要单独标记。
- 先检查内参基因在各组间是否稳定。
- 熔解曲线若出现异常峰，需要回看引物特异性和扩增体系。

### 2^-ΔΔCt 计算模板
```text
Gene\tGroup\tCt(target)\tCt(reference)\tΔCt\tΔΔCt\t2^-ΔΔCt
```

### 结果解释骨架
- The raw Ct values were first quality-checked to ensure acceptable consistency among technical replicates.
- The relative expression levels were then calculated using the 2^-ΔΔCt method with {housekeeping_gene or "the selected housekeeping gene"} as the internal reference.
- Only data passing the predefined quality-control criteria were included in the final statistical analysis.

### Supplementary 建议
- Supplementary Table：Raw Ct values for each replicate
- Supplementary Table：2^-ΔΔCt calculation sheet
- Supplementary Figure：Melting-curve or amplification QC summary if needed

### 核对清单
- [ ] 是否补齐所有重复孔原始 Ct 值
- [ ] 是否标记异常孔和剔除原因
- [ ] 是否确认内参基因稳定
- [ ] 是否保存完整 2^-ΔΔCt 计算表
"""


def build_qpcr_stats_package_bundle(
    project_name: str,
    disease_name: str,
    target_genes: str,
    ddct_data: str,
    stats_summary: str,
):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(limit=12)
    qpcr_legend_block = build_qpcr_supplementary_legend_section(limit=12)
    return f"""## qPCR 统计表与补充材料包

### 目标基因
{target_genes or "- 待补充目标基因"}

### 相对表达结果
```text
{ddct_data or "Gene\tControl\tModel\tTreatment-Low\tTreatment-High\tP value\tSignificance"}
```

### 统计结果汇总
```text
{stats_summary or "Gene\tTest\tP value\tPost hoc\tInterpretation"}
```

### 主文表格模板
#### Table X. Summary of qPCR validation results for {project_name} against {disease_name}
```text
Gene\tControl (mean ± SD)\tModel (mean ± SD)\tTreatment-Low (mean ± SD)\tTreatment-High (mean ± SD)\tP value\tSignificance
```

### Supplementary 建议清单
- Supplementary Table S1：Primer information
- Supplementary Table S2：Raw Ct values
- Supplementary Table S3：2^-ΔΔCt calculation sheet
- Supplementary Table S4：Statistics summary used for plotting

### Results 句库
- RT-qPCR analysis showed that the selected genes were significantly dysregulated in the model group.
- Treatment with {project_name} reversed or attenuated these transcriptional alterations.
- These data provided gene-level support for the proposed mechanism of {project_name} against {disease_name}.

### 核对清单
- [ ] 是否补齐统计检验方法
- [ ] 是否补齐均值、SD 和显著性标记
- [ ] 是否保证正文、图和表的数值一致
- [ ] 是否把原始 Ct 值和计算表放入 Supplementary

{qpcr_registry_block}

{qpcr_legend_block}
"""


def build_qpcr_reviewer_bundle(
    project_name: str,
    disease_name: str,
    reviewer_comment: str,
    target_genes: str,
):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(
        limit=12,
        heading="qPCR 图片自动编号清单",
    )
    qpcr_legend_block = build_qpcr_supplementary_legend_section(limit=12)
    return f"""## qPCR 原始数据审稿答复稿

### Reviewer Comment
{reviewer_comment or "Please provide the raw qPCR data, primer information, and calculation details."}

### Response Draft
We thank the reviewer for this valuable comment. In response, we have carefully reorganized the qPCR validation materials associated with {project_name} against {disease_name}. Specifically, the primer information, raw Ct values, replicate-level records, and the complete 2^-ΔΔCt calculation sheets have been checked and compiled. These files are now available in the revised supplementary materials to improve transparency and reproducibility.

### 涉及目标基因
{target_genes or "- 待补充 qPCR 目标基因"}

### 建议补充到 Supplementary 的项目
- Supplementary Table：Primer sequences
- Supplementary Table：Raw Ct values for each replicate
- Supplementary Table：2^-ΔΔCt calculation sheet
- Supplementary Figure：Amplification / melting-curve QC if required

### 可直接使用的回复句
- We have now provided the complete primer information used for the qPCR assays.
- The raw Ct values for each replicate and the corresponding 2^-ΔΔCt calculation sheet have been added to the Supplementary Materials.
- The related qPCR quality-control images were reorganized and renumbered as supplementary figures, and the corresponding figure legends were prepared for the revised submission.
- These additions do not change the conclusions of the manuscript but improve the transparency of the validation workflow.

{qpcr_registry_block}

{qpcr_legend_block}

### 核对清单
- [ ] 是否补齐引物序列
- [ ] 是否补齐原始 Ct 值
- [ ] 是否补齐 2^-ΔΔCt 计算表
- [ ] 是否在回复信中标明对应 Supplementary 编号
"""


def build_qpcr_mapping_bundle(
    project_name: str,
    disease_name: str,
    main_figures: str,
    supp_figures: str,
    main_tables: str,
    supp_tables: str,
):
    supp_figures_block = supp_figures or build_qpcr_supplementary_mapping_text(limit=12)
    qpcr_bilingual_legend_block = build_qpcr_supplementary_bilingual_legend_section(limit=12)
    return f"""## qPCR 图表编号映射包

### Main Figures
```text
{main_figures or "Figure X\tqPCR relative expression bar plot"}
```

### Supplementary Figures
```text
{supp_figures_block}
```

### Main Tables
```text
{main_tables or "Table X\tqPCR statistics summary"}
```

### Supplementary Tables
```text
{supp_tables or "Supplementary Table S1\tPrimer information\nSupplementary Table S2\tRaw Ct values\nSupplementary Table S3\t2^-ΔΔCt calculation sheet"}
```

### 编号建议
- 主文 Figure 只保留最核心的相对表达图。
- 主文 Table 放统计汇总即可。
- Supplementary 负责承载引物、原始 Ct、计算表和 QC 图。

### 说明句模板
- The main text presents the relative expression changes of the selected genes, while the primer details, raw Ct values, and full 2^-ΔΔCt calculation sheets are provided in the Supplementary Materials.

{qpcr_bilingual_legend_block}

### 核对清单
- [ ] 主文与补充材料编号是否连续
- [ ] qPCR 图、表、Supplementary 是否一一对应
- [ ] 正文首次引用的编号是否正确
"""


def build_qpcr_full_package_bundle(
    project_name: str,
    disease_name: str,
    sample_type: str,
    target_genes: str,
    groups: str,
    primers: str,
    raw_ct_data: str,
    ddct_data: str,
    stats_summary: str,
):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(limit=12)
    qpcr_legend_block = build_qpcr_supplementary_legend_section(limit=12)
    return f"""## qPCR 投稿级全包

### 实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- 样本类型：{sample_type or "- 待补充"}

### 分组设计
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

### 目标基因
{target_genes or "- 待补充目标基因"}

### 引物信息
```text
{primers or "Gene\tForward primer\tReverse primer\tProduct size"}
```

### 原始 Ct 数据
```text
{raw_ct_data or "Gene\tGroup\tRep1\tRep2\tRep3\tMean Ct\tSD"}
```

### 2^-ΔΔCt 数据
```text
{ddct_data or "Gene\tControl\tModel\tTreatment-Low\tTreatment-High"}
```

### 统计汇总
```text
{stats_summary or "Gene\tP value\tPost hoc\tInterpretation"}
```

{build_qpcr_results_bundle(project_name, disease_name, target_genes, ddct_data)}

### Results 初稿
RT-qPCR was performed to evaluate the transcriptional changes associated with {disease_name}. Compared with the control group, the model group displayed dysregulated expression of the selected genes. Treatment with {project_name} reversed or attenuated these changes, thereby supporting the proposed targets and pathways at the gene-expression level.

### Methods 初稿
Total RNA was extracted from {sample_type or "the indicated samples"} in each group and reverse-transcribed into cDNA according to the manufacturer's protocol. Quantitative PCR was then performed using gene-specific primers for {target_genes or "the selected genes"}, with the designated housekeeping gene as the internal reference. Relative mRNA expression was calculated using the 2^-ΔΔCt method, and the data were presented as mean ± SD. Only replicate sets passing the quality-control criteria were included in the final analysis.

### Figure Legend 初稿
- Figure X. Effects of {project_name} on mRNA expression associated with {disease_name}. Relative expression levels of the selected genes were calculated using the 2^-ΔΔCt method and are presented as mean ± SD.

### Supplementary 建议
- Supplementary Table S1：Primer information
- Supplementary Table S2：Raw Ct values
- Supplementary Table S3：2^-ΔΔCt calculation sheet
- Supplementary Table S4：Statistics summary
- Supplementary Figure S1：qPCR QC / melting-curve summary if needed

### 投稿前核对
- [ ] 引物、原始 Ct 值、2^-ΔΔCt 表是否齐全
- [ ] 统计检验与显著性标记是否统一
- [ ] Results、Figure、Supplementary 是否完全对应
- [ ] 是否可直接并入 WB / qPCR 联合验证总稿

{qpcr_registry_block}

{qpcr_legend_block}
"""


def build_qpcr_group_stats_template_bundle(
    project_name: str,
    disease_name: str,
    target_genes: str,
    groups: str,
):
    return f"""## qPCR 分组统计表模板

### 实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}

### 目标基因
{target_genes or "- 待补充目标基因"}

### 分组设计
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

### 统计主表模板
```text
Gene\tGroup\tMean\tSD\tN\tP value\tPost hoc\tSignificance
AKT1\tControl
AKT1\tModel
AKT1\tTreatment-Low
AKT1\tTreatment-High
```

### 推荐统计说明
- 如果只有两组，优先整理 t test 结果。
- 如果多组比较，优先整理 one-way ANOVA + post hoc。
- 结果稿中只保留最终用于出图的均值、SD、P 值和显著性标记。

### Results 句式模板
- The relative mRNA expression levels were compared among the experimental groups.
- Statistical analysis showed that the model group exhibited a significant change relative to the control group.
- Treatment with {project_name} partially or significantly reversed the transcriptional alterations of the selected genes.

### 核对清单
- [ ] 是否写清统计方法
- [ ] 是否补齐均值、SD 和 n
- [ ] 是否统一显著性符号
- [ ] 是否与 Figure 和 Supplementary 数值一致
"""


def build_qpcr_primer_table_bundle(project_name: str):
    return f"""## qPCR 引物信息标准表

### Primer Table 模板
```text
Gene\tForward primer (5'-3')\tReverse primer (5'-3')\tProduct size (bp)\tAnnealing temperature\tReference
GAPDH
ACTB
AKT1
NFE2L2
HMOX1
BAX
BCL2
CASP3
```

### 填写说明
- Forward / Reverse primer 建议统一大写字母格式。
- Product size、退火温度和来源文献尽量一起补齐。
- 内参基因单独标记，避免后续正文与 Supplementary 混乱。

### 推荐 Supplementary 放置方式
- Supplementary Table S1：Primer information used for RT-qPCR in {project_name}

### 核对清单
- [ ] 引物序列方向是否正确
- [ ] 基因名是否与正文一致
- [ ] 内参基因是否明确标注
- [ ] 是否补齐产物长度和退火温度
"""


def build_qpcr_primer_design_bundle(
    project_name: str,
    species: str,
    target_genes: str,
    housekeeping_gene: str,
    amplicon_range: str,
    tm_range: str,
    gc_range: str,
):
    return f"""## qPCR 引物设计建议包

### 项目背景
- 项目：{project_name}
- 物种 / 样本来源：{species or "待补充"}
- 目标基因：{target_genes or "待补充"}
- 内参基因：{housekeeping_gene or "待补充"}

### 推荐设计原则
- 扩增产物长度建议控制在 {amplicon_range or "80-200 bp"}。
- 引物退火温度建议控制在 {tm_range or "58-62°C"}，同一对引物的 Tm 尽量接近。
- GC 含量建议控制在 {gc_range or "40%-60%"}。
- 优先跨越外显子连接区，减少基因组 DNA 干扰。
- 避免连续同碱基、明显发卡结构和引物二聚体风险。
- 建议同时准备 NCBI / Primer-BLAST 验证结果截图或编号。

### Primer Table 设计模板
```text
Gene\tForward primer (5'-3')\tReverse primer (5'-3')\tProduct size (bp)\tTm (°C)\tGC%\tExon junction\tSpecificity check\tRemark
{housekeeping_gene or "GAPDH"}
AKT1
NFE2L2
HMOX1
BAX
BCL2
CASP3
```

### 实验前核对
- [ ] 是否确认基因名与物种一致
- [ ] 是否确认序列方向为 5'-3'
- [ ] 是否完成 Primer-BLAST 特异性验证
- [ ] 是否确认产物长度适合 qPCR
- [ ] 是否给出内参基因选择理由

### Methods 句式模板
- Primers for RT-qPCR were designed according to the target transcript sequences and validated for specificity before use.
- The expected amplicon sizes ranged from {amplicon_range or "80 to 200 bp"}, and the melting temperatures were controlled within {tm_range or "the recommended range"}.

### Supplementary 建议
- Supplementary Table S1：Primer sequences, expected amplicon size, Tm and validation notes.
"""


def build_qpcr_curve_interpretation_bundle(
    project_name: str,
    target_genes: str,
    amplification_notes: str,
    melting_notes: str,
    ntc_status: str,
    efficiency_notes: str,
):
    return f"""## qPCR 图谱讲解与结果解读包

### 目标基因
{target_genes or "待补充目标基因"}

### 需要解读的图谱
1. 扩增曲线（Amplification plot）
2. 熔解曲线（Melting curve）
3. 相对表达柱状图 / 散点图

### 扩增曲线讲解模板
- 理想状态：指数期清晰、平台期稳定、重复孔曲线彼此接近。
- 当前记录：
{amplification_notes or "- 待补充扩增曲线观察结果"}
- 结果判断：
  - 如果重复孔起跳位置差异较大，提示移液或模板一致性问题。
  - 如果背景波动明显，提示基线设置或反应体系稳定性问题。

### 熔解曲线讲解模板
- 理想状态：单一尖锐峰，峰位稳定，无明显肩峰或杂峰。
- 当前记录：
{melting_notes or "- 待补充熔解曲线观察结果"}
- 结果判断：
  - 单峰通常支持扩增特异性较好。
  - 多峰、肩峰或低温小峰常提示非特异扩增或引物二聚体。

### NTC / 阴性对照说明
- 当前情况：{ntc_status or "待补充"}
- 标准解释：
  - NTC 无扩增或极晚期扩增，通常可接受。
  - NTC 明显扩增时，应优先排查污染或引物二聚体。

### 扩增效率与稳定性说明
- 当前记录：{efficiency_notes or "待补充"}
- 推荐补充：
  - 标准曲线斜率
  - 扩增效率（90%-110% 为常见可接受范围）
  - R² 是否接近 1

### Figure Legend / 结果段讲解句式
- The amplification plots showed consistent exponential amplification across technical replicates.
- The melting curves exhibited a single dominant peak for the selected genes, supporting acceptable amplification specificity.
- The relative mRNA expression data were interpreted together with the amplification and melting profiles to ensure data reliability.

### 出图配套建议
- Supplementary Figure：Amplification and melting-curve quality-control panel.
- Main Figure：Relative expression bar chart with mean ± SD and significance marks.
"""


def build_qpcr_error_analysis_bundle(
    project_name: str,
    disease_name: str,
    issue_summary: str,
    raw_ct_pattern: str,
    possible_causes: str,
    corrective_actions: str,
):
    return f"""## qPCR 误差分析与排错包

### 项目背景
- 项目：{project_name}
- 疾病 / 模型：{disease_name}

### 当前问题概述
{issue_summary or "- 待补充"}

### 原始 Ct 异常模式
{raw_ct_pattern or "- 待补充，如：重复孔差值 > 0.5 / NTC 扩增 / 内参波动过大"}

### 常见误差来源排查表
```text
问题类型\t可能表现\t优先排查
移液误差\t重复孔 Ct 差异大\t枪头、操作节奏、混匀
模板质量差\t整体 Ct 偏高或波动大\tRNA 完整性、浓度、纯度
逆转录不稳定\t不同样本整体偏移\t逆转录体系、酶失活、操作时间
引物问题\t多峰、效率低\t二聚体、特异性、Tm 不合适
污染\tNTC 扩增\t体系污染、模板交叉污染
内参不稳定\tΔCt 波动大\t内参选择不合适
```

### 当前推测原因
{possible_causes or "- 待补充"}

### 建议纠正措施
{corrective_actions or "- 待补充"}

### 误差分析写作模板
- The raw Ct data were reviewed before formal statistical analysis.
- Samples or replicate sets with unacceptable amplification consistency were rechecked and flagged during quality control.
- Potential sources of technical variation, including pipetting inconsistency, template quality, and primer specificity, were considered during data interpretation.

### 复测建议
- [ ] 是否需要补做 RNA 质检
- [ ] 是否需要重做逆转录
- [ ] 是否需要更换引物
- [ ] 是否需要替换内参基因
- [ ] 是否需要剔除异常重复孔并记录依据
"""


def build_qpcr_ai_results_prompt(
    project_name: str,
    disease_name: str,
    target_genes: str,
    groups: str,
    ddct_data: str,
    stats_summary: str,
):
    system_prompt = (
        "你是生物医药科研 qPCR 数据解读助手。"
        "必须严格基于用户提供的数据，不得虚构。"
        "请只输出合法 JSON，字段包括：overall_judgment,key_findings,gene_by_gene_interpretation,"
        "results_paragraph,figure_legend,discussion_points,risk_notes,next_steps。"
    )
    user_prompt = f"""项目：{project_name}
疾病/模型：{disease_name}
目标基因：{target_genes}
实验分组：{groups}

2^-ΔΔCt 数据：
{ddct_data}

统计结果：
{stats_summary}

请输出：
1. 总体判断
2. 关键发现
3. 按基因逐条解释
4. 可直接用于论文的 Results 段
5. Figure legend 草稿
6. 可写进 Discussion 的点
7. 风险与保守解释
8. 下一步建议
"""
    return system_prompt, user_prompt


def build_qpcr_ai_curve_prompt(
    project_name: str,
    disease_name: str,
    target_genes: str,
    amplification_notes: str,
    melting_notes: str,
    ntc_status: str,
    efficiency_notes: str,
):
    system_prompt = (
        "你是生物医药科研 qPCR 图谱讲解助手。"
        "必须严格基于提供的图谱观察记录进行解释，不得虚构未提供的实验事实。"
        "请只输出合法 JSON，字段包括：curve_judgment,amplification_interpretation,melting_interpretation,"
        "ntc_interpretation,efficiency_interpretation,figure_caption,methods_qc_sentence,risk_notes,next_steps。"
    )
    user_prompt = f"""项目：{project_name}
疾病/模型：{disease_name}
目标基因：{target_genes}

扩增曲线观察：
{amplification_notes}

熔解曲线观察：
{melting_notes}

NTC 情况：
{ntc_status}

扩增效率/标准曲线备注：
{efficiency_notes}

请输出：
1. 图谱总体判断
2. 扩增曲线解释
3. 熔解曲线解释
4. NTC 解释
5. 扩增效率解释
6. Figure caption 草稿
7. Methods 里的质控句式
8. 风险提示
9. 下一步建议
"""
    return system_prompt, user_prompt


def build_qpcr_ai_error_prompt(
    project_name: str,
    disease_name: str,
    issue_summary: str,
    raw_ct_pattern: str,
    possible_causes: str,
    corrective_actions: str,
):
    system_prompt = (
        "你是生物医药科研 qPCR 误差诊断助手。"
        "必须严格基于用户提供的问题现象进行排查分析，不得虚构。"
        "请只输出合法 JSON，字段包括：problem_summary,most_likely_causes,cause_ranking,"
        "diagnostic_reasoning,corrective_plan,can_use_current_data,retest_priority,writing_note,next_steps。"
    )
    user_prompt = f"""项目：{project_name}
疾病/模型：{disease_name}

当前问题概述：
{issue_summary}

原始 Ct 异常模式：
{raw_ct_pattern}

已怀疑原因：
{possible_causes}

已考虑纠正措施：
{corrective_actions}

请输出：
1. 问题总结
2. 最可能原因
3. 原因排序
4. 诊断逻辑
5. 纠正方案
6. 当前数据是否还可用于结果展示
7. 哪些样本/步骤应优先复测
8. 写进实验记录的说明
9. 下一步建议
"""
    return system_prompt, user_prompt


def build_qpcr_image_writeback_prompt(
    project_name: str,
    disease_name: str,
    image_type: str,
    observation: str,
):
    system_prompt = (
        "你是生物医药科研写作助手。"
        "必须严格基于提供的图片类型和人工观察记录，不得虚构未提供的实验事实。"
        "请只输出合法 JSON，字段包括：results_sentence,supplementary_figure_legend,main_text_note,discussion_note,risk_note。"
    )
    user_prompt = f"""项目：{project_name}
疾病/模型：{disease_name}
图片类型：{image_type}
人工观察：
{observation}

请输出：
1. 可直接用于 Results 的句子
2. Supplementary Figure Legend 草稿
3. 正文中如何引用这张图的备注
4. 可写进 Discussion 的一句提醒
5. 风险与保守表述
"""
    return system_prompt, user_prompt


def format_ai_analysis_markdown(title: str, ai_result: dict):
    if ai_result.get("status") == "not_configured":
        return f"""# {title}

## AI 状态
未配置 AI API。

## 可复制提示词
```text
{ai_result.get("prompt", "")}
```
"""

    if ai_result.get("status") == "error":
        return f"""# {title}

## AI 状态
调用失败：{ai_result.get("error", "")}

## 可复制提示词
```text
{ai_result.get("prompt", "")}
```
"""

    if ai_result.get("status") == "raw":
        return f"""# {title}

## AI 原始输出
{ai_result.get("raw", "")}
"""

    blocks = [f"# {title}", "", "## AI 结构化结果", ""]
    for key, value in ai_result.items():
        blocks.append(f"### {key}")
        if isinstance(value, list):
            if value:
                blocks.extend([f"- {item}" for item in value])
            else:
                blocks.append("-")
        elif isinstance(value, dict):
            blocks.append("```json")
            blocks.append(json.dumps(value, ensure_ascii=False, indent=2))
            blocks.append("```")
        else:
            blocks.append(str(value))
        blocks.append("")
    return "\n".join(blocks).strip() + "\n"


def build_molecular_validation_summary(current_project: dict):
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    return f"""## 分子验证中心说明
- 当前项目：{project_name}
- 疾病 / 模型：{disease_name}
- 本中心统一管理 WB、qPCR 及二者联合验证的记录、结果、图表、Supplementary 与投稿稿件。

### 推荐流程
1. 先整理 qPCR / WB 原始记录。
2. 再完成 qPCR Ct 质控、WB 灰度统计。
3. 输出各自 Results + Methods 初稿。
4. 再生成 WB / qPCR 联合验证总包，用于正文与投稿材料。
"""


def build_wb_qpcr_package_bundle(
    project_name: str,
    disease_name: str,
    target_proteins: str,
    target_genes: str,
    wb_data: str,
    qpcr_data: str,
):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(
        limit=12,
        heading="qPCR 图片 Supplementary Figure 自动编号",
    )
    qpcr_legend_block = build_qpcr_supplementary_legend_section(limit=12)
    wb_targets = target_proteins or "- 待补充 WB 目标蛋白"
    qpcr_targets = target_genes or "- 待补充 qPCR 目标基因"
    wb_block = wb_data or "Protein\tControl\tModel\tTreatment-Low\tTreatment-High"
    qpcr_block = qpcr_data or "Gene\tControl\tModel\tTreatment-Low\tTreatment-High"

    return f"""## WB / qPCR 标准写作整合包

### 一、标准 Figure Legend 清单
- Figure X. Effects of {project_name} on the protein expression related to {disease_name}. Representative immunoblots and normalized gray-value quantification are shown for the indicated proteins. Data are presented as mean ± SD.
- Figure Y. Effects of {project_name} on the mRNA expression related to {disease_name}. Relative expression levels were calculated using the 2^-ΔΔCt method and are presented as mean ± SD.
- Supplementary Figure S1. Full-length immunoblot images for the proteins analyzed in this study.
- Supplementary Figure S2. Raw Ct value summary and primer information for the qPCR assays.

### 二、目标清单
#### WB 目标蛋白
{wb_targets}

#### qPCR 目标基因
{qpcr_targets}

### 三、原始结果摘要
#### WB 归一化数据
```text
{wb_block}
```

#### qPCR 相对表达数据
```text
{qpcr_block}
```

### 四、合并 Results 段骨架
Compared with the model group, {project_name} modulated both the protein and mRNA expression profiles associated with {disease_name}. At the protein level, the representative targets showed an overall trend consistent with regulation of the proposed signaling pathway. At the transcriptional level, the selected genes were also significantly altered after treatment, and these changes were broadly in line with the predicted targets and pathways. Taken together, the combined WB and qPCR findings provided convergent wet-lab evidence supporting the proposed mechanism of {project_name} against {disease_name}.

### 五、分段 Results 句库
- WB results showed that the expression of the selected proteins was markedly dysregulated in the model group relative to the control group.
- Treatment with {project_name} partially or significantly reversed these protein changes, indicating modulation of the corresponding pathway.
- qPCR results demonstrated that the mRNA expression levels of the selected genes were also altered in response to treatment.
- The consistency between the transcriptional and protein-level findings strengthened the biological interpretation of the proposed mechanism.

### 六、Supplementary 原始数据清单
- Supplementary Table S1：Primary antibody information, including supplier, catalog number, host species, and dilution ratio.
- Supplementary Table S2：Primer sequences used for qPCR, including forward and reverse primers.
- Supplementary Table S3：Raw WB gray values before normalization.
- Supplementary Table S4：Normalized WB quantification values used for plotting.
- Supplementary Table S5：Raw Ct values for each qPCR replicate.
- Supplementary Table S6：2^-ΔΔCt calculation sheet and relative expression summary.
- Supplementary Figure S1：Full blot images with molecular weight markers.
- Supplementary Figure S2：Amplification / melting-curve quality control summary if needed.

### 七、投稿前核对清单
- [ ] Figure Legend 是否写清分组、统计学方法和显著性标记
- [ ] Supplementary 是否包含抗体、引物、原始灰度值和原始 Ct 值
- [ ] WB 与 qPCR 目标是否与主文机制一致
- [ ] Results 文字是否避免过度解释，仅基于真实结果

{qpcr_registry_block}

{qpcr_legend_block}
"""


def build_wb_qpcr_full_validation_bundle(
    project_name: str,
    disease_name: str,
    sample_type_wb: str,
    sample_type_qpcr: str,
    groups: str,
    target_proteins: str,
    target_genes: str,
    antibodies: str,
    primers: str,
    wb_data: str,
    qpcr_data: str,
):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(
        limit=12,
        heading="qPCR 图片 Supplementary Figure 自动编号",
    )
    qpcr_legend_block = build_qpcr_supplementary_legend_section(limit=12)
    group_block = groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"
    antibody_block = antibodies or "待补充抗体名称、货号、宿主和稀释比例"
    primer_block = primers or "待补充引物序列与内参基因"
    wb_block = wb_data or "Protein\tControl\tModel\tTreatment-Low\tTreatment-High"
    qpcr_block = qpcr_data or "Gene\tControl\tModel\tTreatment-Low\tTreatment-High"

    return f"""## WB / qPCR 联合验证总包

### 一、实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- WB 样本：{sample_type_wb or "- 待补充"}
- qPCR 样本：{sample_type_qpcr or "- 待补充"}

### 二、分组设计
```text
{group_block}
```

### 三、WB 目标蛋白
{target_proteins or "- 待补充 WB 目标蛋白"}

### 四、qPCR 目标基因
{target_genes or "- 待补充 qPCR 目标基因"}

### 五、抗体信息
```text
{antibody_block}
```

### 六、引物信息
```text
{primer_block}
```

### 七、WB 归一化数据
```text
{wb_block}
```

### 八、qPCR 相对表达数据
```text
{qpcr_block}
```

### 九、联合 Results 初稿
Combined WB and qPCR assays were performed to validate the proposed mechanism of {project_name} against {disease_name} at both protein and transcriptional levels. Compared with the control group, the model group exhibited abnormal expression patterns of the selected proteins and genes. Treatment with {project_name} partially or markedly reversed these changes. The consistency between the qPCR and WB results supported the interpretation that {project_name} regulated the selected targets and pathways at multiple biological levels.

### 十、分段 Results 句库
- Western blot analysis showed that the protein expression pattern of the selected targets was significantly dysregulated in the model group.
- Treatment with {project_name} restored or partially reversed these protein-level abnormalities.
- RT-qPCR analysis further demonstrated that the transcriptional changes of the selected genes were broadly consistent with the protein-level findings.
- Taken together, the convergent qPCR and WB data provided wet-lab evidence supporting the proposed mechanism.

### 十一、联合 Methods 初稿
For protein-level validation, total protein was extracted from {sample_type_wb or "the indicated samples"}, separated by SDS-PAGE, and transferred onto PVDF membranes. After blocking, the membranes were incubated with primary antibodies against {target_proteins or "the selected protein targets"} followed by the appropriate secondary antibodies. Immunoreactive bands were visualized using a chemiluminescence system, and the gray values were quantified with image analysis software. Relative protein expression was normalized to the internal reference protein, and phosphorylated proteins were additionally normalized to their corresponding total proteins when applicable.

For transcriptional validation, total RNA was extracted from {sample_type_qpcr or "the indicated samples"} and reverse-transcribed into cDNA. Quantitative PCR was performed using gene-specific primers for {target_genes or "the selected genes"}, with the designated housekeeping gene as the internal reference. Relative mRNA expression was calculated using the 2^-ΔΔCt method. The combined WB and qPCR data were used to evaluate whether {project_name} modulated the proposed mechanism of {disease_name} at both transcriptional and protein levels.

### 十二、联合 Figure Legend 清单
- Figure X. Effects of {project_name} on the protein expression related to {disease_name}. Representative immunoblots and normalized gray-value quantification are shown for each group.
- Figure Y. Effects of {project_name} on the mRNA expression related to {disease_name}. Relative expression levels were calculated using the 2^-ΔΔCt method and are presented as mean ± SD.
- Supplementary Figure S1. Full-length immunoblot images of the proteins analyzed in this study.
- Supplementary Figure S2. Raw Ct values and primer information used for the qPCR assays.

### 十三、Supplementary 建议清单
- Supplementary Table S1：Primary antibody information
- Supplementary Table S2：Primer sequences and reference gene information
- Supplementary Table S3：Raw WB gray values before normalization
- Supplementary Table S4：Normalized WB quantification values
- Supplementary Table S5：Raw Ct values for each biological replicate
- Supplementary Table S6：2^-ΔΔCt calculation sheet

### 十四、投稿前核对清单
- [ ] WB 与 qPCR 分组是否完全一致
- [ ] 抗体与引物信息是否齐全
- [ ] 原始灰度值和原始 Ct 值是否已保存
- [ ] 统计学方法与显著性标记是否统一
- [ ] Results 是否避免超出真实数据的解释

{qpcr_registry_block}

{qpcr_legend_block}
"""


def build_wb_qpcr_stats_bundle(
    project_name: str,
    disease_name: str,
    target_proteins: str,
    target_genes: str,
):
    wb_targets = target_proteins or "AKT / p-AKT / Nrf2 / HO-1"
    qpcr_targets = target_genes or "AKT1 / NFE2L2 / HMOX1 / BAX / BCL2"
    return f"""## WB / qPCR 统计与补充材料整合包

### 一、主文统计结果表模板
#### Table X. Summary of WB and qPCR validation results for {project_name} against {disease_name}
```text
Assay\tTarget\tControl (mean ± SD)\tModel (mean ± SD)\tTreatment-Low (mean ± SD)\tTreatment-High (mean ± SD)\tPositive control (mean ± SD)\tP value\tSignificance
WB\tTarget 1\t\t\t\t\t\t\t
WB\tTarget 2\t\t\t\t\t\t\t
qPCR\tGene 1\t\t\t\t\t\t\t
qPCR\tGene 2\t\t\t\t\t\t\t
```

### 二、WB 统计表模板
#### Suggested WB targets
{wb_targets}

```text
Protein\tReplicate number\tNormalization method\tControl\tModel\tTreatment-Low\tTreatment-High\tPositive control\tStatistical test\tP value
Protein 1\t3\tTarget / GAPDH\t\t\t\t\t\t\t
Protein 2\t3\tTarget / GAPDH\t\t\t\t\t\t\t
```

### 三、qPCR 统计表模板
#### Suggested qPCR targets
{qpcr_targets}

```text
Gene\tReplicate number\tReference gene\tControl\tModel\tTreatment-Low\tTreatment-High\tPositive control\tStatistical test\tP value
Gene 1\t3\tGAPDH\t\t\t\t\t\t\t
Gene 2\t3\tGAPDH\t\t\t\t\t\t\t
```

### 四、Supplementary Table 模板
#### Supplementary Table S1. Primary antibody information
```text
Target\tSupplier\tCatalog number\tHost species\tDilution\tIncubation condition
```

#### Supplementary Table S2. Primer information used for qPCR
```text
Gene\tForward primer (5'-3')\tReverse primer (5'-3')\tProduct size (bp)\tAnnealing temperature
```

#### Supplementary Table S3. Raw WB gray values
```text
Protein\tGroup\tRep1\tRep2\tRep3\tMean\tSD
```

#### Supplementary Table S4. Raw Ct values and 2^-ΔΔCt results
```text
Gene\tGroup\tCt-Rep1\tCt-Rep2\tCt-Rep3\tMean Ct\tDelta Ct\tDeltaDelta Ct\tRelative expression
```

### 五、原始数据说明稿
The raw data supporting the WB and qPCR findings are provided in the Supplementary Materials. Full-length WB images, raw gray values before normalization, normalized quantification values, primer sequences, raw Ct values, and the corresponding 2^-ΔΔCt calculation sheets were archived to ensure transparency and reproducibility. All quantitative data used for plotting the figures in the main text were directly derived from these raw experimental records.

### 六、返修或投稿时的原始数据说明句
- Raw WB images and quantitative gray-value data are available in the Supplementary Materials.
- Raw Ct values, primer sequences, and the complete 2^-ΔΔCt calculation sheet are provided in the Supplementary Materials.
- All summary statistics in the main text were calculated from at least three biological replicates.

### 七、核对清单
- [ ] 主文统计表是否与柱状图数值一致
- [ ] Supplementary Table 是否补齐抗体和引物信息
- [ ] 是否标明统计学方法、重复数和显著性阈值
- [ ] 原始数据说明是否与投稿要求一致
"""


def build_flow_experiment_bundle(project_name: str, disease_name: str):
    return f"""## 流式细胞术实验设计总包

### 建议实验分组
- Control 组：正常对照
- Model 组：{disease_name} 模型组
- Treatment-Low 组：{project_name} 低剂量组
- Treatment-High 组：{project_name} 高剂量组
- Positive control 组：阳性对照组

### 建议检测指标
- Annexin V / PI：细胞凋亡
- Cell cycle：细胞周期
- ROS fluorescence：若设备支持，可联动氧化应激结果

### 关键记录信息
- 染色方案：
- 上机通道：
- 门控策略：
- 每组采集事件数：

### Results 草稿骨架
- Flow cytometric analysis showed that {project_name} altered the proportion of the target cell population associated with {disease_name}.
- The treatment reduced the apoptotic fraction or shifted the distribution toward the protective phenotype.
"""


def build_ros_experiment_bundle(project_name: str, disease_name: str):
    return f"""## ROS 实验设计总包

### 建议实验分组
- Control 组：正常对照
- Model 组：{disease_name} 模型组
- Treatment-Low 组：{project_name} 低剂量组
- Treatment-High 组：{project_name} 高剂量组
- Positive control 组：阳性对照组

### 建议记录信息
- 探针名称：
- 染色浓度：
- 染色时间：
- 读取方式：酶标仪 / 荧光显微镜 / 流式

### Results 草稿骨架
- Intracellular ROS levels were markedly elevated in the model group compared with the control group.
- Treatment with {project_name} reduced ROS accumulation, indicating attenuation of oxidative stress in the {disease_name} model.
"""


def build_jc1_experiment_bundle(project_name: str, disease_name: str):
    return f"""## JC-1 线粒体膜电位实验设计总包

### 建议实验分组
- Control 组：正常对照
- Model 组：{disease_name} 模型组
- Treatment-Low 组：{project_name} 低剂量组
- Treatment-High 组：{project_name} 高剂量组
- Positive control 组：阳性对照组

### 建议记录信息
- 染色试剂：
- 染色时间：
- 红 / 绿荧光读取方式：
- 计算指标：红绿比值

### Results 草稿骨架
- The mitochondrial membrane potential was significantly reduced in the model group, as reflected by a decreased red/green fluorescence ratio.
- Treatment with {project_name} restored the JC-1 fluorescence pattern, suggesting preservation of mitochondrial function.
"""


def build_if_experiment_bundle(project_name: str, disease_name: str):
    return f"""## 免疫荧光 IF 实验设计总包

### 建议实验分组
- Control 组：正常对照
- Model 组：{disease_name} 模型组
- Treatment-Low 组：{project_name} 低剂量组
- Treatment-High 组：{project_name} 高剂量组
- Positive control 组：阳性对照组

### 建议记录信息
- 目标蛋白：
- 一抗信息：
- 二抗信息：
- DAPI 染核：
- 成像参数：

### Results 草稿骨架
- Immunofluorescence analysis revealed altered expression or subcellular localization of the selected marker in the {disease_name} model.
- Treatment with {project_name} reversed the abnormal fluorescence pattern, supporting modulation of the proposed pathway.
"""


def build_functional_validation_package_bundle(
    project_name: str,
    disease_name: str,
    markers: str,
    main_readouts: str,
):
    return f"""## 功能验证整合写作包

### 覆盖模块
- 流式细胞术
- ROS
- JC-1
- IF / 免疫荧光

### 重点指标
{markers or '- 待补充关键指标 / 标志物'}

### 核心读数
{main_readouts or '- 待补充主读数，如凋亡率、ROS强度、红绿比、荧光定位'}

### Figure Legend 清单
- Figure X. Flow cytometry analysis of apoptotic or other functional cell populations in the {disease_name} model after treatment with {project_name}.
- Figure Y. Intracellular ROS levels in each group following treatment with {project_name}.
- Figure Z. JC-1 fluorescence imaging and red/green ratio quantification showing changes in mitochondrial membrane potential.
- Figure W. Immunofluorescence staining of the selected marker, showing expression level or subcellular localization changes after treatment.

### 合并 Results 段骨架
Functional validation experiments further supported the protective effect of {project_name} against {disease_name}. Flow cytometry demonstrated an improvement in the relevant cell population phenotype, while ROS assays showed attenuation of oxidative stress. JC-1 staining indicated restoration of mitochondrial membrane potential, and immunofluorescence analysis further confirmed the regulation of the selected marker at the cellular level. Together, these results provided complementary functional evidence supporting the proposed mechanism.

### Supplementary 建议
- Supplementary Figure S1：Flow 门控策略图
- Supplementary Figure S2：ROS 原始荧光图 / 原始读数
- Supplementary Figure S3：JC-1 原始图像
- Supplementary Figure S4：IF 原始视野图
- Supplementary Table S1：抗体 / 探针 / 染料信息
- Supplementary Table S2：原始荧光强度或百分比数据

### 审稿前核对清单
- [ ] 是否保存原始流式门控图
- [ ] 是否保存 ROS / JC-1 / IF 原始图像
- [ ] 是否统一图中比例尺、颜色和统计方式
- [ ] 是否把功能实验与主文机制串起来
"""


def build_functional_validation_full_bundle(
    project_name: str,
    disease_name: str,
    sample_type: str,
    groups: str,
    markers: str,
    probe_reagents: str,
    main_readouts: str,
):
    return f"""## 功能验证联合总包

### 一、实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- 样本类型：{sample_type or "- 待补充"}

### 二、统一分组
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

### 三、关键指标 / 标志物
{markers or "- 待补充关键指标 / 标志物"}

### 四、探针 / 染料 / 抗体信息
```text
{probe_reagents or "待补充 Annexin V/PI、ROS 探针、JC-1、IF 一抗/二抗等信息"}
```

### 五、核心读数
{main_readouts or "- 待补充凋亡率、ROS 强度、JC-1 红绿比、IF 定位或荧光强度"}

### 六、联合 Results 初稿
Functional validation assays further supported the protective effect of {project_name} against {disease_name}. Flow cytometry showed an improvement in the relevant cell phenotype, such as reduced apoptosis or restoration of the normal cellular distribution. ROS assays indicated attenuation of oxidative stress after treatment. JC-1 staining suggested recovery of mitochondrial membrane potential, while immunofluorescence analysis further confirmed the expression change or subcellular redistribution of the selected marker. Collectively, these functional data provided complementary evidence supporting the proposed mechanism of {project_name}.

### 七、分段 Results 句库
- Flow cytometry demonstrated that the abnormal cell phenotype observed in the model group was partially or significantly reversed after treatment.
- Intracellular ROS accumulation was markedly increased in the model group but was attenuated by {project_name}.
- JC-1 staining revealed a restoration of mitochondrial membrane potential following treatment.
- Immunofluorescence analysis further confirmed the regulation of the selected marker at the cellular level.

### 八、联合 Methods 初稿
For functional validation, cells or samples derived from {sample_type or "the indicated model"} were assigned to the groups described above. Flow cytometry was performed to assess the relevant cellular phenotype using the designated staining reagents. Intracellular ROS accumulation was evaluated with the appropriate fluorescent probe, and mitochondrial membrane potential was determined by JC-1 staining. Immunofluorescence staining was conducted using antibodies against the selected marker to assess expression level or subcellular localization. Quantitative data were collected from at least three independent experiments and presented as mean ± SD.

### 九、Figure Legend 总清单
- Figure X. Flow cytometry analysis of the relevant cell phenotype in the {disease_name} model after treatment with {project_name}.
- Figure Y. Intracellular ROS levels in each group following treatment with {project_name}.
- Figure Z. JC-1 fluorescence imaging and red/green ratio quantification showing changes in mitochondrial membrane potential.
- Figure W. Immunofluorescence staining of the selected marker, showing expression level or subcellular localization changes after treatment.

### 十、Supplementary 建议清单
- Supplementary Figure S1：Flow 门控策略图
- Supplementary Figure S2：ROS 原始荧光图 / 原始读数
- Supplementary Figure S3：JC-1 原始图像
- Supplementary Figure S4：IF 原始视野图
- Supplementary Table S1：探针 / 染料 / 抗体信息
- Supplementary Table S2：原始功能读数和统计表

### 十一、投稿前核对清单
- [ ] Flow / ROS / JC-1 / IF 分组是否完全一致
- [ ] 原始图像、门控图和原始读数是否齐全
- [ ] 图中比例尺、颜色方案和统计标记是否统一
- [ ] 功能实验结果是否与主文机制一致
- [ ] Results 文字是否严格基于真实读数
"""


def build_recent_validation_snapshot():
    module_specs = [
        ("CCK-8", "05_数据分析/CCK8"),
        ("WB", "03_实验记录/WB"),
        ("qPCR", "03_实验记录/qPCR"),
        ("Flow", "03_实验记录/Flow"),
        ("ROS", "03_实验记录/ROS"),
        ("JC-1", "03_实验记录/JC1"),
        ("IF", "03_实验记录/IF"),
    ]
    blocks = []
    for label, folder in module_specs:
        items = get_recent_notes(folder, limit=2)
        if items:
            lines = [f"- {item['name']}｜{item['path']}" for item in items]
            blocks.append(f"### {label}\n" + "\n".join(lines))
        else:
            blocks.append(f"### {label}\n- 当前暂无最近记录。")
    return "\n\n".join(blocks)


def build_recent_validation_draft_fragments():
    draft_specs = [
        ("CCK-8 草稿", ["cck8", "cck-8"]),
        ("WB / qPCR 联合草稿", ["wb_qpcr", "wb qpcr", "wb", "qpcr"]),
        ("功能验证联合草稿", ["functional_validation", "flow_ros_jc1_if", "flow", "ros", "jc1", "if"]),
    ]
    files = list_md("06_论文写作")
    blocks = []

    for label, keywords in draft_specs:
        matched = None
        for file in files:
            haystack = file.name.lower()
            if any(keyword in haystack for keyword in keywords):
                matched = file
                break

        if not matched:
            blocks.append(f"### {label}\n- 当前暂无最近草稿。")
            continue

        content = read(matched)[:800]
        blocks.append(
            f"### {label}\n"
            f"- 来源：{matched.name}｜{matched.relative_to(ROOT)}\n"
            f"```text\n{content}\n```"
        )

    return "\n\n".join(blocks)


def build_recent_network_snapshot():
    figure_items = get_recent_figure_packages(limit=3)
    network_items = get_recent_notes("02_项目管理/网络药理学", limit=3)

    figure_lines = [f"- {item['name']}｜{item['path']}" for item in figure_items]
    network_lines = [f"- {item['name']}｜{item['path']}" for item in network_items]

    figure_block = "\n".join(figure_lines) if figure_lines else "- 当前暂无最近网络药理图表包。"
    network_block = "\n".join(network_lines) if network_lines else "- 当前暂无最近网络药理记录。"

    return f"""### 最近网络药理图表包
{figure_block}

### 最近网络药理记录
{network_block}"""


def build_network_validation_master_bundle(
    project_name: str,
    disease_name: str,
    mechanism_focus: str,
    target_focus: str,
    recent_network_snapshot: str,
    recent_validation_snapshot: str,
    recent_validation_fragments: str,
):
    mechanism_text = mechanism_focus or "多成分-多靶点-多通路作用机制"
    target_text = target_focus or "核心靶点、关键通路与下游验证指标"

    return f"""## 网络药理 + 实验验证整合总稿

### 一、研究主线
- 研究对象：{project_name}
- 疾病 / 模型：{disease_name}
- 机制主线：{mechanism_text}
- 优先验证重点：{target_text}

### 二、最近网络药理自动摘要
{recent_network_snapshot}

### 三、最近实验验证自动摘要
{recent_validation_snapshot}

### 四、最近验证草稿自动拼接
{recent_validation_fragments}

### 五、总 Results 主段初稿
Network pharmacology analysis suggested that {project_name} may exert therapeutic effects against {disease_name} through a multi-component, multi-target, and multi-pathway mode of action. The shared targets, hub genes, and representative enriched pathways provided a systems-level framework for selecting downstream validation markers. Subsequent experimental validation further supported this mechanistic prediction. CCK-8 assays demonstrated an overall beneficial effect on cell viability, WB and qPCR analyses suggested regulation of the selected targets and pathways at both protein and transcriptional levels, and functional assays including flow cytometry, ROS, JC-1, and immunofluorescence provided additional phenotypic and mechanistic support. Collectively, these data connected in silico predictions with wet-lab evidence and strengthened the proposed mechanism of {project_name} against {disease_name}.

### 六、Results 分段衔接句
- The network pharmacology results first identified shared targets, hub genes, and representative pathways associated with {disease_name}.
- Based on these findings, the key targets and pathways were prioritized for downstream experimental validation.
- The subsequent CCK-8, WB, qPCR, and functional assays generally supported the mechanistic hypothesis derived from the network pharmacology analysis.
- The consistency between the computational predictions and the experimental observations strengthened the overall interpretation of the study.

### 七、Discussion 主段初稿
The present study integrated network pharmacology analysis with downstream experimental validation to explore the potential therapeutic mechanism of {project_name} against {disease_name}. The network-level findings suggested that the pharmacological effects of {project_name} were likely mediated through coordinated regulation of multiple targets and pathways rather than a single molecular event. This systems-level prediction was further supported by wet-lab evidence showing beneficial effects on cellular phenotype, oxidative stress, mitochondrial function, and target-associated protein or gene expression. Therefore, the combined strategy of network pharmacology and experimental validation provided a coherent framework for interpreting the pharmacological activity of {project_name}.

### 八、Methods 总骨架
- Network pharmacology analysis was first conducted to identify shared targets, hub genes, and representative enriched pathways associated with {project_name} against {disease_name}.
- Based on these findings, candidate targets and pathways were prioritized for downstream validation.
- Cell viability was assessed using the CCK-8 assay.
- Protein-level changes were examined by Western blot analysis.
- Transcriptional changes were determined by RT-qPCR.
- Flow cytometry, ROS assays, JC-1 staining, and immunofluorescence were used to further validate the functional and mechanistic effects.

### 九、Figure 编排建议
- Figure 1：网络药理整体流程 / 成分-靶点-通路框架
- Figure 2：PPI / GO / KEGG 核心结果
- Figure 3：CCK-8 活力验证
- Figure 4：WB + qPCR 联合机制验证
- Figure 5：Flow / ROS / JC-1 / IF 功能验证

### 十、Supplementary 建议
- Supplementary Figure S1：完整网络药理附图或扩展图
- Supplementary Figure S2：Full blot images
- Supplementary Figure S3：Flow gating strategy
- Supplementary Figure S4：ROS / JC-1 / IF 原始图像
- Supplementary Table S1：抗体与引物信息
- Supplementary Table S2：原始灰度值、Ct 值与功能读数

### 十一、投稿前核对清单
- [ ] 网络药理结论与实验验证主线是否一致
- [ ] 关键靶点、通路和验证指标是否一一对应
- [ ] Results 段是否从预测证据自然过渡到湿实验证据
- [ ] Figure 编号、Figure Legend 与 Supplementary 是否完整对应
"""


def build_full_validation_master_bundle(
    project_name: str,
    disease_name: str,
    core_markers: str,
    key_readouts: str,
    recent_snapshot: str = "",
    recent_fragments: str = "",
):
    return f"""## 实验验证总包

### 覆盖模块
- CCK-8：整体活力 / 保护效应
- WB：蛋白水平机制验证
- qPCR：转录水平机制验证
- Flow：凋亡或表型流式验证
- ROS：氧化应激验证
- JC-1：线粒体膜电位验证
- IF：蛋白表达 / 定位验证

### 核心标志物
{core_markers or '- 待补充核心靶点、通路蛋白和功能标志物'}

### 核心读数
{key_readouts or '- 待补充细胞活力、蛋白表达、基因表达、凋亡率、ROS、膜电位和荧光定位读数'}

### 最近验证记录自动摘要
{recent_snapshot or '- 当前暂无自动摘要。'}

### 最近验证草稿自动拼接
{recent_fragments or '- 当前暂无最近草稿片段。'}

### 推荐 Figure 编排
- Figure 1：实验设计流程图 / 分组示意图
- Figure 2：CCK-8 活力结果
- Figure 3：WB 条带图 + 灰度统计
- Figure 4：qPCR 相对表达结果
- Figure 5：Flow 结果
- Figure 6：ROS 与 JC-1 结果
- Figure 7：IF 代表图与定量

### 合并 Results 段骨架
The experimental validation workflow further supported the protective effect of {project_name} against {disease_name}. Cell viability assays demonstrated an overall beneficial effect of the treatment. WB and qPCR analyses consistently suggested regulation of the selected targets and pathways at both protein and transcriptional levels. Flow cytometry further showed improvement in the relevant cell phenotype, while ROS and JC-1 assays indicated attenuation of oxidative stress and preservation of mitochondrial function. In addition, immunofluorescence analysis confirmed the expression change or subcellular redistribution of the selected marker. Collectively, these findings provided multi-level experimental evidence supporting the proposed mechanism of {project_name}.

### Figure Legend 总清单
- Figure 2. Effects of {project_name} on cell viability in the {disease_name} model.
- Figure 3. Effects of {project_name} on the protein expression of the selected targets in the {disease_name} model.
- Figure 4. Effects of {project_name} on the mRNA expression of the selected genes in the {disease_name} model.
- Figure 5. Flow cytometry analysis showing the effect of {project_name} on the relevant cell phenotype.
- Figure 6. Effects of {project_name} on intracellular ROS accumulation and mitochondrial membrane potential.
- Figure 7. Immunofluorescence staining of the selected marker in each group.

### Supplementary 建议
- Supplementary Figure S1：Full blot images
- Supplementary Figure S2：Flow gating strategy
- Supplementary Figure S3：ROS raw fluorescence images / readings
- Supplementary Figure S4：JC-1 raw images
- Supplementary Figure S5：IF raw fields
- Supplementary Table S1：Primary antibody information
- Supplementary Table S2：Primer sequences
- Supplementary Table S3：Raw WB gray values
- Supplementary Table S4：Raw Ct values and 2^-ΔΔCt calculations
- Supplementary Table S5：Raw flow percentages / counts
- Supplementary Table S6：Raw ROS / JC-1 / IF quantification values

### Methods 总骨架
- Cell viability was measured using the CCK-8 assay.
- Protein-level changes were determined by Western blot analysis.
- Transcriptional changes were evaluated by RT-qPCR.
- Flow cytometry was used to analyze apoptosis or other functional cell phenotypes.
- Intracellular ROS levels and mitochondrial membrane potential were assessed using ROS probes and JC-1 staining, respectively.
- Immunofluorescence staining was performed to assess the expression level or localization of the selected marker.

### 审稿前核对清单
- [ ] 主文 Figure 是否覆盖从表型到机制的完整证据链
- [ ] 所有 Supplementary 原始数据是否齐全
- [ ] WB / qPCR / 功能实验之间结论是否一致
- [ ] Results 文字是否严格基于真实结果
- [ ] Figure Legends 与正文引用编号是否一致
"""



def build_wb_qpcr_reviewer_bundle(
    project_name: str,
    disease_name: str,
    reviewer_comment: str,
    target_proteins: str,
    target_genes: str,
):
    return f"""## WB / qPCR 原始数据答复稿

### 审稿人意见原文
{reviewer_comment or '- 待补充审稿人意见'}

### 建议回复主段
We thank the reviewer for this valuable comment. In response, we have carefully整理并补充了与 {project_name} 在 {disease_name} 模型中的 WB 和 qPCR 验证相关的原始数据材料. Specifically, the full-length immunoblot images, raw gray values, normalized quantification values, primer sequences, raw Ct values, and the complete 2^-ΔΔCt calculation sheets have been rechecked and organized. These materials are now available in the revised supplementary files and support the reproducibility and transparency of the reported results.

### 可直接补到 Response Letter 的句子
- We have added the raw WB images and quantitative gray-value data to the Supplementary Materials.
- We have also provided the primer information, raw Ct values, and the complete 2^-ΔΔCt calculation sheet for the qPCR assays.
- These additions do not alter the conclusions of the study but improve the transparency of the experimental evidence.

### 建议补充的数据点
#### WB 目标蛋白
{target_proteins or '- 待补充 WB 目标蛋白'}

#### qPCR 目标基因
{target_genes or '- 待补充 qPCR 目标基因'}

### 建议放置位置
- Supplementary Figure S1：完整 WB 条带原图
- Supplementary Table S1：抗体信息
- Supplementary Table S2：引物信息
- Supplementary Table S3：原始灰度值与归一化结果
- Supplementary Table S4：原始 Ct 值与 2^-ΔΔCt 结果

### 说明结论不变的句子
- The additional raw data provided in the Supplementary Materials further support the consistency of the reported WB and qPCR findings, and the overall conclusions of the manuscript remain unchanged.

### 核对清单
- [ ] 是否补齐 full blot 图
- [ ] 是否补齐原始灰度值
- [ ] 是否补齐引物序列
- [ ] 是否补齐原始 Ct 值和 2^-ΔΔCt 表
- [ ] 是否在 Response Letter 中写明补充位置
"""


def build_wb_qpcr_mapping_bundle(
    project_name: str,
    disease_name: str,
    main_figures: str,
    supp_figures: str,
    main_tables: str,
    supp_tables: str,
):
    supp_figures_block = supp_figures or (
        "Supplementary Figure S1\tFull blot\n"
        + build_qpcr_supplementary_mapping_text(limit=12)
    )
    qpcr_bilingual_legend_block = build_qpcr_supplementary_bilingual_legend_section(limit=12)
    return f"""## WB / qPCR 图表编号映射包

### 主文 Figure 清单
```text
{main_figures or "Figure X\tWB条带+灰度\nFigure Y\tqPCR柱状图"}
```

### Supplementary Figure 清单
```text
{supp_figures_block}
```

### 主文 Table 清单
```text
{main_tables or "Table X\tWB/qPCR统计结果总表"}
```

### Supplementary Table 清单
```text
{supp_tables or "Supplementary Table S1\t抗体信息\nSupplementary Table S2\t引物信息\nSupplementary Table S3\t原始灰度值\nSupplementary Table S4\t原始Ct与2^-ΔΔCt"}
```

### 推荐映射逻辑
- 主文 Figure 优先保留最核心的机制证据：WB 定量图、qPCR 相对表达图。
- Supplementary Figure 主要放完整 WB 条带、熔解曲线、扩增曲线等支撑性图像。
- 主文 Table 建议只保留统计结果总表。
- Supplementary Table 用于放抗体、引物、原始值和计算表。

{qpcr_bilingual_legend_block}

### 编号一致性核对清单
- [ ] 主文 Figure 编号是否与正文引用一致
- [ ] Supplementary Figure 编号是否与图注一致
- [ ] 主文 Table 编号是否与 Results 段一致
- [ ] Supplementary Table 编号是否与 Response Letter 一致
- [ ] Figure Legend / Supplementary Legend 是否一一对应

### 投稿前说明句
- The numbering of the main figures, supplementary figures, main tables, and supplementary tables has been cross-checked to ensure consistency throughout the revised manuscript.
- The supplementary items were organized to provide full transparency for the WB and qPCR validation workflow of {project_name} against {disease_name}.
"""

def build_network_methods_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    methods_lines = [
        f"- Network pharmacology analysis was performed to investigate the potential mechanism of {project_name} against {disease_name}.",
        "- Compound-associated targets, disease-related targets, and, when available, differentially expressed genes were integrated to identify shared targets.",
    ]

    if any(item["name"] == "PPI 网络图" for item in recommendations):
        methods_lines.append("- A protein-protein interaction network was constructed for the shared targets to identify hub genes.")
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        methods_lines.append("- GO enrichment analysis was used to characterize the biological functions of the shared targets.")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        methods_lines.append("- KEGG pathway enrichment analysis was conducted to identify representative signaling pathways.")
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        methods_lines.append("- A component-target network was established to illustrate the multi-component and multi-target characteristics of the project.")

    return f"""## Methods 初稿

### 网络药理学方法骨架
{chr(10).join(methods_lines)}

### 可直接扩写的小标题
- Active compound collection and target prediction
- Disease target collection
- Intersection target identification
- Protein-protein interaction network construction
- GO and KEGG enrichment analyses
- Network visualization and hub target screening
- Experimental validation strategy

### Methods 英文模板
Network pharmacology analysis was conducted to explore the potential therapeutic mechanism of {project_name} against {disease_name}. Compound-associated targets, disease-related targets, and differentially expressed genes were integrated to identify shared targets. The shared targets were then subjected to protein-protein interaction analysis, functional enrichment analysis, and network visualization to identify hub genes and representative pathways. The resulting targets and pathways were further used to guide downstream docking and experimental validation.
"""


def build_network_introduction_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    mechanism_terms = []
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        mechanism_terms.append("oxidative stress")
        mechanism_terms.append("apoptosis")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        mechanism_terms.append("signaling pathways")
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        mechanism_terms.append("hub targets")

    mechanism_text = ", ".join(dict.fromkeys(mechanism_terms)) if mechanism_terms else "multi-target mechanisms"

    return f"""## Introduction 初稿

### 可直接扩写的逻辑
- 先交代 {disease_name} 的疾病负担、病理机制或临床治疗局限。
- 再说明天然产物或复杂成分体系在多靶点干预方面的潜在优势。
- 然后引出 {project_name} 作为候选研究对象的意义。
- 最后说明本研究通过网络药理、富集分析及后续验证来探索其潜在机制。

### Introduction 英文模板
{disease_name} remains a major health problem because of its complex pathogenesis and limited therapeutic options. Natural products have attracted increasing attention owing to their multi-component and multi-target characteristics. {project_name} may provide therapeutic benefits through {mechanism_text}. Therefore, this study aimed to explore the potential mechanism of {project_name} against {disease_name} by integrating network pharmacology analysis with downstream validation strategies.

### 待补充背景点
- 疾病流行病学或临床痛点：
- 当前常规治疗局限：
- 研究对象已有药理报道：
- 研究创新点：
"""


def build_network_abstract_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    has_enrichment = any(
        item["name"] in {"GO 气泡图", "KEGG 气泡图"}
        for item in recommendations
    )
    has_ppi = any(item["name"] == "PPI 网络图" for item in recommendations)

    result_points = []
    if has_ppi:
        result_points.append("identified hub targets from the shared target network")
    if has_enrichment:
        result_points.append("revealed representative biological processes and signaling pathways")
    if not result_points:
        result_points.append("generated a preliminary multi-target mechanism framework")

    results_text = "; ".join(result_points)

    return f"""## Abstract 初稿

### Structured Abstract 骨架
- Background：
- Purpose：
- Methods：
- Results：
- Conclusion：

### Abstract 英文模板
Background: {disease_name} is associated with complex pathological mechanisms and still lacks fully satisfactory therapeutic strategies. Purpose: This study aimed to investigate the potential therapeutic mechanism of {project_name} against {disease_name}. Methods: A network pharmacology workflow was used to integrate compound-associated targets, disease-related targets, and, when available, differentially expressed genes, followed by protein-protein interaction and enrichment analyses. Results: The analysis {results_text}. Conclusion: These findings suggest that {project_name} may exert therapeutic effects through a multi-component, multi-target, and multi-pathway mode of action, thereby providing a basis for subsequent docking and experimental validation.

### 待补充摘要数据
- 关键靶点数量：
- 代表性通路：
- 后续验证结果：
"""


def build_network_cover_letter_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    evidence_terms = []
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        evidence_terms.append("component-target network analysis")
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        evidence_terms.append("hub-target identification")
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        evidence_terms.append("GO functional enrichment")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        evidence_terms.append("KEGG pathway analysis")

    evidence_text = ", ".join(evidence_terms) if evidence_terms else "network pharmacology analysis"

    return f"""## Cover Letter 初稿

### 投稿信结构提示
- 第一段：说明稿件题目、研究主题和投稿类型。
- 第二段：概括本研究围绕 {project_name} 与 {disease_name} 的核心发现。
- 第三段：强调创新性、机制价值和潜在临床意义。
- 第四段：声明稿件未一稿多投、作者一致同意投稿。

### Cover Letter 英文模板
Dear Editor,

We are pleased to submit our manuscript entitled "[Manuscript Title]" for consideration for publication in [Journal Name]. In this study, we investigated the potential therapeutic mechanism of {project_name} against {disease_name} using {evidence_text}, together with downstream validation planning.

Our work highlights the multi-component, multi-target, and multi-pathway characteristics of {project_name} and provides a mechanistic framework for understanding its potential therapeutic effects in {disease_name}. We believe that these findings may be of interest to the readership of [Journal Name], particularly those focusing on natural products, pharmacology, and disease mechanism research.

This manuscript is original, has not been published previously, and is not under consideration for publication elsewhere. All authors have approved the manuscript and agree with its submission to your journal.

Thank you for your time and consideration. We look forward to your response.

Sincerely,
[Corresponding Author]

### 待补充投稿信息
- 目标期刊：
- 稿件标题：
- 研究亮点 3 条：
- 通讯作者信息：
"""


def build_network_graphical_abstract_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    modules = []
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        modules.append("活性成分")
        modules.append("潜在靶点")
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        modules.append("核心靶点")
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        modules.append("生物过程")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        modules.append("关键信号通路")

    module_text = " → ".join(dict.fromkeys(modules)) if modules else "成分 → 靶点 → 通路 → 验证"

    return f"""## Graphical Abstract 要点

### 图文摘要主线
- 推荐主线：{project_name} → {module_text} → {disease_name} 改善
- 左侧：研究对象 / 提取物 / 代表性活性成分
- 中间：核心靶点、PPI 或富集到的代表性通路
- 右侧：疾病表型改善或后续实验验证方向

### 图中建议保留的文字
- 研究对象：{project_name}
- 疾病 / 模型：{disease_name}
- 关键词 1：Multi-component
- 关键词 2：Multi-target
- 关键词 3：Multi-pathway

### 图文摘要说明句模板
The graphical abstract illustrates the potential therapeutic mechanism of {project_name} against {disease_name} from active compounds to hub targets and representative pathways, providing a concise overview of the network pharmacology-guided validation strategy.

### 设计检查清单
- [ ] 左中右结构是否清晰
- [ ] 术语是否与正文一致
- [ ] 关键通路是否只保留 1-2 条
- [ ] 核心靶点是否控制在 3-5 个
- [ ] 配色是否适合投稿期刊风格
"""


def build_network_highlights_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    highlight_terms = []
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        highlight_terms.append("multi-component and multi-target characteristics")
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        highlight_terms.append("hub targets")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        highlight_terms.append("representative signaling pathways")

    mechanism_text = ", ".join(highlight_terms) if highlight_terms else "a systems-level mechanism framework"

    return f"""## Highlights 初稿

### Highlights 撰写要求
- 每条尽量控制在 85 个字符左右。
- 用结果导向短句，不写空泛背景。
- 优先突出研究对象、机制主线、方法特色和验证价值。

### Highlights 英文模板
- {project_name} showed potential therapeutic relevance against {disease_name}.
- Network pharmacology identified {mechanism_text} associated with the project.
- The study provided candidate targets and pathways for downstream validation.

### 中文提炼版本
- {project_name} 对 {disease_name} 具有潜在干预价值。
- 网络药理学揭示了其多成分、多靶点、多通路作用特征。
- 研究为后续对接与实验验证提供了明确候选方向。
"""


def build_network_conclusion_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    support_terms = []
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        support_terms.append("hub-target screening")
    if any(item["name"] == "GO 气泡图" for item in recommendations):
        support_terms.append("biological process enrichment")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        support_terms.append("pathway-level evidence")

    support_text = ", ".join(support_terms) if support_terms else "network pharmacology evidence"

    return f"""## Conclusion 初稿

### Conclusion 英文模板
In conclusion, the present study suggests that {project_name} may exert therapeutic effects against {disease_name} through a multi-component, multi-target, and multi-pathway mode of action. The combination of {support_text} provided a preliminary mechanistic basis for understanding the pharmacological effects of this project. These findings offer candidate targets and pathways for further docking studies and experimental validation.

### 中文结论骨架
- 本研究提示 {project_name} 可能通过多成分、多靶点、多通路方式干预 {disease_name}。
- 网络药理结果为其潜在机制提供了初步系统性证据。
- 后续仍需结合分子对接及实验验证进一步确认关键靶点与通路。

### 结论写作提醒
- 不要把“预测”写成“已证实”。
- 最后一段最好自然衔接后续验证工作。
"""


def build_network_keywords_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    keywords = [project_name, disease_name, "network pharmacology"]
    if any(item["name"] == "PPI 网络图" for item in recommendations):
        keywords.append("hub targets")
    if any(item["name"] == "KEGG 气泡图" for item in recommendations):
        keywords.append("signaling pathways")
    if any(item["name"] == "成分-靶点网络图" for item in recommendations):
        keywords.append("natural products")

    normalized = []
    for item in keywords:
        if item and item not in normalized:
            normalized.append(item)

    return f"""## Keywords 初稿

### 推荐英文关键词
- {chr(10).join([f"- {item}" for item in normalized[:6]])}

### 推荐中文关键词
- {project_name}
- {disease_name}
- 网络药理学
- 核心靶点
- 信号通路

### 选择建议
- 优先保留 4-6 个关键词。
- 关键词尽量覆盖研究对象、疾病、方法和机制。
"""


def build_network_title_bundle(
    recommendations,
    project_name: str,
    disease_name: str,
):
    has_ppi = any(item["name"] == "PPI 网络图" for item in recommendations)
    has_kegg = any(item["name"] == "KEGG 气泡图" for item in recommendations)

    route_phrase = "based on network pharmacology analysis"
    if has_ppi and has_kegg:
        route_phrase = "based on network pharmacology and pathway enrichment analysis"

    return f"""## Title 备选初稿

### 英文标题备选
- Exploring the Potential Mechanism of {project_name} against {disease_name} {route_phrase}
- Network Pharmacology-Based Investigation of {project_name} for the Treatment of {disease_name}
- Mechanistic Study of {project_name} in {disease_name}: A Network Pharmacology Perspective

### 中文标题备选
- 基于网络药理学的{project_name}干预{disease_name}潜在机制研究
- {project_name}治疗{disease_name}的网络药理学机制探讨
- {project_name}干预{disease_name}的多靶点机制研究

### 标题优化提醒
- 避免标题过长。
- 若后续加入 docking / 实验验证，可在副标题中补充。
"""


def build_network_submission_package_bundle(
    project_name: str,
    disease_name: str,
):
    return f"""## Submission Package 总包

### 投稿包组成
- Title
- Abstract
- Keywords
- Highlights
- Introduction
- Methods
- Results
- Discussion
- Conclusion
- Cover Letter
- Graphical Abstract
- Figure Legends

### 投稿前检查清单
- [ ] 标题与摘要保持一致
- [ ] 关键词覆盖研究对象、疾病和方法
- [ ] Highlights 已压缩为 3-4 条短句
- [ ] Figure legend 与图号完全对应
- [ ] Results 与 Discussion 的逻辑顺序一致
- [ ] Methods 已补数据库、软件和筛选阈值
- [ ] Cover Letter 已补期刊名称和稿件标题
- [ ] Graphical Abstract 与正文机制主线一致
- [ ] 结论没有把预测结果写成已完全证实

### 建议投稿主线
This submission package centers on the potential therapeutic mechanism of {project_name} against {disease_name}, with network pharmacology serving as the main discovery framework and downstream validation as the next evidence step.

### 建议最后人工确认的内容
- 目标期刊格式要求
- 作者信息与单位
- 图表分辨率与命名
- 缩写首次出现定义
- 引文格式与参考文献完整性
"""


def build_response_letter_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    journal_name_map = {
        "generic": "[Journal Name]",
        "phytomedicine": "Phytomedicine",
        "joe": "Journal of Ethnopharmacology",
    }
    journal_name = journal_name_map.get(journal, "[Journal Name]")

    if journal == "phytomedicine":
        tone_hint = "回复语气应专业、简洁，重点强调机制证据链、天然产物药理价值和修改后的增强内容。"
    elif journal == "joe":
        tone_hint = "回复语气应兼顾传统应用背景与现代机制解释，突出研究对象来源、研究依据和机制补强。"
    else:
        tone_hint = "回复语气应礼貌、明确、逐条对应，避免情绪化或空泛表述。"

    return f"""## Response Letter 草稿

### 回复原则
- 逐条对应审稿意见。
- 先感谢，再回答，再说明修改位置。
- 若无法完全满足，解释原因并给出替代性补充。
- 避免使用防御性语气。

### 当前期刊回复提示
- 目标期刊：{journal_name}
- 风格提示：{tone_hint}

### Response Letter 开头模板
Dear Editor and Reviewers,

We sincerely thank you for the careful evaluation of our manuscript and for the constructive comments and suggestions. We have carefully revised the manuscript entitled "[Manuscript Title]" and addressed the comments point by point below. We believe that these revisions have improved the clarity and quality of the manuscript.

### 总体回复思路
- 本研究围绕 {project_name} 与 {disease_name} 的潜在机制展开。
- 若有新增图表或新增分析，优先说明新增内容。
- 若有补充实验或补充解释，说明其如何增强原结论。

### 常用句式
- We thank the reviewer for this insightful comment.
- We have revised the manuscript accordingly.
- In response to this concern, we have added...
- The relevant changes have been incorporated in the revised manuscript.
- We respectfully clarify that...

### 逐条回复骨架
#### Editor comments
- Comment:
- Response:
- Changes made in manuscript:

#### Reviewer 1
- Comment 1:
- Response 1:
- Location in revised manuscript:

#### Reviewer 2
- Comment 1:
- Response 1:
- Location in revised manuscript:
"""


def build_reviewer_comment_split_bundle(raw_comments: str):
    lines = [line.strip() for line in raw_comments.splitlines() if line.strip()]
    comments = []

    for line in lines:
        if line[:3].lower() in {"1. ", "2. ", "3. ", "4. ", "5. "}:
            comments.append(line[3:].strip())
        elif line.startswith(("-", "•", "*")):
            comments.append(line[1:].strip())
        else:
            comments.append(line)

    if not comments:
        comments = ["[请粘贴审稿意见后重新生成]"]

    blocks = []
    for idx, comment in enumerate(comments, start=1):
        blocks.append(
            f"""### Comment {idx}
{comment}

### Response {idx}
We thank the reviewer for this valuable comment.

### Changes made
- 

### Location in revised manuscript
- Page:
- Line:
"""
        )

    return "## Reviewer Comment 拆分结果\n\n" + "\n".join(blocks)


def build_journal_preset_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    preset_map = {
        "generic": {
            "label": "通用投稿模板",
            "scope": "适合先整理完整投稿材料，再根据目标期刊二次微调。",
            "focus": [
                "标题、摘要、关键词、Highlights 先内部统一",
                "Figure legends 与正文段落逐一对应",
                "Cover letter 中补齐期刊名称、稿件类型和创新点",
            ],
            "checks": [
                "核对摘要、结论和讨论是否同一口径",
                "核对缩写首次出现是否定义",
                "核对参考文献格式与期刊要求是否一致",
            ],
        },
        "phytomedicine": {
            "label": "Phytomedicine 模板",
            "scope": "更强调天然产物药理机制、疾病相关性和转化潜力。",
            "focus": [
                f"突出 {project_name} 作为天然产物或植物来源干预策略的药理意义",
                f"强调 {disease_name} 相关机制主线和潜在应用价值",
                "摘要、Highlights 和 Cover letter 中都要明确创新点与机制证据链",
            ],
            "checks": [
                "检查植物药/天然产物表述是否统一",
                "检查机制解释是否与图表和验证计划一致",
                "检查图文摘要是否清晰展示成分—靶点—通路主线",
            ],
        },
        "joe": {
            "label": "Journal of Ethnopharmacology 模板",
            "scope": "更强调传统应用背景、药用依据、天然产物来源与机制研究衔接。",
            "focus": [
                f"补足 {project_name} 的传统药用背景、来源和研究依据",
                "说明为何选择该研究对象以及其与现代机制研究的连接",
                f"在引言和讨论中更自然地连接传统用途与 {disease_name} 的现代研究问题",
            ],
            "checks": [
                "检查研究对象来源、部位、命名是否规范统一",
                "检查引言中传统应用背景是否交代充分",
                "检查机制研究结果是否没有脱离天然产物研究语境",
            ],
        },
    }

    selected = preset_map.get(journal, preset_map["generic"])
    focus_lines = "\n".join([f"- {item}" for item in selected["focus"]])
    check_lines = "\n".join([f"- [ ] {item}" for item in selected["checks"]])

    return f"""## 期刊模板建议

### 当前模板
- 目标模板：{selected['label']}
- 适用说明：{selected['scope']}

### 当前模板写作重点
{focus_lines}

### 当前模板额外检查
{check_lines}
"""


def build_journal_cover_letter_style_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    if journal == "phytomedicine":
        return f"""## Cover Letter 期刊风格建议

### Phytomedicine 风格重点
- 第一段尽快点明 {project_name} 的天然产物 / 植物药研究属性。
- 第二段强调对 {disease_name} 的机制探索价值和潜在转化意义。
- 第三段突出多成分、多靶点、多通路特点，但避免过度夸大临床应用。

### Cover Letter 句式建议
- We believe this work fits the scope of Phytomedicine because it highlights the pharmacological potential of a natural-product-based intervention.
- The study provides a mechanistic framework linking active compounds, hub targets, and representative pathways relevant to {disease_name}.
"""

    if journal == "joe":
        return f"""## Cover Letter 期刊风格建议

### Journal of Ethnopharmacology 风格重点
- 第一段补足 {project_name} 的传统应用背景或民族药用依据。
- 第二段解释为何从传统用途中延伸到 {disease_name} 的现代机制研究。
- 第三段强调天然产物来源、药用依据与网络药理机制分析之间的逻辑桥梁。

### Cover Letter 句式建议
- We believe this manuscript fits the scope of the Journal of Ethnopharmacology because it connects the traditional medicinal relevance of {project_name} with modern mechanism-oriented pharmacological analysis.
- The study extends ethnopharmacological knowledge by exploring the potential therapeutic mechanism of {project_name} against {disease_name}.
"""

    return f"""## Cover Letter 期刊风格建议

### 通用风格重点
- 简洁说明稿件主题、核心发现和投稿价值。
- 不要把验证计划写成已经完成的实验结果。
- 重点说明为什么该稿件适合目标期刊读者。
"""


def build_journal_highlights_style_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    if journal == "phytomedicine":
        return f"""## Highlights 期刊风格建议

### Phytomedicine 更适合的亮点表达
- 强调天然产物药理价值。
- 强调机制主线而不是泛泛背景。
- 可突出后续验证潜力，但避免直接写成临床结论。

### 推荐表达方向
- {project_name} showed pharmacological potential against {disease_name}.
- Network pharmacology revealed representative targets and pathways.
- The findings support subsequent docking and biological validation.
"""

    if journal == "joe":
        return f"""## Highlights 期刊风格建议

### Journal of Ethnopharmacology 更适合的亮点表达
- 兼顾传统药用背景与现代机制研究。
- 突出天然来源和研究依据。
- 机制亮点要与 ethnopharmacology 语境保持一致。

### 推荐表达方向
- {project_name} was investigated based on its medicinal relevance.
- The study linked traditional use with modern network pharmacology analysis.
- Candidate targets and pathways were identified for {disease_name}.
"""

    return f"""## Highlights 期刊风格建议

### 通用亮点表达
- 每条短、准、硬。
- 一条说研究对象，一条说方法发现，一条说后续验证价值。
"""


def build_journal_graphical_abstract_style_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    if journal == "phytomedicine":
        return f"""## Graphical Abstract 期刊风格建议

### Phytomedicine 图文摘要重点
- 左侧突出天然产物来源或活性成分。
- 中间突出核心靶点和关键信号通路。
- 右侧突出对 {disease_name} 的改善方向或验证路径。

### 版式建议
- 用 3 段式结构：成分 → 靶点 / 通路 → 疾病相关效应。
- 颜色尽量清爽，突出药理机制主线。
"""

    if journal == "joe":
        return f"""## Graphical Abstract 期刊风格建议

### Journal of Ethnopharmacology 图文摘要重点
- 起点可加入药材 / 民族药 / 传统用途线索。
- 中段展示网络药理机制链条。
- 终点展示与 {disease_name} 相关的现代药理解释。

### 版式建议
- 用“传统依据 → 机制分析 → 现代验证方向”的叙事顺序。
- 图中术语尽量兼顾天然产物研究语境。
"""

    return f"""## Graphical Abstract 期刊风格建议

### 通用图文摘要重点
- 保留一条清晰主线。
- 核心靶点和通路不要过多。
- 与摘要和结果中的主机制保持一致。
"""


def build_journal_cover_letter_full_draft_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    if journal == "phytomedicine":
        return f"""## Cover Letter 成稿版（Phytomedicine）

Dear Editor,

We are pleased to submit our manuscript entitled "[Manuscript Title]" for consideration for publication in Phytomedicine. In this study, we explored the potential therapeutic mechanism of {project_name} against {disease_name} using a network pharmacology-based strategy integrated with downstream validation planning.

Our findings highlight the pharmacological potential of {project_name} as a natural-product-based intervention and reveal a multi-component, multi-target, and multi-pathway mechanism framework relevant to {disease_name}. By connecting active compounds, hub targets, and representative signaling pathways, this work provides a mechanistic basis for subsequent docking and experimental validation.

We believe this manuscript fits the scope of Phytomedicine because it emphasizes the therapeutic relevance of a natural product and provides mechanism-oriented pharmacological insights with potential translational value.

This manuscript is original, has not been published previously, and is not under consideration elsewhere. All authors have approved the manuscript and agree with its submission.

Thank you for your time and consideration.

Sincerely,
[Corresponding Author]
"""
    if journal == "joe":
        return f"""## Cover Letter 成稿版（Journal of Ethnopharmacology）

Dear Editor,

We are pleased to submit our manuscript entitled "[Manuscript Title]" for consideration for publication in the Journal of Ethnopharmacology. This work investigates the potential therapeutic mechanism of {project_name} against {disease_name} through network pharmacology analysis and downstream validation planning.

The study is particularly relevant to the journal because it helps connect the medicinal relevance of {project_name} with modern mechanism-oriented pharmacological investigation. By linking active compounds, candidate targets, and representative pathways, our work extends the understanding of how a traditional or natural-product-derived intervention may act in the context of {disease_name}.

We believe this manuscript will be of interest to readers in ethnopharmacology, natural product research, and mechanism-based pharmacology.

This manuscript is original, has not been published previously, and is not under consideration elsewhere. All authors have approved the manuscript and agree with its submission.

Thank you for your time and consideration.

Sincerely,
[Corresponding Author]
"""
    return f"""## Cover Letter 成稿版（通用）

Dear Editor,

We are pleased to submit our manuscript entitled "[Manuscript Title]" for consideration for publication in [Journal Name]. This study explored the potential therapeutic mechanism of {project_name} against {disease_name} through network pharmacology analysis and downstream validation planning.

Our work provides a preliminary mechanistic framework linking active compounds, candidate targets, and representative pathways, thereby offering a basis for further validation and interpretation.

This manuscript is original, has not been published previously, and is not under consideration elsewhere. All authors have approved the manuscript and agree with its submission.

Thank you for your consideration.

Sincerely,
[Corresponding Author]
"""


def build_journal_highlights_full_draft_bundle(
    journal: str,
    project_name: str,
    disease_name: str,
):
    if journal == "phytomedicine":
        return f"""## Highlights 成稿版（Phytomedicine）

- {project_name} showed pharmacological potential against {disease_name}.
- Network pharmacology revealed candidate hub targets and representative pathways.
- The study supports subsequent docking and biological validation of a natural-product-based intervention.
"""
    if journal == "joe":
        return f"""## Highlights 成稿版（Journal of Ethnopharmacology）

- {project_name} was investigated in a natural-product and medicinal-use context.
- Network pharmacology connected traditional relevance with modern mechanistic analysis.
- Candidate targets and pathways were identified for follow-up validation in {disease_name}.
"""
    return f"""## Highlights 成稿版（通用）

- {project_name} showed potential relevance against {disease_name}.
- Network pharmacology identified candidate targets and pathways.
- The findings provide a basis for downstream validation.
"""


def get_recent_notes(folder: str, limit: int = 5):
    files = list_md(folder)
    items = []
    for file in files[:limit]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:300],
        })
    return items


def get_recent_qpcr_image_writebacks(limit: int = 5):
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    if not folder.exists():
        return []
    files = sorted(
        folder.glob("*_qPCR_Image_Writeback.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = []
    for file in files[:limit]:
        items.append(
            {
                "name": file.name,
                "path": str(file.relative_to(ROOT)),
                "content": read(file)[:500],
            }
        )
    return items


def get_qpcr_image_type_bucket(image_type: str):
    text = (image_type or "").strip()
    lower = text.lower()
    if "扩增" in text:
        return "S1", "扩增曲线补充图"
    if "熔解" in text or "融解" in text:
        return "S2", "熔解曲线补充图"
    if "ct" in lower or "报告" in text:
        return "S3", "原始 Ct 报告补充图"
    if "仪器" in text or "截图" in text:
        return "S4", "仪器结果截图补充图"
    return "S5", "其他 qPCR 支持图片"


def _format_qpcr_supplementary_suffix(index: int):
    if index <= 26:
        return chr(64 + index)
    return f"-{index}"


def build_qpcr_image_registry(limit: int | None = None):
    image_files = list_files(
        "03_实验记录/qPCR_原始图片",
        suffixes={".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"},
    )
    if not image_files:
        return []

    ordered = sorted(image_files, key=lambda p: (p.stat().st_mtime, p.name))
    counters = {}
    registry = []
    for file in ordered:
        note_path = file.with_suffix(".md")
        note_text = read(note_path) if note_path.exists() else ""
        image_type = extract_markdown_section(note_text, "图片类型") if note_text else ""
        supp_base, supp_title = get_qpcr_image_type_bucket(image_type)
        counters[supp_base] = counters.get(supp_base, 0) + 1
        suffix = _format_qpcr_supplementary_suffix(counters[supp_base])
        registry.append(
            {
                "name": file.name,
                "path": str(file.relative_to(ROOT)),
                "note_path": str(note_path.relative_to(ROOT)) if note_path.exists() else "",
                "note_content": note_text[:240] if note_text else "",
                "image_type": image_type,
                "supplementary_label": f"Supplementary Figure {supp_base}{suffix}",
                "supplementary_title": supp_title,
                "mtime": file.stat().st_mtime,
            }
        )

    registry.sort(key=lambda item: item["mtime"], reverse=True)
    if limit is not None:
        registry = registry[:limit]
    for item in registry:
        item.pop("mtime", None)
    return registry


def build_qpcr_supplementary_registry_section(
    limit: int | None = None,
    heading: str = "qPCR 图片 Supplementary Figure 建议清单",
):
    registry = build_qpcr_image_registry(limit=limit)
    if not registry:
        return f"""## {heading}
- 当前暂无已归档的 qPCR 原始图片。
"""

    lines = [f"## {heading}"]
    for item in registry:
        lines.append(f"### {item['supplementary_label']}")
        lines.append(f"- 建议标题：{item['supplementary_title']}")
        lines.append(f"- 图片类型：{item['image_type'] or '未注明'}")
        lines.append(f"- 原始文件：{item['path']}")
        if item["note_path"]:
            lines.append(f"- 备注文件：{item['note_path']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_qpcr_supplementary_mapping_text(limit: int | None = None):
    registry = build_qpcr_image_registry(limit=limit)
    if not registry:
        return "Supplementary Figure S1\tqPCR QC / melting curve"

    lines = []
    for item in registry:
        lines.append(
            f"{item['supplementary_label']}\t{item['supplementary_title']}（{item['image_type'] or '未注明'}）"
        )
    return "\n".join(lines)


def build_qpcr_supplementary_legend_section(
    limit: int | None = None,
    heading: str = "qPCR Supplementary Figure Legend 草稿",
):
    registry = build_qpcr_image_registry(limit=limit)
    if not registry:
        return f"""## {heading}
- 当前暂无已归档的 qPCR 原始图片，暂无法生成正式图注。
"""

    lines = [f"## {heading}"]
    for item in registry:
        image_type = item["image_type"] or "qPCR supporting image"
        lines.append(
            f"- {item['supplementary_label']}. {item['supplementary_title']} for the qPCR assay. This panel presents the {image_type} supporting the transcriptional validation workflow, and the corresponding raw image is archived at {item['path']}."
        )
    return "\n".join(lines) + "\n"


def build_qpcr_supplementary_bilingual_legend_section(
    limit: int | None = None,
    heading: str = "qPCR Supplementary Figure Legend 中英双语稿",
):
    registry = build_qpcr_image_registry(limit=limit)
    if not registry:
        return f"""## {heading}
- 当前暂无已归档的 qPCR 原始图片，暂无法生成双语图注。
"""

    lines = [f"## {heading}"]
    for item in registry:
        image_type = item["image_type"] or "qPCR supporting image"
        lines.append(f"### {item['supplementary_label']}")
        lines.append(
            f"- 中文：{item['supplementary_title']}，用于展示 qPCR 实验中的{image_type}，对应原始图片归档路径为 {item['path']}。"
        )
        lines.append(
            f"- English: {item['supplementary_title']} for the qPCR assay. This panel presents the {image_type} supporting the transcriptional validation workflow, and the corresponding raw image is archived at {item['path']}."
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_recent_image_writeback_section(items, heading: str = "最近 qPCR 图片回填草稿"):
    if not items:
        return f"""## {heading}
- 当前暂无 qPCR 图片回填草稿。
"""

    lines = [f"## {heading}"]
    for item in items:
        lines.append(f"### {item['name']}")
        lines.append(f"- 路径：{item['path']}")
        lines.append(item["content"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_experiment_dashboard_modules():
    module_specs = [
        {
            "key": "cck8",
            "title": "CCK-8",
            "description": "细胞活力与给药趋势",
            "folders": ["03_实验记录", "05_数据分析"],
            "keywords": ["cck8", "cck-8", "细胞活力"],
            "next_step": "补齐浓度梯度、重复次数和统计图。",
        },
        {
            "key": "wb",
            "title": "WB",
            "description": "蛋白表达验证",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": ["wb", "western blot"],
            "next_step": "补齐灰度值、内参与代表性条带图。",
        },
        {
            "key": "qpcr",
            "title": "qPCR",
            "description": "转录水平验证",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": ["qpcr", "rt-qpcr", "rt qpcr", "pcr", "ct值"],
            "next_step": "补齐 Ct 原始值、2^-ΔΔCt 表和引物信息。",
        },
        {
            "key": "flow",
            "title": "Flow",
            "description": "流式表型验证",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": ["flow", "流式"],
            "next_step": "补齐门控图、阳性率和统计比较。",
        },
        {
            "key": "ros",
            "title": "ROS",
            "description": "氧化应激水平",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": ["ros", "氧化应激"],
            "next_step": "补齐荧光图、定量值与代表性结果句。",
        },
        {
            "key": "jc1",
            "title": "JC-1",
            "description": "线粒体膜电位",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": ["jc1", "jc-1", "膜电位"],
            "next_step": "补齐红绿比值、统计图和机制解释。",
        },
        {
            "key": "if",
            "title": "IF",
            "description": "免疫荧光定位验证",
            "folders": ["03_实验记录", "06_论文写作"],
            "keywords": [" if", "if验证", "免疫荧光", "immunofluorescence"],
            "next_step": "补齐代表图、定位描述和定量策略。",
        },
    ]

    modules = []
    for spec in module_specs:
        matched = []
        for folder in spec["folders"]:
            for file in list_md(folder):
                haystack = f"{file.name}\n{read(file)[:400]}".lower()
                if any(keyword in haystack for keyword in spec["keywords"]):
                    matched.append(file)

        unique_files = []
        seen = set()
        for file in matched:
            rel = str(file.relative_to(ROOT))
            if rel in seen:
                continue
            seen.add(rel)
            unique_files.append(file)

        recent = []
        for file in unique_files[:3]:
            recent.append({
                "name": file.name,
                "path": str(file.relative_to(ROOT)),
                "content": read(file)[:220],
            })

        count = len(unique_files)
        if count >= 3:
            status = "已形成可写结果基础"
        elif count >= 1:
            status = "已有记录，建议继续补图和统计"
        else:
            status = "尚缺直接记录"

        can_make_figure = count >= 1
        can_write_results = count >= 2
        can_write_methods = count >= 1
        if spec["key"] in {"wb", "qpcr", "flow", "ros", "jc1", "if"}:
            can_make_figure = count >= 1
            can_write_results = count >= 1
            can_write_methods = True

        deliverables = []
        if can_make_figure:
            deliverables.append("Figure")
        if can_write_results:
            deliverables.append("Results")
        if can_write_methods:
            deliverables.append("Methods")

        modules.append({
            "key": spec["key"],
            "title": spec["title"],
            "description": spec["description"],
            "count": count,
            "status": status,
            "next_step": spec["next_step"],
            "can_make_figure": can_make_figure,
            "can_write_results": can_write_results,
            "can_write_methods": can_write_methods,
            "deliverables": deliverables,
            "recent": recent,
        })

    return modules


def get_validation_writing_outputs(limit: int = 8):
    keywords = [
        "wb",
        "qpcr",
        "flow",
        "ros",
        "jc1",
        "jc-1",
        "if",
        "验证",
        "supplementary",
        "figure",
        "methods",
    ]
    items = []
    for file in list_md("06_论文写作"):
        haystack = file.name.lower()
        if not any(keyword in haystack for keyword in keywords):
            continue
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:260],
        })
        if len(items) >= limit:
            break
    return items


def get_experiment_dashboard_summary():
    modules = build_experiment_dashboard_modules()
    active = sum(1 for module in modules if module["count"] > 0)
    ready = sum(1 for module in modules if module["count"] >= 3)
    empty = [module["title"] for module in modules if module["count"] == 0]
    figure_ready = [module["title"] for module in modules if module["can_make_figure"]]
    results_ready = [module["title"] for module in modules if module["can_write_results"]]
    methods_ready = [module["title"] for module in modules if module["can_write_methods"]]

    figure_suggestions = []
    if any(module["key"] == "cck8" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：CCK-8 细胞活力柱状图 / 折线图")
    if any(module["key"] == "wb" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：WB 条带图 + 灰度值统计图")
    if any(module["key"] == "qpcr" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：qPCR 相对表达柱状图")
    if any(module["key"] == "flow" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：流式门控图 + 阳性率统计图")
    if any(module["key"] == "ros" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：ROS 荧光图 + 定量图")
    if any(module["key"] == "jc1" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：JC-1 红绿荧光图 + 比值统计图")
    if any(module["key"] == "if" and module["can_make_figure"] for module in modules):
        figure_suggestions.append("Figure：IF 代表图 + 定量分析图")

    results_suggestions = []
    if results_ready:
        results_suggestions.append(
            "Results：已可先写 " + "、".join(results_ready[:4]) + " 的结果段初稿"
        )
    if "wb" in [module["key"] for module in modules if module["can_write_results"]] and \
       "qpcr" in [module["key"] for module in modules if module["can_write_results"]]:
        results_suggestions.append("Results：可合并生成 WB + qPCR 联合验证结果段")

    methods_suggestions = []
    if methods_ready:
        methods_suggestions.append(
            "Methods：已可先写 " + "、".join(methods_ready[:4]) + " 的方法学初稿"
        )
    if "flow" in [module["key"] for module in modules if module["can_write_methods"]]:
        methods_suggestions.append("Methods：可补写流式染色、门控和统计分析描述")

    return {
        "modules": modules,
        "active_count": active,
        "ready_count": ready,
        "empty_modules": empty,
        "figure_ready": figure_ready,
        "results_ready": results_ready,
        "methods_ready": methods_ready,
        "figure_suggestions": figure_suggestions,
        "results_suggestions": results_suggestions,
        "methods_suggestions": methods_suggestions,
    }


def get_recent_figure_packages(limit: int = 5):
    files = list_md("05_数据分析/科研作图")
    items = []
    for file in files:
        if "网络药理图表包" not in file.name:
            continue
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:300],
        })
        if len(items) >= limit:
            break
    return items


def get_table_preview(path: Path, max_rows: int = 5):
    suffix = path.suffix.lower()
    result = {
        "headers": [],
        "rows": [],
        "error": "",
        "suffix": suffix,
    }

    if not path.exists() or not path.is_file():
        result["error"] = "文件不存在。"
        return result

    try:
        if suffix in {".csv", ".tsv", ".txt"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                sample = f.read(2048)
                f.seek(0)
                if suffix in {".csv", ".txt"}:
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                        delimiter = dialect.delimiter
                    except Exception:
                        delimiter = "," if "," in sample else "\t"
                reader = csv.reader(f, delimiter=delimiter)
                rows = list(reader)
            if rows:
                result["headers"] = rows[0]
                result["rows"] = rows[1:1 + max_rows]
            return result

        if suffix in {".xlsx", ".xls"}:
            result["error"] = "当前环境未启用 Excel 预览，请先转成 CSV/TSV，或后续再补 Excel 解析。"
            return result

        result["error"] = "当前文件类型暂不支持预览。"
        return result
    except Exception as e:
        result["error"] = f"预览失败：{e}"
        return result


def infer_column_checks(path: Path, headers: list[str]):
    normalized_headers = [h.strip().lower() for h in headers if h is not None]

    def find_match(candidates: list[str]):
        for candidate in candidates:
            if candidate.lower() in normalized_headers:
                return candidate
        return ""

    def has_any(*candidates: str):
        return bool(find_match(list(candidates)))

    folder_hint = "/".join(path.parts[-3:]).lower()
    checks = []
    mapping_rules = {}

    if "gene_omics" in folder_hint:
        mapping_rules = {
            "gene": ["gene", "symbol", "gene_symbol", "gene symbol"],
            "log2fc": ["log2fc", "logfc", "log2_fc", "log2 fold change"],
            "pvalue": ["pvalue", "p_value", "p.value", "p val"],
            "padj": ["padj", "fdr", "adj_p", "adj_pval", "adj.p.val"],
        }
        checks = [
            ("gene", has_any("gene", "symbol", "gene_symbol")),
            ("log2fc", has_any("log2fc", "logfc", "log2_fc")),
            ("pvalue", has_any("pvalue", "p_value", "p.value")),
            ("padj", has_any("padj", "fdr", "adj_p", "adj_pval")),
        ]
    elif "targets" in folder_hint:
        mapping_rules = {
            "compound_name": ["compound_name", "compound", "ingredient", "compound name"],
            "target": ["target", "gene", "symbol", "gene_symbol"],
            "probability": ["probability", "score", "confidence"],
        }
        checks = [
            ("compound_name", has_any("compound_name", "compound", "ingredient")),
            ("target", has_any("target", "gene", "symbol")),
            ("probability", has_any("probability", "score", "confidence")),
        ]
    elif "disease" in folder_hint:
        mapping_rules = {
            "gene": ["gene", "symbol", "gene_symbol", "gene symbol"],
            "score": ["score", "relevance", "confidence"],
            "disease": ["disease", "phenotype"],
        }
        checks = [
            ("gene", has_any("gene", "symbol", "gene_symbol")),
            ("score", has_any("score", "relevance", "confidence")),
            ("disease", has_any("disease", "phenotype")),
        ]
    elif "enrichment" in folder_hint:
        mapping_rules = {
            "term": ["term", "description", "pathway"],
            "pvalue": ["pvalue", "p_value", "p.adjust", "padj", "adj.p.val"],
            "count": ["count", "gene_count", "genes"],
        }
        checks = [
            ("term", has_any("term", "description", "pathway")),
            ("pvalue", has_any("pvalue", "p_value", "p.adjust", "padj")),
            ("count", has_any("count", "gene_count", "genes")),
        ]
    elif "network" in folder_hint:
        mapping_rules = {
            "gene": ["gene", "symbol", "target"],
            "source": ["source", "from"],
            "target": ["target", "to"],
        }
        checks = [
            ("gene", has_any("gene", "symbol", "target")),
            ("source", has_any("source", "from")),
            ("target", has_any("target", "to")),
        ]
    else:
        mapping_rules = {
            "gene/target": ["gene", "symbol", "target"],
            "score/pvalue": ["score", "pvalue", "p_value", "padj"],
        }
        checks = [
            ("gene/target", has_any("gene", "symbol", "target")),
            ("score/pvalue", has_any("score", "pvalue", "p_value", "padj")),
        ]

    found = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    suggested_mappings = []
    for canonical, candidates in mapping_rules.items():
        matched = find_match(candidates)
        if matched:
            suggested_mappings.append({"from": matched, "to": canonical})

    return {
        "found": found,
        "missing": missing,
        "folder_hint": folder_hint,
        "suggested_mappings": suggested_mappings,
    }


def suggest_dataset_type(path: Path, headers: list[str]):
    normalized_headers = {h.strip().lower() for h in headers if h is not None}
    folder_hint = "/".join(path.parts[-3:]).lower()

    candidates = [
        {
            "type": "DEG / Gene 表",
            "score": 0,
            "reasons": [],
        },
        {
            "type": "成分靶点表",
            "score": 0,
            "reasons": [],
        },
        {
            "type": "疾病靶点表",
            "score": 0,
            "reasons": [],
        },
        {
            "type": "交集 / 网络表",
            "score": 0,
            "reasons": [],
        },
        {
            "type": "富集结果表",
            "score": 0,
            "reasons": [],
        },
    ]

    def add_score(type_name: str, points: int, reason: str):
        for item in candidates:
            if item["type"] == type_name:
                item["score"] += points
                item["reasons"].append(reason)
                break

    if "gene_omics" in folder_hint:
        add_score("DEG / Gene 表", 2, "文件位于 gene_omics 目录")
    if "targets" in folder_hint:
        add_score("成分靶点表", 2, "文件位于 targets 目录")
    if "disease" in folder_hint:
        add_score("疾病靶点表", 2, "文件位于 disease 目录")
    if "network" in folder_hint:
        add_score("交集 / 网络表", 2, "文件位于 network 目录")
    if "enrichment" in folder_hint:
        add_score("富集结果表", 2, "文件位于 enrichment 目录")

    if {"gene", "symbol", "gene_symbol"} & normalized_headers:
        add_score("DEG / Gene 表", 1, "存在 gene/symbol 类列名")
        add_score("疾病靶点表", 1, "存在 gene/symbol 类列名")
        add_score("交集 / 网络表", 1, "存在 gene/symbol 类列名")
    if {"log2fc", "logfc", "log2_fc"} & normalized_headers:
        add_score("DEG / Gene 表", 2, "存在 log2FC 类列名")
    if {"pvalue", "p_value", "p.value", "padj", "adj.p.val", "fdr"} & normalized_headers:
        add_score("DEG / Gene 表", 1, "存在 P 值 / 校正 P 值类列名")
        add_score("富集结果表", 1, "存在 P 值 / 校正 P 值类列名")
    if {"compound_name", "compound", "ingredient"} & normalized_headers:
        add_score("成分靶点表", 2, "存在 compound/ingredient 类列名")
    if {"target", "targets"} & normalized_headers:
        add_score("成分靶点表", 1, "存在 target 类列名")
        add_score("交集 / 网络表", 1, "存在 target 类列名")
    if {"score", "confidence", "relevance"} & normalized_headers:
        add_score("疾病靶点表", 1, "存在 score/confidence 类列名")
        add_score("成分靶点表", 1, "存在 score/confidence 类列名")
    if {"term", "description", "pathway"} & normalized_headers:
        add_score("富集结果表", 2, "存在 term/pathway 类列名")
    if {"count", "gene_count", "genes"} & normalized_headers:
        add_score("富集结果表", 1, "存在 count/genes 类列名")
    if {"source", "from"} & normalized_headers:
        add_score("交集 / 网络表", 1, "存在 source/from 类列名")
    if {"to"} & normalized_headers:
        add_score("交集 / 网络表", 1, "存在 to 类列名")

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    return {
        "type": best["type"],
        "score": best["score"],
        "reasons": best["reasons"][:4],
    }


env.globals["current_project"] = get_current_project
env.globals["runtime_status"] = get_runtime_status

@app.get("/", response_class=HTMLResponse)
def index():
    today = read(ROOT / "01_今日打工" / "今日任务.md")
    current_project = get_current_project()
    if current_project:
        overview = "\n".join(
            [
                f"项目名称：{current_project.get('name', '')}",
                f"项目简称：{current_project.get('short_name', '')}",
                f"研究类型：{current_project.get('category', '')}",
                f"研究对象：{current_project.get('research_object', '')}",
                f"疾病 / 模型：{current_project.get('disease', '')}",
                f"当前阶段：{current_project.get('stage', '')}",
                f"项目状态：{current_project.get('status', '')}",
            ]
        )
    else:
        overview = "尚未选择当前项目。"
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
    return template.render(
        today=today,
        overview=overview,
        modules=MODULES,
        recent=recent,
        active_project=current_project,
    )

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


@app.get("/media")
def media_file(path: str):
    p = ROOT / path
    if not p.exists() or not p.is_file():
        return HTMLResponse("文件不存在", status_code=404)

    suffix = p.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    media_type = media_types.get(suffix)
    if not media_type:
        return HTMLResponse("当前文件不是支持预览的图片格式", status_code=400)
    return FileResponse(p, media_type=media_type, filename=p.name)

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


@app.get("/data-import", response_class=HTMLResponse)
def data_import_page():
    current_project = get_current_project()
    recent_imports = get_recent_project_imports()
    imported_files = []
    for items in recent_imports.values():
        imported_files.extend(items)

    template = env.get_template("data_import/index.html")
    return template.render(
        modules=MODULES,
        active_project=current_project,
        imported_files=imported_files[:20],
        recent_imports=recent_imports,
    )


@app.get("/data-import/preview", response_class=HTMLResponse)
def data_import_preview(path: str, note: str = "", selected_type: str = ""):
    file_path = ROOT / path
    preview = get_table_preview(file_path)
    column_checks = infer_column_checks(file_path, preview.get("headers", [])) if not preview.get("error") else None
    type_suggestion = suggest_dataset_type(file_path, preview.get("headers", [])) if not preview.get("error") else None
    selected_type_labels = {
        "deg": "DEG / Gene 表",
        "compound_targets": "成分靶点表",
        "disease_targets": "疾病靶点表",
        "intersection": "交集基因 / 交集靶点表",
        "enrichment": "GO / KEGG / 富集结果表",
        "general": "通用数据表",
    }
    selected_type_label = selected_type_labels.get(selected_type, "")
    type_mismatch = bool(
        selected_type_label
        and type_suggestion
        and selected_type_label != type_suggestion.get("type", "")
    )
    template = env.get_template("data_import/preview.html")
    return template.render(
        modules=MODULES,
        active_project=get_current_project(),
        path=path,
        note=note,
        preview=preview,
        column_checks=column_checks,
        type_suggestion=type_suggestion,
        selected_type=selected_type,
        selected_type_label=selected_type_label,
        type_mismatch=type_mismatch,
    )


@app.post("/data-import/upload")
def data_import_upload(
    dataset_name: str = Form(...),
    data_type: str = Form(...),
    file: UploadFile = File(...),
):
    current_project = get_current_project()
    project_root = get_current_project_root()
    if not current_project or not project_root:
        return HTMLResponse("请先在项目中心选择当前项目。", status_code=400)

    folder_map = {
        "deg": "gene_omics",
        "compound_targets": "targets",
        "disease_targets": "disease",
        "intersection": "network",
        "enrichment": "enrichment",
        "general": "data",
    }
    target_folder = folder_map.get(data_type, "data")
    out_dir = project_root / target_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix
    if suffix.lower() not in {".csv", ".xlsx", ".xls", ".tsv", ".txt"}:
        return HTMLResponse("仅支持 csv、xlsx、xls、tsv、txt 文件。", status_code=400)

    filename = f"{date.today().isoformat()}_{safe_name(dataset_name)}{suffix.lower()}"
    file_path = out_dir / filename
    file_path.write_bytes(file.file.read())

    note_dir = ROOT / "05_数据分析" / "科研作图"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / f"{date.today().isoformat()}_{safe_name(dataset_name)}_数据导入记录.md"
    if not note_path.exists():
        note_path.write_text(
            f"""# 数据导入记录｜{dataset_name}

## 日期
{date.today().isoformat()}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 项目编号：{current_project.get('project_id', '')}

## 数据类型
- 类型：{data_type}
- 保存目录：projects/{current_project.get('project_id', '')}/{target_folder}

## 原始文件
- 文件名：{file.filename}
- 保存后文件：{filename}

## 后续建议
- [ ] 检查列名是否标准化
- [ ] 检查基因名 / 靶点名是否去重
- [ ] 进入交集分析
- [ ] 进入可视化
- [ ] 进入 Results 写作
""",
            encoding="utf-8",
        )

    return RedirectResponse(
        url=(
            f"/data-import/preview?path={file_path.relative_to(ROOT)}"
            f"&note={note_path.relative_to(ROOT)}"
            f"&selected_type={data_type}"
        ),
        status_code=303,
    )


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
    current_project = get_current_project() or {}
    template = env.get_template("experiment/index.html")
    return template.render(items=items, active_project=current_project)


@app.get("/experiment-dashboard", response_class=HTMLResponse)
def experiment_dashboard():
    current_project = get_current_project() or {}
    summary = get_experiment_dashboard_summary()
    writing_items = get_validation_writing_outputs()
    template = env.get_template("experiment_dashboard/index.html")
    return template.render(
        active_project=current_project,
        modules=summary["modules"],
        active_count=summary["active_count"],
        ready_count=summary["ready_count"],
        empty_modules=summary["empty_modules"],
        figure_ready=summary["figure_ready"],
        results_ready=summary["results_ready"],
        methods_ready=summary["methods_ready"],
        figure_suggestions=summary["figure_suggestions"],
        results_suggestions=summary["results_suggestions"],
        methods_suggestions=summary["methods_suggestions"],
        writing_items=writing_items,
    )


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
    current_project = get_current_project()
    recent_imports = get_recent_project_imports()
    figure_context = build_network_figure_context()
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("figure/index.html")
    return template.render(
        items=items,
        modules=MODULES,
        active_project=current_project,
        recent_imports=recent_imports,
        figure_context=figure_context,
    )

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


@app.post("/figure/network-package/new")
def figure_network_package_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "科研作图"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_网络药理图表包.md"
    context = build_network_figure_context()
    current_project = context["current_project"]
    intersection_path = context["intersection_path"]
    enrichment_path = context["enrichment_path"]
    target_path = context["target_path"]
    disease_path = context["disease_path"]
    figure_input_summary_text = context["input_summary_text"]
    recommendations = context["recommendations"]
    recommendation_text = "\n".join(
        [
            f"- {item['name']}（{item['priority']}）：{item['reason']}"
            for item in recommendations
        ]
    )
    legend_checklist = build_network_legend_checklist(recommendations)
    legend_bundle = build_network_legend_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
    )
    results_bundle = build_network_results_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
    )
    discussion_bundle = build_network_discussion_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    validation_bundle = build_network_validation_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    experiment_bundle = build_network_experiment_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    methods_bundle = build_network_methods_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    introduction_bundle = build_network_introduction_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    abstract_bundle = build_network_abstract_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    cover_letter_bundle = build_network_cover_letter_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    graphical_abstract_bundle = build_network_graphical_abstract_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    highlights_bundle = build_network_highlights_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    conclusion_bundle = build_network_conclusion_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    keywords_bundle = build_network_keywords_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    title_bundle = build_network_title_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    content = f"""# 网络药理图表包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 图表任务清单
- [ ] Venn 图
- [ ] UpSet 图
- [ ] 成分-靶点网络图
- [ ] PPI 网络图
- [ ] GO 气泡图
- [ ] KEGG 气泡图
- [ ] 核心靶点柱状图
- [ ] Figure legend 草稿

## 输入文件
- 成分表：
- 成分-靶点边表：{target_path}
- 疾病靶点表：{disease_path}
- 交集基因表：{intersection_path}
- PPI 文件：
- GO 结果：{enrichment_path}
- KEGG 结果：{enrichment_path}

## 最近输入摘要
{figure_input_summary_text}

## 推荐优先顺序
{recommendation_text}

## 输出文件位置
- PNG：
- SVG / PDF：
- CSV：

## 图风格说明
- 用途（汇报 / 论文 / 投稿）：
- 颜色方案：
- 字体要求：
- 是否需要 Cytoscape 精修：

## 标准图注清单
{legend_checklist}

{legend_bundle}

{results_bundle}

{discussion_bundle}

{validation_bundle}

{experiment_bundle}

{methods_bundle}

{introduction_bundle}

{abstract_bundle}

{cover_letter_bundle}

{graphical_abstract_bundle}

{highlights_bundle}

{conclusion_bundle}

{keywords_bundle}

{title_bundle}

## 图注草稿
- Figure 1：
- Figure 2：
- Supplementary：

## 后续衔接
- [ ] 进入 Docking 候选筛选
- [ ] 进入 Results 写作
- [ ] 进入 Discussion 写作

## 风险点
- 图表是否信息过载：
- 标签是否重叠：
- 输入数据是否已去重：
- 是否需要只保留 Top 10 / 20：
"""
    if not file_path.exists():
        file_path.write_text(content, encoding="utf-8")
    else:
        existing = file_path.read_text(encoding="utf-8")
        changed = False
        if "## 推荐优先顺序" not in existing:
            existing = existing.rstrip() + f"""

## 推荐优先顺序
{recommendation_text}
"""
            changed = True
        if "## 标准图注清单" not in existing:
            existing = existing.rstrip() + f"""

## 标准图注清单
{legend_checklist}
"""
            changed = True
        if "## 建议图号分配" not in existing:
            existing = existing.rstrip() + f"""

{legend_bundle}
"""
            changed = True
        if "## Results 段落初稿" not in existing:
            existing = existing.rstrip() + f"""

{results_bundle}
"""
            changed = True
        if "## Discussion 过渡与机制解释草稿" not in existing:
            existing = existing.rstrip() + f"""

{discussion_bundle}
"""
            changed = True
        if "## Docking / WB / qPCR 验证建议" not in existing:
            existing = existing.rstrip() + f"""

{validation_bundle}
"""
            changed = True
        if "## 实验分组建议 + 指标清单" not in existing:
            existing = existing.rstrip() + f"""

{experiment_bundle}
"""
            changed = True
        if "## Methods 初稿" not in existing:
            existing = existing.rstrip() + f"""

{methods_bundle}
"""
            changed = True
        if "## Introduction 初稿" not in existing:
            existing = existing.rstrip() + f"""

{introduction_bundle}
"""
            changed = True
        if "## Abstract 初稿" not in existing:
            existing = existing.rstrip() + f"""

{abstract_bundle}
"""
            changed = True
        if "## Cover Letter 初稿" not in existing:
            existing = existing.rstrip() + f"""

{cover_letter_bundle}
"""
            changed = True
        if "## Graphical Abstract 要点" not in existing:
            existing = existing.rstrip() + f"""

{graphical_abstract_bundle}
"""
            changed = True
        if "## Highlights 初稿" not in existing:
            existing = existing.rstrip() + f"""

{highlights_bundle}
"""
            changed = True
        if "## Conclusion 初稿" not in existing:
            existing = existing.rstrip() + f"""

{conclusion_bundle}
"""
            changed = True
        if "## Keywords 初稿" not in existing:
            existing = existing.rstrip() + f"""

{keywords_bundle}
"""
            changed = True
        if "## Title 备选初稿" not in existing:
            existing = existing.rstrip() + f"""

{title_bundle}
"""
            changed = True
        if changed:
            file_path.write_text(existing + "\n", encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/figure/network-package/auto")
def figure_network_package_auto():
    context = build_network_figure_context()
    if not context["readiness"]["can_auto_create"]:
        return RedirectResponse(url="/figure", status_code=303)
    return figure_network_package_new(title=context["auto_title"])


@app.get("/writing", response_class=HTMLResponse)
def writing_index():
    files = list_md("06_论文写作")
    current_project = get_current_project()
    recent_figures = get_recent_notes("05_数据分析/科研作图", limit=5)
    recent_figure_packages = get_recent_figure_packages(limit=5)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=5)
    items = []
    for file in files[:30]:
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
    template = env.get_template("writing/index.html")
    return template.render(
        items=items,
        modules=MODULES,
        active_project=current_project,
        recent_figures=recent_figures,
        recent_figure_packages=recent_figure_packages,
        recent_network=recent_network,
    )


def build_submission_checklist_summary():
    writing_files = list_md("06_论文写作")
    figure_files = list_md("05_数据分析/科研作图")
    figure_packages = get_recent_figure_packages(limit=20)

    def normalize(name: str) -> str:
        return name.lower().replace(" ", "_").replace("-", "_")

    writing_index = []
    for file in writing_files:
        writing_index.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "normalized": normalize(file.name),
        })

    figure_index = []
    for file in figure_files:
        figure_index.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "normalized": normalize(file.name),
        })

    figure_package_index = []
    for item in figure_packages:
        figure_package_index.append({
            "name": item["name"],
            "path": item["path"],
            "normalized": normalize(item["name"]),
        })

    def find_match(pool, keywords):
        for item in pool:
            normalized = item["normalized"]
            if all(keyword in normalized for keyword in keywords):
                return item
        return None

    checklist_sections = [
        {
            "title": "主文与整合稿",
            "items": [
                {
                    "label": "网络药理 + 实验验证整合总稿",
                    "keywords": ["network", "validation", "master"],
                    "pool": "writing",
                },
                {
                    "label": "实验验证总控包",
                    "keywords": ["full", "validation", "master"],
                    "pool": "writing",
                },
                {
                    "label": "投稿总包 Submission Package",
                    "keywords": ["submission", "package"],
                    "pool": "writing",
                },
                {
                    "label": "Methods 初稿 / 方法整合",
                    "keywords": ["methods"],
                    "pool": "writing",
                },
            ],
        },
        {
            "title": "Figure 与补充材料",
            "items": [
                {
                    "label": "网络药理图表包",
                    "keywords": ["network", "figure", "package"],
                    "pool": "figure_package",
                },
                {
                    "label": "Figure Legend / Results 草稿",
                    "keywords": ["figure", "legend"],
                    "pool": "writing",
                },
                {
                    "label": "WB / qPCR 全验证包",
                    "keywords": ["wb", "qpcr", "full", "validation", "package"],
                    "pool": "writing",
                },
                {
                    "label": "CCK-8 全包",
                    "keywords": ["cck8", "full", "package"],
                    "pool": "writing",
                },
                {
                    "label": "Figure 文件清单",
                    "keywords": ["figure", "manifest"],
                    "pool": "writing",
                },
                {
                    "label": "Supplementary 清单",
                    "keywords": ["supplementary", "checklist"],
                    "pool": "writing",
                },
            ],
        },
        {
            "title": "投稿与返修文件",
            "items": [
                {
                    "label": "Cover Letter",
                    "keywords": ["cover", "letter"],
                    "pool": "writing",
                },
                {
                    "label": "Response Letter",
                    "keywords": ["response", "letter"],
                    "pool": "writing",
                },
                {
                    "label": "审稿意见拆分稿",
                    "keywords": ["reviewer"],
                    "pool": "writing",
                },
                {
                    "label": "原始数据归档清单",
                    "keywords": ["rawdata", "archive"],
                    "pool": "writing",
                },
                {
                    "label": "最终投稿 Checklist",
                    "keywords": ["final", "submission", "checklist"],
                    "pool": "writing",
                },
            ],
        },
    ]

    pool_mapping = {
        "writing": writing_index,
        "figure": figure_index,
        "figure_package": figure_package_index,
    }

    ready_count = 0
    missing_count = 0
    sections = []
    missing_items = []
    section_summaries = []

    for section in checklist_sections:
        rendered_items = []
        section_ready = 0
        section_total = len(section["items"])
        for item in section["items"]:
            matched = find_match(pool_mapping[item["pool"]], item["keywords"])
            status = "ready" if matched else "missing"
            if matched:
                ready_count += 1
                section_ready += 1
            else:
                missing_count += 1
                missing_items.append(item["label"])
            rendered_items.append({
                "label": item["label"],
                "status": status,
                "matched": matched,
            })
        sections.append({
            "title": section["title"],
            "entries": rendered_items,
        })
        percent = int((section_ready / section_total) * 100) if section_total else 0
        section_summaries.append({
            "title": section["title"],
            "ready": section_ready,
            "total": section_total,
            "percent": percent,
        })

    recent_submission_items = []
    for item in writing_index:
        if any(keyword in item["normalized"] for keyword in [
            "submission",
            "response",
            "cover",
            "reviewer",
            "master",
            "validation",
            "figure",
        ]):
            recent_submission_items.append(item)
        if len(recent_submission_items) >= 8:
            break

    grouped_recent_items = {
        "主文 / 整合稿": [],
        "Figure / Supplementary": [],
        "投稿 / 返修": [],
    }
    for item in recent_submission_items:
        normalized = item["normalized"]
        if any(keyword in normalized for keyword in ["master", "submission", "methods", "validation"]):
            grouped_recent_items["主文 / 整合稿"].append(item)
        elif any(keyword in normalized for keyword in ["figure", "supplementary", "manifest", "rawdata"]):
            grouped_recent_items["Figure / Supplementary"].append(item)
        else:
            grouped_recent_items["投稿 / 返修"].append(item)

    next_action_map = {
        "网络药理 + 实验验证整合总稿": "先生成整合总稿，把网络药理和实验验证主线串成同一份投稿底稿。",
        "实验验证总控包": "补一份实验验证总控包，把 WB、qPCR、CCK-8 和功能验证统一归档。",
        "投稿总包 Submission Package": "生成 Submission Package，把标题、摘要、Highlights、Cover Letter 一次集中。",
        "Methods 初稿 / 方法整合": "优先补 Methods，避免投稿前还在回填实验与分析步骤。",
        "网络药理图表包": "先整理网络药理图表包，后续 Figure Legend 和投稿图件会更顺。",
        "Figure Legend / Results 草稿": "补 Figure Legend / Results 草稿，让图和正文同时成型。",
        "WB / qPCR 全验证包": "生成 WB / qPCR 全验证包，把分子验证结果和补充材料一次整理好。",
        "CCK-8 全包": "整理 CCK-8 全包，把细胞活力结果、统计和图注统一。",
        "Figure 文件清单": "生成 Figure 文件清单，先统一主图、补充图和 legend 的交付编号。",
        "Supplementary 清单": "生成 Supplementary 清单，防止投稿时遗漏表格和补充图。",
        "Cover Letter": "先补 Cover Letter，投稿时可以直接复制调整。",
        "Response Letter": "预先生成 Response Letter 模板，返修时能直接进入回复。",
        "审稿意见拆分稿": "准备审稿意见拆分模板，后续返修会更快。",
        "原始数据归档清单": "先做原始数据归档清单，避免投稿后找不到对应底稿。",
        "最终投稿 Checklist": "最后生成最终投稿 Checklist，作为提交前总核对清单。",
    }
    next_actions = []
    for label in missing_items[:5]:
        next_actions.append({
            "label": label,
            "description": next_action_map.get(label, "建议优先补齐这一项，完善投稿材料链条。"),
        })

    total_count = ready_count + missing_count
    readiness_percent = int((ready_count / total_count) * 100) if total_count else 0

    return {
        "total_count": total_count,
        "ready_count": ready_count,
        "missing_count": missing_count,
        "readiness_percent": readiness_percent,
        "sections": sections,
        "section_summaries": section_summaries,
        "missing_items": missing_items,
        "recent_submission_items": recent_submission_items,
        "grouped_recent_items": grouped_recent_items,
        "next_actions": next_actions,
    }


def build_submission_supplementary_bundle(project_name: str, disease_name: str):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(
        limit=12,
        heading="qPCR 原始图片自动编号清单",
    )
    qpcr_legend_block = build_qpcr_supplementary_legend_section(
        limit=12,
        heading="qPCR Supplementary Figure Legend 正式稿",
    )
    return f"""## Supplementary 文件建议清单
- Supplementary Figure S1：成分筛选或原始成分信息补充
- Supplementary Figure S2：PPI 或扩展网络结果补充
- Supplementary Figure S3：GO / KEGG 扩展富集结果
- Supplementary Figure S4：对接姿势补充图或额外成分-靶点结果
- Supplementary Figure S5：WB 原膜、qPCR 原始扩增信息、额外功能验证图

## Supplementary Table 建议清单
| 文件编号 | 建议名称 | 主要内容 |
|---|---|---|
| Table S1 | Compound list of {project_name} | 成分名称、CID、SMILES、筛选依据 |
| Table S2 | Predicted targets of {project_name} | 成分-靶点预测结果与来源数据库 |
| Table S3 | Disease-related targets for {disease_name} | 疾病靶点、筛选阈值、来源数据库 |
| Table S4 | Shared targets and hub genes | 交集靶点、核心靶点及网络指标 |
| Table S5 | GO and KEGG enrichment results | 富集结果明细、p值/FDR、基因数 |
| Table S6 | Docking scores and interaction summary | 对接能量、关键相互作用、候选排序 |
| Table S7 | Primer / antibody / reagent information | qPCR 引物、WB 抗体、关键试剂信息 |

## Supplementary 整理清单
- [ ] 所有 Supplementary Figure 均有标题和图注
- [ ] 所有 Supplementary Table 均有列名说明
- [ ] 原始图、原始表与正文中的结果一一对应
- [ ] Figure / Table 在正文首次提及时编号一致
- [ ] 文件格式统一为 PDF / XLSX / TIFF / CSV 的投稿要求格式

## 建议最终目录
- Supplementary_Figures/
- Supplementary_Tables/
- Raw_Data_Index/
- Figure_Legend_Supplementary/
- Method_Details_Extended/

{qpcr_registry_block}
"""


def build_submission_naming_guide_bundle(project_name: str, disease_name: str):
    return f"""## 投稿文件命名规范建议

### 主文文件
- Manuscript_MainText_{safe_name(project_name)}.docx
- Cover_Letter_{safe_name(project_name)}.docx
- Response_Letter_{safe_name(project_name)}.docx
- Highlights_{safe_name(project_name)}.docx
- Graphical_Abstract_{safe_name(project_name)}.pptx

### Figure 文件
- Figure1_Study_Design.tif
- Figure2_Component_Target_Network.tif
- Figure3_PPI_and_Enrichment.tif
- Figure4_Docking_and_Core_Targets.tif
- Figure5_WB_qPCR_Functional_Validation.tif

### Supplementary 文件
- Supplementary_Figure_S1_Component_Screening.tif
- Supplementary_Figure_S2_Extended_PPI.tif
- Supplementary_Table_S1_Compound_List.xlsx
- Supplementary_Table_S2_Target_List.xlsx
- Supplementary_Table_S3_Enrichment_Results.xlsx

### 原始数据文件
- RawData_WB_{safe_name(disease_name)}.zip
- RawData_qPCR_{safe_name(disease_name)}.xlsx
- RawData_CCK8_{safe_name(disease_name)}.xlsx
- RawData_Docking_{safe_name(project_name)}.csv

## 命名统一规则
- 只使用英文字母、数字、下划线
- 不在最终投稿文件中使用空格和中文
- 同一类型文件编号连续，不跳号
- Figure / Table / Supplementary 的编号必须与正文一致
- 最终归档前检查大小写和缩写是否统一

## 投稿前最终核对
- [ ] 主文文件名与期刊要求一致
- [ ] Figure 文件名与图注编号一致
- [ ] Supplementary 文件名与正文引用一致
- [ ] 原始数据文件与补充材料可一一对应
- [ ] 所有最终文件放入同一投稿归档目录
"""


def build_submission_figure_manifest_bundle(project_name: str, disease_name: str):
    return f"""## Figure 文件清单
| Figure 编号 | 建议文件名 | 主要内容 | 建议格式 |
|---|---|---|---|
| Figure 1 | Figure1_Study_Design.tif | 研究流程、技术路线、整体设计 | TIFF / PDF |
| Figure 2 | Figure2_Component_Target_Network.tif | 成分-靶点网络与关键成分信息 | TIFF / SVG |
| Figure 3 | Figure3_PPI_and_Enrichment.tif | PPI、GO、KEGG 结果主图 | TIFF / SVG |
| Figure 4 | Figure4_Docking_and_Core_Targets.tif | 核心靶点与分子对接结果 | TIFF / PDF |
| Figure 5 | Figure5_Functional_Validation.tif | CCK-8、WB、qPCR、功能验证 | TIFF / PDF |

## Figure 配套材料
- Figure_Legends_{safe_name(project_name)}.docx
- Graphical_Abstract_{safe_name(project_name)}.pptx
- Supplementary_Figure_S1_to_S5.pdf

## Figure 交付核对
- [ ] 每张 Figure 都有最终编号
- [ ] 每张 Figure 都有对应 legend
- [ ] 主图与补充图编号不混淆
- [ ] 图片分辨率满足期刊要求
- [ ] 所有统计标记与结果段一致
- [ ] 文件名与正文引用完全一致

## 推荐归档目录
- Figures/Main_Figures/
- Figures/Supplementary_Figures/
- Figures/Graphical_Abstract/
- Figures/Figure_Legends/
"""


def build_submission_rawdata_archive_bundle(project_name: str, disease_name: str):
    return f"""## 原始数据归档清单
| 数据类型 | 建议文件名 | 说明 |
|---|---|---|
| UPLC / 成分原始数据 | RawData_UPLC_{safe_name(project_name)}.zip | 原始谱图、峰表、成分识别记录 |
| 网络药理输入表 | RawData_Network_Input_{safe_name(project_name)}.xlsx | 成分、靶点、疾病靶点、交集表 |
| 富集分析结果 | RawData_Enrichment_{safe_name(project_name)}.xlsx | GO / KEGG / Reactome 明细 |
| Docking 原始结果 | RawData_Docking_{safe_name(project_name)}.csv | 对接能量、相互作用、候选排序 |
| CCK-8 原始数据 | RawData_CCK8_{safe_name(disease_name)}.xlsx | OD 值、均值、SD、统计结果 |
| WB 原始图像 | RawData_WB_{safe_name(disease_name)}.zip | 原膜、裁切图、定量表 |
| qPCR 原始数据 | RawData_qPCR_{safe_name(disease_name)}.xlsx | Ct 值、2^-ΔΔCt 计算、统计结果 |
| 其他功能验证 | RawData_Functional_{safe_name(disease_name)}.zip | ROS、JC-1、流式、IF 等 |

## 原始数据归档原则
- [ ] 每类数据保留原始文件与整理后文件
- [ ] Excel / CSV 中保留原始数值，不只保留图片
- [ ] 图片类原始数据与统计表一一对应
- [ ] 每个归档文件包含简短 readme 说明
- [ ] 文件名与论文图号、实验名称保持一致

## 推荐目录结构
- Raw_Data/UPLC/
- Raw_Data/Network/
- Raw_Data/Docking/
- Raw_Data/CCK8/
- Raw_Data/WB/
- Raw_Data/qPCR/
- Raw_Data/Functional/
"""


def build_submission_final_checklist_bundle(project_name: str, disease_name: str):
    qpcr_registry_block = build_qpcr_supplementary_registry_section(
        limit=12,
        heading="qPCR 图片 Supplementary 自动编号核对",
    )
    qpcr_bilingual_legend_block = build_qpcr_supplementary_bilingual_legend_section(
        limit=12,
        heading="qPCR Supplementary Figure Legend 中英双语核对稿",
    )
    return f"""## 期刊提交前最终 Checklist

### 主文与基础文件
- [ ] Main manuscript 已定稿
- [ ] Title / Abstract / Keywords 已最终确认
- [ ] Cover Letter 已按目标期刊调整
- [ ] Highlights / Graphical Abstract 已完成

### Figure 与 Supplementary
- [ ] 所有主图编号、图注、正文引用一致
- [ ] Supplementary Figure / Table 已编号完成
- [ ] qPCR Supplementary Figure 的中英双语图注已核对
- [ ] Figure 文件名已改为英文规范命名
- [ ] 所有图片分辨率和格式符合期刊要求

### 数据与方法
- [ ] 原始数据归档包已整理
- [ ] Methods 细节足以支持重复实验
- [ ] 统计学方法、软件版本、阈值已写清
- [ ] WB / qPCR / CCK-8 / 其他功能验证数据与正文一致

### 投稿与返修准备
- [ ] Submission Package 已整理
- [ ] 文件命名规范已统一
- [ ] 作者信息、单位、基金号已核对
- [ ] 利益冲突、伦理、数据可用性声明已补齐
- [ ] 返修模板与 Reviewer Response 模板已预留

### 最终归档
- [ ] 建立 Final_Submission_{safe_name(project_name)} 目录
- [ ] 建立 Raw_Data_{safe_name(project_name)} 目录
- [ ] 建立 Supplementary_{safe_name(project_name)} 目录
- [ ] 生成最终提交前版本号记录

{qpcr_registry_block}

{qpcr_bilingual_legend_block}

## 最终提交目录建议
- Final_Submission/
- Supplementary/
- Raw_Data/
- Response_Package/
- Journal_Requirements/
"""


def build_submission_toolkit_bundle(project_name: str, disease_name: str):
    return f"""## 投稿工具包总览

### 主文与整合稿
- Network_Validation_Master：网络药理与实验验证整合总稿
- Full_Validation_Master：实验验证总控包
- Submission_Package：投稿总包
- Methods_Draft：方法学整合稿

### Figure 与补充材料
- Figure_Manifest：主图与补充图交付清单
- Supplementary_Checklist：补充材料整理清单
- Submission_Naming_Guide：统一命名规范
- RawData_Archive：原始数据归档清单

### 投稿与返修
- Cover_Letter：投稿信
- Response_Letter：返修回复
- Reviewer_Split：审稿意见拆分稿
- Final_Submission_Checklist：提交前最终核对单

## 推荐使用顺序
1. 先完成 {project_name} 针对 {disease_name} 的整合总稿。
2. 再整理 Figure、Supplementary 和 Raw Data 归档。
3. 最后生成 Cover Letter、Submission Package 和 Final Checklist。

## 最终归档总目录
- 01_Main_Manuscript/
- 02_Figures/
- 03_Supplementary/
- 04_Raw_Data/
- 05_Submission_Package/
- 06_Response_Package/

## 一键核对
- [ ] 主文、图表、补充材料、原始数据均已齐全
- [ ] 投稿文件命名已统一
- [ ] 期刊要求的特殊文件已补齐
- [ ] 可直接进入在线投稿系统提交
"""


def build_submission_journal_template_context(journal: str, project_name: str, disease_name: str):
    journal_labels = {
        "generic": "通用投稿模板",
        "phytomedicine": "Phytomedicine",
        "joe": "Journal of Ethnopharmacology",
    }
    selected_journal = journal if journal in journal_labels else "generic"
    return {
        "selected_journal": selected_journal,
        "journal_label": journal_labels[selected_journal],
        "journal_options": [
            {"value": "generic", "label": "通用投稿模板"},
            {"value": "phytomedicine", "label": "Phytomedicine"},
            {"value": "joe", "label": "Journal of Ethnopharmacology"},
        ],
        "preset_bundle": build_journal_preset_bundle(selected_journal, project_name, disease_name),
        "cover_bundle": build_journal_cover_letter_style_bundle(selected_journal, project_name, disease_name),
        "highlights_bundle": build_journal_highlights_style_bundle(selected_journal, project_name, disease_name),
        "graphical_bundle": build_journal_graphical_abstract_style_bundle(selected_journal, project_name, disease_name),
        "cover_full_bundle": build_journal_cover_letter_full_draft_bundle(selected_journal, project_name, disease_name),
        "highlights_full_bundle": build_journal_highlights_full_draft_bundle(selected_journal, project_name, disease_name),
    }


@app.get("/submission", response_class=HTMLResponse)
def submission_index(journal: str = "generic"):
    files = list_md("06_论文写作")
    current_project = get_current_project()
    current_project = current_project or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    recent_figure_packages = get_recent_figure_packages(limit=5)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=5)
    checklist = build_submission_checklist_summary()
    journal_context = build_submission_journal_template_context(journal, project_name, disease_name)
    items = []
    for file in files[:30]:
        lower = file.name.lower()
        if not any(keyword in lower for keyword in [
            "submission",
            "response",
            "cover",
            "master",
            "validation",
            "figure",
            "supplementary",
            "reviewer",
        ]):
            continue
        items.append({
            "name": file.name,
            "path": str(file.relative_to(ROOT)),
            "content": read(file)[:500]
        })
        if len(items) >= 20:
            break
    template = env.get_template("submission/index.html")
    return template.render(
        items=items,
        modules=MODULES,
        active_project=current_project,
        recent_figure_packages=recent_figure_packages,
        recent_network=recent_network,
        checklist=checklist,
        journal_context=journal_context,
    )


@app.post("/writing/submission-supplementary/new")
def writing_submission_supplementary_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Supplementary_Checklist.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    recent_figure_packages = get_recent_figure_packages(limit=5)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=5)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    bundle = build_submission_supplementary_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Supplementary Checklist｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{bundle}

## 最终补充材料目录

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/submission-naming-guide/new")
def writing_submission_naming_guide_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Submission_Naming_Guide.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    bundle = build_submission_naming_guide_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Submission Naming Guide｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

{bundle}

## 最终文件归档路径

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/submission-figure-manifest/new")
def writing_submission_figure_manifest_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Figure_Manifest.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    bundle = build_submission_figure_manifest_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Figure Manifest｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

{bundle}

## 最终 Figure 交付记录

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/submission-rawdata-archive/new")
def writing_submission_rawdata_archive_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_RawData_Archive.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    bundle = build_submission_rawdata_archive_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Raw Data Archive｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

{bundle}

## 最终原始数据归档路径

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/submission-final-checklist/new")
def writing_submission_final_checklist_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Final_Submission_Checklist.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    bundle = build_submission_final_checklist_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Final Submission Checklist｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

{bundle}

## 最终提交日期

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/submission-toolkit/new")
def writing_submission_toolkit_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Submission_Toolkit.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    checklist = build_submission_checklist_summary()
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    bundle = build_submission_toolkit_bundle(project_name, disease_name)
    missing_summary = "\n".join([f"- {item}" for item in checklist["missing_items"]]) if checklist["missing_items"] else "- 当前投稿核心材料已基本齐全。"

    if not file_path.exists():
        content = f"""# Submission Toolkit｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标期刊模板
- 模板代号：{journal}

{journal_bundle}

## 当前完成度
- 已就绪：{checklist['ready_count']}
- 待补齐：{checklist['missing_count']}
- 完成度：{checklist['readiness_percent']}%

## 当前待补齐项
{missing_summary}

{bundle}

## 最终提交备注

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/new")
def writing_new(title: str = Form(...), section_type: str = Form("discussion")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    recent_figures = get_recent_notes("05_数据分析/科研作图", limit=3)
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figures]
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_summary = "\n".join(figure_summary_lines) if figure_summary_lines else "- 当前暂无最近 Figure 记录。"
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    figure_context = build_network_figure_context()
    discussion_bundle = build_network_discussion_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    methods_bundle = build_network_methods_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    introduction_bundle = build_network_introduction_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    abstract_bundle = build_network_abstract_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    cover_letter_bundle = build_network_cover_letter_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    highlights_bundle = build_network_highlights_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    conclusion_bundle = build_network_conclusion_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    keywords_bundle = build_network_keywords_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    title_bundle = build_network_title_bundle(
        figure_context["recommendations"],
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    response_bundle = build_response_letter_bundle(
        "generic",
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    section_map = {
        "introduction": "Introduction",
        "methods": "Materials and Methods",
        "results": "Results",
        "discussion": "Discussion",
        "abstract": "Abstract",
        "cover": "Cover Letter",
        "highlights": "Highlights",
        "conclusion": "Conclusion",
        "keywords": "Keywords",
        "title": "Title Candidates",
        "response": "Response Letter"
    }

    if not file_path.exists():
        extra_results_context = ""
        if section_type == "results":
            extra_results_context = f"""

## 最近 Figure 记录
{figure_summary}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

## 推荐写作顺序
- 先描述图中观察到的结果
- 再说明统计差异
- 最后点出与机制相关的结论
"""
        extra_discussion_context = ""
        if section_type == "discussion":
            extra_discussion_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{discussion_bundle}
"""
        extra_methods_context = ""
        if section_type == "methods":
            extra_methods_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{methods_bundle}
"""
        extra_introduction_context = ""
        if section_type == "introduction":
            extra_introduction_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{introduction_bundle}
"""
        extra_abstract_context = ""
        if section_type == "abstract":
            extra_abstract_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{abstract_bundle}
"""
        extra_cover_context = ""
        if section_type == "cover":
            extra_cover_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{cover_letter_bundle}
"""
        extra_highlights_context = ""
        if section_type == "highlights":
            extra_highlights_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{highlights_bundle}
"""
        extra_conclusion_context = ""
        if section_type == "conclusion":
            extra_conclusion_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{conclusion_bundle}
"""
        extra_keywords_context = ""
        if section_type == "keywords":
            extra_keywords_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{keywords_bundle}
"""
        extra_title_context = ""
        if section_type == "title":
            extra_title_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{title_bundle}
"""
        extra_response_context = ""
        if section_type == "response":
            extra_response_context = f"""

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{response_bundle}
"""

        content = f"""# 论文写作｜{title}

## 日期
{today}

## 写作部分
{section_map.get(section_type, "Discussion")}

## 本部分目的

## 已有数据 / 图表

## 核心结论

## 需要引用的文献
{extra_results_context}{extra_discussion_context}{extra_methods_context}{extra_introduction_context}{extra_abstract_context}{extra_cover_context}{extra_highlights_context}{extra_conclusion_context}{extra_keywords_context}{extra_title_context}{extra_response_context}

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


@app.post("/writing/figure-draft/new")
def writing_figure_draft_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Figure_Legend_Results.md"
    current_project = get_current_project() or {}
    recent_figures = get_recent_notes("05_数据分析/科研作图", limit=3)
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figures]
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_summary = "\n".join(figure_summary_lines) if figure_summary_lines else "- 当前暂无最近 Figure 记录。"
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"

    if not file_path.exists():
        content = f"""# Figure Legend + Results 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 对应图号
- Figure：
- Supplementary Figure：

## 对应数据来源
- 原始数据：
- 统计结果：
- 图像文件：
- 对应图表包：

## 最近 Figure 记录
{figure_summary}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

## Figure Legend 草稿

### Figure 标题

### Legend 正文

### 缩写说明

## Results 草稿

### 结果段标题

### 结果正文

### 关键结论
- 

## 逻辑检查
- [ ] 图号与正文一致
- [ ] 统计方法已说明
- [ ] 显著性标注已说明
- [ ] 预测结果与验证结果区分清楚
- [ ] 没有超出图中数据的过度解释

## 可接入后续写作
- [ ] Discussion
- [ ] Abstract
- [ ] Cover Letter

## 待补充内容

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-discussion/new")
def writing_network_discussion_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Discussion_桥接草稿.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    discussion_bundle = build_network_discussion_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Discussion 桥接草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{discussion_bundle}

## Discussion 初稿

### 第一段：承接 Results

### 第二段：机制解释

### 第三段：与既往研究比较

### 第四段：后续验证与局限

## 待补充文献

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-validation/new")
def writing_network_validation_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Validation_Plan.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    validation_bundle = build_network_validation_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# 验证计划草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{validation_bundle}

## 待确定的核心靶点
- 靶点 1：
- 靶点 2：
- 靶点 3：

## 待确定的关键活性成分
- 成分 1：
- 成分 2：
- 成分 3：

## 实验安排草稿
- Docking：
- WB：
- qPCR：
- IF / ROS / 凋亡：

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-experiment/new")
def writing_network_experiment_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Experiment_Plan.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    experiment_bundle = build_network_experiment_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# 实验验证草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{experiment_bundle}

## 待确定关键蛋白
- 蛋白 1：
- 蛋白 2：
- 蛋白 3：

## 待确定 qPCR 基因
- 基因 1：
- 基因 2：
- 基因 3：

## 预期结果

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)




@app.post("/writing/wb-qpcr-validation/new")
def writing_wb_qpcr_validation_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Validation_Draft.md"
    current_project = get_current_project() or {}
    project_name = current_project.get('research_object', '') or current_project.get('name', '') or 'the project'
    disease_name = current_project.get('disease', '') or 'the disease model'
    recent_wb = get_recent_notes("03_实验记录/WB", limit=5)
    recent_qpcr = get_recent_notes("03_实验记录/qPCR", limit=5)
    wb_summary = "\n".join([f"- {item['name']}｜{item['path']}" for item in recent_wb]) if recent_wb else "- 当前暂无最近 WB 记录。"
    qpcr_summary = "\n".join([f"- {item['name']}｜{item['path']}" for item in recent_qpcr]) if recent_qpcr else "- 当前暂无最近 qPCR 记录。"
    wb_bundle = build_wb_experiment_bundle(project_name, disease_name)
    qpcr_bundle = build_qpcr_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# WB / qPCR 验证整合草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近 WB 记录
{wb_summary}

## 最近 qPCR 记录
{qpcr_summary}

{wb_bundle}

{qpcr_bundle}

## 联合验证逻辑
- 先用 qPCR 提供转录水平证据。
- 再用 WB 提供蛋白水平和通路活化证据。
- 若转录与蛋白变化一致，可增强机制链条的可信度。
- 若结果不一致，优先排查时间点、抗体 / 引物、样本质量和通路反馈调节。

## 建议图表组合
- Figure X：WB 条带图 + 灰度柱状图
- Figure Y：qPCR 相对表达柱状图
- Supplementary：原始 Ct 表、原始灰度值、抗体与引物清单

## Methods 整合骨架
- Western blot analysis was performed to evaluate the protein-level changes of the proposed targets and pathways.
- RT-qPCR was conducted to determine the transcriptional changes of the selected genes.
- The combined evidence from transcriptional and protein-level assays was used to validate the proposed mechanism.

## Results 整合骨架
- Compared with the model group, {project_name} modulated both the mRNA and protein expression profiles associated with {disease_name}.
- The qPCR and WB findings were generally consistent with the predicted targets and signaling pathways.
- These data provided convergent wet-lab evidence supporting the proposed mechanism.

## Discussion 承接句
- The combined qPCR and WB results strengthened the interpretation that {project_name} may regulate the selected pathway at both transcriptional and protein levels.
- This multi-level validation helped bridge the in silico predictions and the biological response observed in the experimental model.

## 修改记录
"""
        file_path.write_text(content, encoding='utf-8')

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/wb-qpcr-package/new")
def writing_wb_qpcr_package_new(
    title: str = Form(...),
    target_proteins: str = Form(""),
    target_genes: str = Form(""),
    wb_data: str = Form(""),
    qpcr_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Figure_Results_Supplementary.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    package_bundle = build_wb_qpcr_package_bundle(
        project_name,
        disease_name,
        target_proteins,
        target_genes,
        wb_data,
        qpcr_data,
    )

    if not file_path.exists():
        content = f"""# WB / qPCR 图注-结果-Supplementary 整合包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{package_bundle}

## 自定义补充说明

## 最终可复制段落

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/wb-qpcr-full-package/new")
def writing_wb_qpcr_full_package_new(
    title: str = Form(...),
    sample_type_wb: str = Form(""),
    sample_type_qpcr: str = Form(""),
    groups: str = Form(""),
    target_proteins: str = Form(""),
    target_genes: str = Form(""),
    antibodies: str = Form(""),
    primers: str = Form(""),
    wb_data: str = Form(""),
    qpcr_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Full_Validation_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    image_writebacks = get_recent_qpcr_image_writebacks(limit=5)
    bundle = build_wb_qpcr_full_validation_bundle(
        project_name,
        disease_name,
        sample_type_wb,
        sample_type_qpcr,
        groups,
        target_proteins,
        target_genes,
        antibodies,
        primers,
        wb_data,
        qpcr_data,
    )
    image_writeback_block = build_recent_image_writeback_section(
        image_writebacks,
        heading="最近 qPCR 图片回填草稿（自动并入）",
    )

    if not file_path.exists():
        content = f"""# WB / qPCR 联合验证总包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

{image_writeback_block}

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/wb-qpcr-stats/new")
def writing_wb_qpcr_stats_new(
    title: str = Form(...),
    target_proteins: str = Form(""),
    target_genes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Stats_Supplementary.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    stats_bundle = build_wb_qpcr_stats_bundle(
        project_name,
        disease_name,
        target_proteins,
        target_genes,
    )

    if not file_path.exists():
        content = f"""# WB / qPCR 统计表与补充材料整合包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{stats_bundle}

## 自定义补充说明

## 最终投稿用说明段

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)



@app.post("/writing/wb-qpcr-reviewer/new")
def writing_wb_qpcr_reviewer_new(
    title: str = Form(...),
    reviewer_comment: str = Form(""),
    target_proteins: str = Form(""),
    target_genes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Reviewer_Response.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_wb_qpcr_reviewer_bundle(project_name, disease_name, reviewer_comment, target_proteins, target_genes)

    if not file_path.exists():
        content = f"""# WB / qPCR 原始数据审稿答复稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

## 最终答复稿

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/wb-qpcr-mapping/new")
def writing_wb_qpcr_mapping_new(
    title: str = Form(...),
    main_figures: str = Form(""),
    supp_figures: str = Form(""),
    main_tables: str = Form(""),
    supp_tables: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_qPCR_Figure_Table_Mapping.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_wb_qpcr_mapping_bundle(project_name, disease_name, main_figures, supp_figures, main_tables, supp_tables)

    if not file_path.exists():
        content = f"""# WB / qPCR 图表编号映射表｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

## 最终映射说明

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/functional-validation-package/new")
def writing_functional_validation_package_new(
    title: str = Form(...),
    markers: str = Form(""),
    main_readouts: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Functional_Validation_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_functional_validation_package_bundle(
        project_name,
        disease_name,
        markers,
        main_readouts,
    )

    if not file_path.exists():
        content = f"""# 功能验证整合写作包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

## 最终 Results 段

## 最终 Figure Legends

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/functional-validation-full-package/new")
def writing_functional_validation_full_package_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    groups: str = Form(""),
    markers: str = Form(""),
    probe_reagents: str = Form(""),
    main_readouts: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Functional_Validation_Full_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_functional_validation_full_bundle(
        project_name,
        disease_name,
        sample_type,
        groups,
        markers,
        probe_reagents,
        main_readouts,
    )

    if not file_path.exists():
        content = f"""# 功能验证联合总包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-validation-master/new")
def writing_network_validation_master_new(
    title: str = Form(...),
    mechanism_focus: str = Form(""),
    target_focus: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Network_Validation_Master_Draft.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    recent_network_snapshot = build_recent_network_snapshot()
    recent_validation_snapshot = build_recent_validation_snapshot()
    recent_validation_fragments = build_recent_validation_draft_fragments()
    bundle = build_network_validation_master_bundle(
        project_name,
        disease_name,
        mechanism_focus,
        target_focus,
        recent_network_snapshot,
        recent_validation_snapshot,
        recent_validation_fragments,
    )

    if not file_path.exists():
        content = f"""# 网络药理 + 实验验证整合总稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 自动汇总来源
本稿会自动带入最近网络药理图表包、最近网络药理记录、最近验证记录摘要，以及最近验证草稿片段，便于继续整合成完整论文正文。

{bundle}

## 最终可复制 Results 段

## 最终可复制 Discussion 段

## 最终可复制 Methods 片段

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/full-validation-master/new")
def writing_full_validation_master_new(
    title: str = Form(...),
    core_markers: str = Form(""),
    key_readouts: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Full_Validation_Master_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    recent_snapshot = build_recent_validation_snapshot()
    recent_fragments = build_recent_validation_draft_fragments()
    bundle = build_full_validation_master_bundle(
        project_name,
        disease_name,
        core_markers,
        key_readouts,
        recent_snapshot,
        recent_fragments,
    )

    if not file_path.exists():
        content = f"""# 实验验证总控整合包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 自动汇总来源
本稿已自动读取最近的 CCK-8、WB、qPCR、Flow、ROS、JC-1、IF 记录名称与路径，便于继续补写总 Results、总 Methods 与 Figure Legends。
本稿同时会自动拼接最近的验证写作草稿片段，便于继续合并为总 Results 与总 Methods。

{bundle}

## 最终可复制 Results 段

## 最终可复制 Figure Legends

## 最终可复制 Methods 片段

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)

@app.post("/writing/network-methods/new")
def writing_network_methods_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Methods_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    methods_bundle = build_network_methods_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Methods 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{methods_bundle}

## 待补充数据库与参数
- 靶点数据库：
- 疾病数据库：
- PPI 平台：
- 富集分析平台：
- 筛选阈值：

## 待补充软件与版本
- Cytoscape：
- STRING：
- R / Python：
- GraphPad Prism：

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-introduction/new")
def writing_network_introduction_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Introduction_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    introduction_bundle = build_network_introduction_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Introduction 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{introduction_bundle}

## Introduction 正文草稿

## 待补充文献

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-abstract/new")
def writing_network_abstract_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Abstract_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    abstract_bundle = build_network_abstract_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Abstract 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{abstract_bundle}

## Abstract 正文草稿

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-cover-letter/new")
def writing_network_cover_letter_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Cover_Letter_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    cover_letter_bundle = build_network_cover_letter_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    journal_cover_style_bundle = build_journal_cover_letter_style_bundle(
        journal,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    journal_cover_full_bundle = build_journal_cover_letter_full_draft_bundle(
        journal,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Cover Letter 草稿｜{title}

## 日期
{today}

## 目标期刊模板
- 模板代号：{journal}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{cover_letter_bundle}

{journal_cover_style_bundle}

{journal_cover_full_bundle}

## Cover Letter 正文

## 待补充期刊信息
- Journal：
- Article type：
- Highlights：

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-graphical-abstract/new")
def writing_network_graphical_abstract_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Graphical_Abstract_Brief.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    graphical_abstract_bundle = build_network_graphical_abstract_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    journal_graphical_style_bundle = build_journal_graphical_abstract_style_bundle(
        journal,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Graphical Abstract 要点｜{title}

## 日期
{today}

## 目标期刊模板
- 模板代号：{journal}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{graphical_abstract_bundle}

{journal_graphical_style_bundle}

## 画图执行备注
- 推荐版式：
- 推荐主色：
- 需要保留的核心元素：

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-highlights/new")
def writing_network_highlights_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Highlights_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    highlights_bundle = build_network_highlights_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    journal_highlights_style_bundle = build_journal_highlights_style_bundle(
        journal,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )
    journal_highlights_full_bundle = build_journal_highlights_full_draft_bundle(
        journal,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Highlights 草稿｜{title}

## 日期
{today}

## 目标期刊模板
- 模板代号：{journal}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{highlights_bundle}

{journal_highlights_style_bundle}

{journal_highlights_full_bundle}

## 最终 Highlights

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-conclusion/new")
def writing_network_conclusion_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Conclusion_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    conclusion_bundle = build_network_conclusion_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Conclusion 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{conclusion_bundle}

## Conclusion 正文

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-keywords/new")
def writing_network_keywords_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Keywords_Draft.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    keywords_bundle = build_network_keywords_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Keywords 草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{keywords_bundle}

## 最终 Keywords

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-title/new")
def writing_network_title_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Title_Candidates.md"
    current_project = get_current_project() or {}
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    title_bundle = build_network_title_bundle(
        recommendations,
        current_project.get('research_object', '') or current_project.get('name', '') or "the project",
        current_project.get('disease', '') or "the disease model",
    )

    if not file_path.exists():
        content = f"""# Title 备选｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

{title_bundle}

## 最终标题

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-submission-package/new")
def writing_network_submission_package_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Submission_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get('research_object', '') or current_project.get('name', '') or "the project"
    disease_name = current_project.get('disease', '') or "the disease model"
    context = build_network_figure_context()
    recommendations = context["recommendations"]
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    recent_writing = get_recent_notes("06_论文写作", limit=12)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    writing_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_writing]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    writing_summary = "\n".join(writing_summary_lines) if writing_summary_lines else "- 当前暂无最近论文写作记录。"

    intro_bundle = build_network_introduction_bundle(recommendations, project_name, disease_name)
    abstract_bundle = build_network_abstract_bundle(recommendations, project_name, disease_name)
    cover_bundle = build_network_cover_letter_bundle(recommendations, project_name, disease_name)
    graphical_bundle = build_network_graphical_abstract_bundle(recommendations, project_name, disease_name)
    highlights_bundle = build_network_highlights_bundle(recommendations, project_name, disease_name)
    conclusion_bundle = build_network_conclusion_bundle(recommendations, project_name, disease_name)
    keywords_bundle = build_network_keywords_bundle(recommendations, project_name, disease_name)
    title_bundle = build_network_title_bundle(recommendations, project_name, disease_name)
    methods_bundle = build_network_methods_bundle(recommendations, project_name, disease_name)
    discussion_bundle = build_network_discussion_bundle(recommendations, project_name, disease_name)
    submission_bundle = build_network_submission_package_bundle(project_name, disease_name)
    journal_bundle = build_journal_preset_bundle(journal, project_name, disease_name)
    journal_cover_style_bundle = build_journal_cover_letter_style_bundle(journal, project_name, disease_name)
    journal_highlights_style_bundle = build_journal_highlights_style_bundle(journal, project_name, disease_name)
    journal_graphical_style_bundle = build_journal_graphical_abstract_style_bundle(journal, project_name, disease_name)

    if not file_path.exists():
        content = f"""# Submission Package｜{title}

## 日期
{today}

## 目标期刊模板
- 模板代号：{journal}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{submission_bundle}

{journal_bundle}

{journal_cover_style_bundle}

{journal_highlights_style_bundle}

{journal_graphical_style_bundle}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

## 最近论文写作记录
{writing_summary}

{title_bundle}

{keywords_bundle}

{highlights_bundle}

{intro_bundle}

{abstract_bundle}

{methods_bundle}

{discussion_bundle}

{conclusion_bundle}

{cover_bundle}

{graphical_bundle}

## 最终投稿前操作
- [ ] 整理最终题目
- [ ] 整理最终摘要
- [ ] 整理最终关键词
- [ ] 整理最终 Highlights
- [ ] 核对 Figure Legends
- [ ] 核对 Cover Letter
- [ ] 核对图文摘要
- [ ] 导出投稿清单

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-response-letter/new")
def writing_network_response_letter_new(title: str = Form(...), journal: str = Form("generic")):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Response_Letter_Draft.md"
    current_project = get_current_project() or {}
    project_name = current_project.get('research_object', '') or current_project.get('name', '') or "the project"
    disease_name = current_project.get('disease', '') or "the disease model"
    recent_figure_packages = get_recent_figure_packages(limit=3)
    recent_network = get_recent_notes("02_项目管理/网络药理学", limit=3)
    recent_writing = get_recent_notes("06_论文写作", limit=12)
    figure_package_lines = [f"- {item['name']}｜{item['path']}" for item in recent_figure_packages]
    network_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_network]
    writing_summary_lines = [f"- {item['name']}｜{item['path']}" for item in recent_writing]
    figure_package_summary = "\n".join(figure_package_lines) if figure_package_lines else "- 当前暂无最近网络药理图表包。"
    network_summary = "\n".join(network_summary_lines) if network_summary_lines else "- 当前暂无最近网络药理记录。"
    writing_summary = "\n".join(writing_summary_lines) if writing_summary_lines else "- 当前暂无最近论文写作记录。"
    response_bundle = build_response_letter_bundle(journal, project_name, disease_name)

    if not file_path.exists():
        content = f"""# Response Letter 草稿｜{title}

## 日期
{today}

## 目标期刊模板
- 模板代号：{journal}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 最近网络药理图表包
{figure_package_summary}

## 最近网络药理记录
{network_summary}

## 最近论文写作记录
{writing_summary}

{response_bundle}

## Reviewer Comment 追踪表
| Reviewer | Comment Summary | Action Taken | Manuscript Location |
|---|---|---|---|
| Editor |  |  |  |
| Reviewer 1 |  |  |  |
| Reviewer 2 |  |  |  |

## 最终 Response Letter 正文

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/reviewer-split/new")
def writing_reviewer_split_new(
    title: str = Form(...),
    reviewer_name: str = Form("Reviewer 1"),
    raw_comments: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_Reviewer_Split.md"
    split_bundle = build_reviewer_comment_split_bundle(raw_comments)

    if not file_path.exists():
        content = f"""# 审稿意见拆分｜{title}

## 日期
{today}

## 审稿人
{reviewer_name}

## 原始审稿意见
{raw_comments or "[尚未粘贴原始审稿意见]"}

{split_bundle}

## 汇总说明
- [ ] 是否每条意见都已回复
- [ ] 是否说明具体修改位置
- [ ] 是否需要补实验 / 补分析 / 补文献

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/network", response_class=HTMLResponse)
def network_index():
    files = list_md("02_项目管理/网络药理学")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project()
    recent_imports = get_recent_project_imports()
    intersection_context = build_network_intersection_context()
    figure_context = build_network_figure_context()
    template = env.get_template("network/index.html")
    return template.render(
        items=items,
        modules=MODULES,
        active_project=current_project,
        recent_imports=recent_imports,
        intersection_context=intersection_context,
        figure_context=figure_context,
    )

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


@app.post("/network/intersection/new")
def network_intersection_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "网络药理学"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_DEG_交集分析.md"
    context = build_network_intersection_context()
    current_project = context["current_project"]
    deg_path = context["deg_path"]
    target_path = context["target_path"]
    disease_path = context["disease_path"]
    network_path = context["network_path"]
    import_summary_text = context["import_summary_text"]

    if not file_path.exists():
        content = f"""# DEG ∩ 网络药理靶点交集分析｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 输入文件
- 差异基因表（DEG）：{deg_path}
- 成分靶点表：{target_path}
- 疾病靶点表：{disease_path}
- 网络药理交集靶点表：{network_path}

## 最近输入摘要
{import_summary_text}

## DEG 筛选条件
- |log2FC|：
- P value：
- Padj / FDR：
- 数据集编号：

## 网络药理靶点来源
- SwissTargetPrediction：
- GeneCards：
- OMIM：
- DisGeNET：
- 其他：

## 交集分析
- DEG 数量：
- 网络药理候选靶点数量：
- 交集基因数：
- 核心交集基因：

## 后续分析计划
- [ ] PPI 网络
- [ ] GO 富集
- [ ] KEGG 富集
- [ ] Cytoscape 可视化
- [ ] Docking 候选组合
- [ ] WB / qPCR 验证

## 结果文件位置
- 交集表：
- Venn / UpSet 图：
- PPI：
- GO：
- KEGG：

## 结果解释

## Results 草稿

## 风险点
- DEG 数据集是否匹配疾病模型：
- 交集是否过少：
- 是否需要放宽 / 收紧阈值：
- 是否存在基因名标准化问题：
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/network/intersection/auto")
def network_intersection_auto():
    context = build_network_intersection_context()
    if not context["readiness"]["can_auto_create"]:
        return RedirectResponse(url="/network", status_code=303)
    return network_intersection_new(title=context["auto_title"])


@app.post("/network/visualization/new")
def network_visualization_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "科研作图"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_网络药理可视化.md"
    current_project = get_current_project() or {}

    if not file_path.exists():
        content = f"""# 网络药理可视化任务｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 输入文件
- DEG 表：
- 网络药理交集表：
- 成分-靶点边表：
- PPI 数据：
- GO 结果：
- KEGG 结果：

## 本次需要生成的图
- [ ] Venn 图
- [ ] UpSet 图
- [ ] 交集基因表
- [ ] PPI 网络图
- [ ] GO 气泡图
- [ ] KEGG 气泡图
- [ ] 成分-靶点网络图

## 图表输出位置
- PNG：
- SVG / PDF：
- 原始 CSV：

## 图注草稿
- Figure title：
- Figure legend：

## 与后续流程衔接
- [ ] 进入 Cytoscape 精修
- [ ] 进入 Docking 候选筛选
- [ ] 进入 Results 写作

## 风险点
- 基因名是否标准化：
- 输入表是否去重：
- 图中标签是否过密：
- 是否需要 Top N 筛选：
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/screen", response_class=HTMLResponse)
def screen_index():
    files = list_md("02_项目管理/虚拟筛选")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project()
    template = env.get_template("screen/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project)

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


@app.get("/docking", response_class=HTMLResponse)
def docking_index():
    files = list_md("02_项目管理/分子对接")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project()
    template = env.get_template("docking/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project)


@app.post("/docking/new")
def docking_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "分子对接"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# 分子对接任务｜{title}

## 日期
{today}

## 对接目的

## 配体信息
- 化合物名称：
- PubChem CID：
- SMILES：
- SDF / MOL2 文件位置：

## 蛋白信息
- 靶点名称：
- UniProt ID：
- PDB ID：
- 蛋白来源：

## 软件与工具
- AutoDock Vina：
- OpenBabel：
- PyMOL：
- Discovery Studio：

## 对接参数
- Grid center：
- Grid size：
- Exhaustiveness：
- Number of modes：

## 对接结果
| 配体 | 靶点 | Binding Energy kcal/mol | 主要相互作用 | 备注 |
|---|---|---|---|---|

## 相互作用分析
- 氢键：
- 疏水作用：
- π-π：
- 关键氨基酸：

## 图片位置
- 2D interaction：
- 3D pose：
- Surface pocket：

## 是否进入 MD
- [ ] 是
- [ ] 否

## 论文 Results 草稿

## 风险点
- 蛋白结构质量：
- 配体构象：
- 对接盒设置：
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/md", response_class=HTMLResponse)
def md_index():
    files = list_md("02_项目管理/分子动力学")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project()
    template = env.get_template("md/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project)

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
    current_project = get_current_project()
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("admet/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project)

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
    current_project = get_current_project()
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("natural_product/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project)

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


@app.get("/gene", response_class=HTMLResponse)
def gene_index():
    files = list_md("02_项目管理/Gene_Omics")
    current_project = get_current_project()
    recent_imports = get_recent_project_imports()
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("gene/index.html")
    return template.render(items=items, modules=MODULES, active_project=current_project, recent_imports=recent_imports)


@app.post("/gene/new")
def gene_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "02_项目管理" / "Gene_Omics"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# Gene / Omics 分析任务｜{title}

## 日期
{today}

## 项目背景
- 项目名称：
- 疾病 / 模型：
- 数据来源（GEO / RNA-seq / TCGA / 自测序）：
- 数据集编号：

## 样本信息
- 实验组：
- 对照组：
- 样本量：
- 平台：

## 数据处理流程
- 原始数据下载：
- 质控：
- 标准化：
- 差异分析：
- 富集分析：
- 可视化：

## 差异基因筛选阈值
- |log2FC|：
- P value：
- Padj / FDR：

## 候选基因
- 

## 与网络药理交集
- 交集基因数：
- 核心基因：
- 后续靶点：

## 推荐后续动作
- [ ] GO / KEGG 富集
- [ ] PPI 网络
- [ ] 与成分靶点交集
- [ ] 进入 Docking
- [ ] 进入 WB / qPCR 验证

## 结果文件位置

## 图表位置
- Volcano：
- Heatmap：
- PCA：
- Enrichment：

## 结果解释

## Results 草稿

## 风险点
- 样本量是否足够：
- 批次效应是否处理：
- 阈值是否过严 / 过宽：
- 是否存在过度解释：
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


@app.post("/pdf-to-note")
def pdf_to_note(path: str = Form(...)):
    today = date.today().isoformat()
    pdf_path = ROOT / path
    title = pdf_path.stem if pdf_path.exists() else "未命名PDF"

    folder = ROOT / "04_文献笔记"
    folder.mkdir(parents=True, exist_ok=True)
    note_path = folder / f"{today}_{safe_name(title)}_文献笔记.md"

    if not note_path.exists():
        content = f"""# 文献笔记｜{title}

## 日期
{today}

## 来源PDF
{path}

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
        note_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={note_path.relative_to(ROOT)}", status_code=303)


@app.post("/pdf-extract-note")
def pdf_extract_note(path: str = Form(...)):
    today = date.today().isoformat()
    pdf_path = ROOT / path
    title = pdf_path.stem

    text_content = ""
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages[:8]:
            text_content += page.extract_text() or ""
            text_content += "\n\n"
    except Exception as e:
        text_content = f"PDF解析失败：{e}"

    folder = ROOT / "04_文献笔记"
    folder.mkdir(parents=True, exist_ok=True)
    note_path = folder / f"{today}_{safe_name(title)}_PDF解析.md"

    content = f"""# PDF文献解析｜{title}

## 日期
{today}

## 来源PDF
{path}

## 自动提取文本（前8页）
{text_content[:8000]}

## AI后续整理
- 一句话总结：
- 研究背景：
- 研究目的：
- 实验方法：
- 主要结果：
- 创新点：
- 不足：
- Research Gap：
- 与我的课题关系：
"""

    note_path.write_text(content, encoding="utf-8")
    return RedirectResponse(url=f"/file?path={note_path.relative_to(ROOT)}", status_code=303)


@app.post("/literature-ai-prompt")
def literature_ai_prompt(path: str = Form(...)):
    p = ROOT / path
    source_text = read(p)

    today = date.today().isoformat()
    folder = ROOT / "04_文献笔记"
    folder.mkdir(parents=True, exist_ok=True)

    file_path = folder / f"{today}_{safe_name(p.stem)}_AI整理提示词.md"

    content = f"""# 文献AI整理提示词｜{p.stem}

请根据以下 PDF 提取文本，帮我整理成高质量文献笔记。

## 我的课题背景
我正在研究金毛狗脊治疗缺血性脑卒中的作用机制，研究路线包括：
UPLC-QTOF/MS 成分分析、网络药理学、虚拟筛选、分子对接、H/R细胞模型、WB、RT-qPCR 和论文写作。

## 请按以下结构输出
1. 一句话总结
2. 研究背景
3. 研究目的
4. 实验设计 / 方法
5. 主要结果
6. 创新点
7. 不足与局限
8. Research Gap
9. 与我的课题关系
10. 可用于 Introduction 的内容
11. 可用于 Discussion 的内容
12. 值得追踪的关键词
13. 可引用的关键句子

## PDF提取文本
{source_text[:12000]}
"""

    file_path.write_text(content, encoding="utf-8")
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/literature-v2", response_class=HTMLResponse)
def literature_v2():
    folder = ROOT / "04_文献笔记" / "PDF库"
    folder.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(folder.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = [{"name": p.name, "path": str(p.relative_to(ROOT))} for p in pdfs]
    template = env.get_template("literature_v2.html")
    return template.render(items=items, modules=MODULES)

@app.post("/literature-v2/analyze")
def literature_v2_analyze(path: str = Form(...)):
    pdf_path = ROOT / path
    today = date.today().isoformat()

    raw_text = ""
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages[:3]:
            raw_text += page.extract_text() or ""
            raw_text += "\n"
    except Exception as e:
        raw_text = f"PDF解析失败：{e}"

    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", raw_text)
    doi = doi_match.group(0).rstrip(".;,") if doi_match else ""

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    year_match = re.search(r"(20\d{2}|19\d{2})", raw_text)
    year = year_match.group(0) if year_match else ""

    journal_keywords = ["Journal", "Nature", "Science", "Cell", "Frontiers", "Phytomedicine", "Biomedicine", "Molecules", "Pharmacology"]
    journal = ""
    for line in lines[:40]:
        if any(k.lower() in line.lower() for k in journal_keywords):
            journal = line
            break

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    candidate_title = ""
    for line in lines[:20]:
        if 20 <= len(line) <= 220 and not line.lower().startswith(("abstract", "keywords", "doi")):
            candidate_title = line
            break

    title = candidate_title or pdf_path.stem

    note_dir = ROOT / "04_文献笔记"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / f"{today}_{safe_name(title)}_V2文献卡片.md"

    content = f"""# 文献卡片 V2｜{title}

## 日期
{today}

## 来源PDF
{path}

## 自动识别信息
- 标题：{title}
- DOI：{doi}
- 作者：
- 期刊：{journal}
- 年份：{year}
- 关键词：

## 一句话总结

## 研究背景

## 研究目的

## 方法设计

## 主要结果

## 创新点

## 不足与局限

## Research Gap

## 与我的金毛狗脊 / 缺血性脑卒中课题关系

## 可用于 Introduction 的内容

## 可用于 Discussion 的内容

## AI整理提示词
请根据下面的PDF提取文本，整理为高质量科研文献笔记，重点关注：
1. 缺血性脑卒中
2. 氧化应激
3. 炎症
4. 凋亡
5. PI3K/AKT、Nrf2、MAPK、NF-κB等机制
6. 与天然产物药理学研究的关系

## PDF前3页提取文本
{raw_text[:10000]}
"""
    note_path.write_text(content, encoding="utf-8")
    return RedirectResponse(url=f"/file?path={note_path.relative_to(ROOT)}", status_code=303)


@app.get("/cck8", response_class=HTMLResponse)
def cck8_index():
    files = list_md("05_数据分析/CCK8")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    template = env.get_template("cck8/index.html")
    return template.render(items=items, modules=MODULES)

@app.post("/cck8/new")
def cck8_new(
    title: str = Form(...),
    cell: str = Form(""),
    timepoint: str = Form(""),
    groups: str = Form(""),
    od_data: str = Form("")
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "CCK8"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"

    if not file_path.exists():
        content = f"""# CCK-8 数据记录｜{title}

## 日期
{today}

## 细胞类型
{cell}

## 处理时间
{timepoint}

## 分组与浓度
{groups}

## 原始 OD 数据
{text_block_start}
{od_data}
{text_block_end}

## 数据处理规则
细胞活率 = (OD处理组 - OD空白) / (OD对照组 - OD空白) × 100%

## 初步结果

## 异常值检查
- [ ] 是否有边缘孔异常
- [ ] 是否有气泡
- [ ] 是否有污染
- [ ] 是否有 OD 过高/过低

## GraphPad Prism 导入格式

## Figure 计划

## Results 草稿

## 下一步
""".replace("{text_block_start}", "```text").replace("{text_block_end}", "```")

        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


def build_cck8_full_package_bundle(
    project_name: str,
    disease_name: str,
    cell_type: str,
    timepoint: str,
    groups: str,
    od_data: str,
):
    return f"""## CCK-8 联合总包

### 一、实验对象
- 项目：{project_name}
- 疾病 / 模型：{disease_name}
- 细胞类型：{cell_type or "- 待补充"}
- 处理时间：{timepoint or "- 待补充"}

### 二、实验分组
```text
{groups or "Control / Model / Treatment-Low / Treatment-High / Positive control"}
```

### 三、原始 OD 数据
```text
{od_data or "Group\tRep1\tRep2\tRep3\tMean"}
```

### 四、Results 初稿
CCK-8 assay was performed to evaluate the effect of {project_name} on cell viability in the {disease_name} model. Compared with the control group, the model group exhibited a marked reduction in cell viability. Treatment with {project_name} partially or significantly restored cell viability, suggesting an overall protective effect against model-induced cellular injury.

### 五、Methods 初稿
Cell viability was assessed using the CCK-8 assay. Cells were seeded into 96-well plates and exposed to the indicated treatments for {timepoint or "the specified duration"}. After incubation, CCK-8 reagent was added to each well and the plates were further incubated under standard culture conditions. Absorbance was measured at 450 nm using a microplate reader, and relative cell viability was calculated according to the experimental design.

### 六、Figure Legend 初稿
- Figure X. Effects of {project_name} on cell viability in the {disease_name} model, as determined by the CCK-8 assay. Data are presented as mean ± SD.

### 七、Supplementary 建议
- Supplementary Table S1：Raw OD values for each replicate
- Supplementary Table S2：Cell viability calculation sheet
- Supplementary Note S1：Plate layout and blank-control arrangement

### 八、投稿前核对清单
- [ ] 是否补齐空白孔和对照孔信息
- [ ] 是否明确细胞密度与处理时间
- [ ] 是否保存原始 OD 值和计算过程
- [ ] 是否补充统计学方法与显著性标记
"""


@app.post("/cck8/full-package/new")
def cck8_full_package_new(
    title: str = Form(...),
    cell: str = Form(""),
    timepoint: str = Form(""),
    groups: str = Form(""),
    od_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_CCK8_Full_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_cck8_full_package_bundle(
        project_name,
        disease_name,
        cell,
        timepoint,
        groups,
        od_data,
    )

    if not file_path.exists():
        content = f"""# CCK-8 联合总包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

{bundle}

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)




@app.get("/wb", response_class=HTMLResponse)
def wb_index():
    files = list_md("03_实验记录/WB")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project() or {}
    template = env.get_template("wb/index.html")
    return template.render(items=items, active_project=current_project)


@app.post("/wb/new")
def wb_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    target_proteins: str = Form(""),
    groups: str = Form(""),
    antibodies: str = Form(""),
    notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "WB"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_wb_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# WB 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 样本类型
{sample_type}

## 目标蛋白
{target_proteins}

## 实验分组
{text_block_start}
{groups}
{text_block_end}

## 抗体信息
{text_block_start}
{antibodies}
{text_block_end}

## 样本制备与上样
- 裂解液：
- 定量方法：
- 上样量：
- 胶浓度：
- 转膜条件：

## 孵育条件
- 封闭液：
- 一抗条件：
- 二抗条件：
- ECL / 显影：

## 原始条带与灰度数据
```text
组别	目标蛋白灰度	内参灰度	归一化结果
Control			
Model			
Treatment-Low			
Treatment-High			
Positive control			
```

## 异常与备注
{text_block_start}
{notes}
{text_block_end}

{bundle}

## Figure Legend 草稿
- Figure X. Effects of {project_name} on the protein expression related to {disease_name}.

## 下一步
- [ ] 完成灰度统计
- [ ] 生成柱状图
- [ ] 写入 Results
- [ ] 与 qPCR 结果交叉验证
""".replace("{text_block_start}", "```text").replace("{text_block_end}", "```")
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/wb/results/new")
def wb_results_new(
    title: str = Form(...),
    target_proteins: str = Form(""),
    normalized_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "WB"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_Results.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_wb_results_bundle(project_name, disease_name, target_proteins, normalized_data)

    if not file_path.exists():
        content = f"""# WB 结果分析稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}

## 自定义结果说明

## 最终 Results 段

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/wb/full-draft/new")
def wb_full_draft_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    target_proteins: str = Form(""),
    groups: str = Form(""),
    antibodies: str = Form(""),
    normalized_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_WB_Full_Draft.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_wb_full_draft_bundle(
        project_name,
        disease_name,
        sample_type,
        target_proteins,
        groups,
        antibodies,
        normalized_data,
    )

    if not file_path.exists():
        content = f"""# WB 全套草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/qpcr", response_class=HTMLResponse)
def qpcr_index():
    files = list_md("03_实验记录/qPCR")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    recent_results = get_recent_notes("05_数据分析/qPCR", limit=5)
    recent_writing = get_recent_notes("06_论文写作/WB_qPCR验证", limit=8)
    image_items = build_qpcr_image_registry(limit=12)
    current_project = get_current_project() or {}
    template = env.get_template("qpcr/index.html")
    return template.render(
        items=items,
        active_project=current_project,
        recent_results=recent_results,
        recent_writing=recent_writing,
        image_items=image_items,
    )


@app.post("/qpcr/image-upload")
async def qpcr_image_upload(
    title: str = Form(...),
    image_type: str = Form(""),
    observation: str = Form(""),
    file: UploadFile = File(...),
):
    current_project = get_current_project() or {}
    folder = ROOT / "03_实验记录" / "qPCR_原始图片"
    folder.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
        return HTMLResponse("仅支持 png、jpg、jpeg、gif、webp、bmp、tif、tiff 图片。", status_code=400)

    today = date.today().isoformat()
    filename = f"{today}_{safe_name(title)}{suffix}"
    file_path = folder / filename
    content = await file.read()
    file_path.write_bytes(content)

    note_path = file_path.with_suffix(".md")
    if not note_path.exists():
        note_path.write_text(
            f"""# qPCR 原始图片记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 图片类型
{image_type or "待补充"}

## 原始文件
{file_path.relative_to(ROOT)}

## 图谱观察
{observation or "待补充"}

## 推荐用途
- [ ] 扩增曲线解读
- [ ] 熔解曲线解读
- [ ] Supplementary Figure
- [ ] 审稿补充材料

## 下一步
- [ ] 如需 AI 解读，请把主要观察复制到 qPCR 工作台的 AI 图谱讲解模块
- [ ] 如需写正文，请补充与 Ct / 2^-ΔΔCt 数据的对应关系
""",
            encoding="utf-8",
        )

    registry = build_qpcr_image_registry()
    current_item = next(
        (item for item in registry if item["path"] == str(file_path.relative_to(ROOT))),
        None,
    )
    if current_item:
        note_text = read(note_path)
        if "## Supplementary Figure 建议编号" not in note_text:
            note_text = note_text.rstrip() + f"""

## Supplementary Figure 建议编号
{current_item['supplementary_label']}

## Supplementary Figure 建议标题
{current_item['supplementary_title']}
"""
            note_path.write_text(note_text + "\n", encoding="utf-8")

    return RedirectResponse(url="/qpcr", status_code=303)


@app.post("/qpcr/ai-curve-from-image")
def qpcr_ai_curve_from_image(note_path: str = Form(...)):
    note_file = ROOT / note_path
    if not note_file.exists():
        return HTMLResponse("图片备注不存在", status_code=404)

    note_text = read(note_file)
    image_type = extract_markdown_section(note_text, "图片类型")
    observation = extract_markdown_section(note_text, "图谱观察")
    image_rel_path = extract_markdown_section(note_text, "原始文件")
    image_name = Path(image_rel_path).name if image_rel_path else note_file.stem
    supplementary_label = extract_markdown_section(note_text, "Supplementary Figure 建议编号")
    supplementary_title = extract_markdown_section(note_text, "Supplementary Figure 建议标题")

    amplification_notes = ""
    melting_notes = ""
    lower_type = image_type.lower()
    if "熔解" in image_type:
        melting_notes = observation
    elif "扩增" in image_type:
        amplification_notes = observation
    else:
        amplification_notes = f"图片类型：{image_type or '未注明'}\n观察记录：{observation}"

    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(image_name)}_qPCR_AI_Image_Curve.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"

    system_prompt, user_prompt = build_qpcr_ai_curve_prompt(
        project_name,
        disease_name,
        "",
        amplification_notes,
        melting_notes,
        "",
        f"来源图片类型：{image_type or '未注明'}；{supplementary_label or '未分配补充图编号'}；{supplementary_title or '未分配补充图标题'}",
    )
    result = ai_json_or_prompt(system_prompt, user_prompt)
    content = format_ai_analysis_markdown(f"qPCR 图片AI图谱讲解｜{image_name}", result)
    file_path.write_text(
        f"""## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

## 来源图片
{image_rel_path}

## 来源备注
{note_path}

## 图片类型
{image_type or "未注明"}

## Supplementary Figure 建议编号
{supplementary_label or "待补充"}

## Supplementary Figure 建议标题
{supplementary_title or "待补充"}

## 人工观察
{observation or "待补充"}

{content}""",
        encoding="utf-8",
    )
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/image-writeback/new")
def qpcr_image_writeback_new(note_path: str = Form(...)):
    note_file = ROOT / note_path
    if not note_file.exists():
        return HTMLResponse("图片备注不存在", status_code=404)

    note_text = read(note_file)
    image_type = extract_markdown_section(note_text, "图片类型")
    observation = extract_markdown_section(note_text, "图谱观察")
    image_rel_path = extract_markdown_section(note_text, "原始文件")
    image_name = Path(image_rel_path).stem if image_rel_path else note_file.stem
    supplementary_label = extract_markdown_section(note_text, "Supplementary Figure 建议编号")
    supplementary_title = extract_markdown_section(note_text, "Supplementary Figure 建议标题")

    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(image_name)}_qPCR_Image_Writeback.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"

    system_prompt, user_prompt = build_qpcr_image_writeback_prompt(
        project_name,
        disease_name,
        f"{image_type or '未注明'}｜{supplementary_label or '未分配补充图编号'}｜{supplementary_title or '未分配补充图标题'}",
        observation or "待补充",
    )
    result = ai_json_or_prompt(system_prompt, user_prompt)
    content = format_ai_analysis_markdown(f"qPCR 图片回填草稿｜{image_name}", result)
    file_path.write_text(
        f"""## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

## 来源图片
{image_rel_path}

## 来源备注
{note_path}

## 图片类型
{image_type or '未注明'}

## Supplementary Figure 建议编号
{supplementary_label or '待补充'}

## Supplementary Figure 建议标题
{supplementary_title or '待补充'}

## 人工观察
{observation or '待补充'}

{content}""",
        encoding="utf-8",
    )
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/molecular-validation", response_class=HTMLResponse)
def molecular_validation_index():
    current_project = get_current_project() or {}
    wb_records = get_recent_notes("03_实验记录/WB", limit=6)
    qpcr_records = get_recent_notes("03_实验记录/qPCR", limit=6)
    wb_results = get_recent_notes("05_数据分析/WB", limit=6)
    qpcr_results = get_recent_notes("05_数据分析/qPCR", limit=6)
    qpcr_images = build_qpcr_image_registry(limit=8)
    validation_writing = get_recent_notes("06_论文写作/WB_qPCR验证", limit=12)
    summary = build_molecular_validation_summary(current_project)
    template = env.get_template("molecular_validation/index.html")
    return template.render(
        active_project=current_project,
        summary=summary,
        wb_records=wb_records,
        qpcr_records=qpcr_records,
        wb_results=wb_results,
        qpcr_results=qpcr_results,
        qpcr_images=qpcr_images,
        validation_writing=validation_writing,
    )


@app.post("/qpcr/new")
def qpcr_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    target_genes: str = Form(""),
    groups: str = Form(""),
    primers: str = Form(""),
    notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# qPCR 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 样本类型
{sample_type}

## 目标基因
{target_genes}

## 实验分组
{text_block_start}
{groups}
{text_block_end}

## 引物信息
{text_block_start}
{primers}
{text_block_end}

## RNA 与逆转录记录
- RNA 提取试剂：
- RNA 浓度：
- A260/A280：
- 逆转录体系：
- 反应程序：

## 原始 Ct 数据
```text
Gene	Control-1	Control-2	Control-3	Model-1	Model-2	Model-3	Treatment-Low	Treatment-High	Positive control

```

## 2^-ΔΔCt 结果
```text
Gene	Control	Model	Treatment-Low	Treatment-High	Positive control

```

## 异常与备注
{text_block_start}
{notes}
{text_block_end}

{bundle}

## Figure Legend 草稿
- Figure X. Effects of {project_name} on the mRNA expression related to {disease_name}.

## 下一步
- [ ] 完成 Ct 质控
- [ ] 计算 2^-ΔΔCt
- [ ] 生成柱状图
- [ ] 与 WB 结果交叉验证
""".replace("{text_block_start}", "```text").replace("{text_block_end}", "```")
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/full-draft/new")
def qpcr_full_draft_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    target_genes: str = Form(""),
    groups: str = Form(""),
    primers: str = Form(""),
    ddct_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Full_Draft.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_full_draft_bundle(
        project_name,
        disease_name,
        sample_type,
        target_genes,
        groups,
        primers,
        ddct_data,
    )

    if not file_path.exists():
        content = f"""# qPCR 全套草稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/results/new")
def qpcr_results_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    ddct_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Results.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_results_bundle(project_name, disease_name, target_genes, ddct_data)

    if not file_path.exists():
        content = f"""# qPCR 结果分析稿｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}

## 自定义结果说明

## 最终 Results 段

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/ct-qc/new")
def qpcr_ct_qc_new(
    title: str = Form(...),
    housekeeping_gene: str = Form(""),
    raw_ct_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Ct_QC.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_ct_qc_bundle(project_name, disease_name, housekeeping_gene, raw_ct_data)

    if not file_path.exists():
        content = f"""# qPCR Ct 质控与计算包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}

## 质控备注

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/group-stats/new")
def qpcr_group_stats_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    groups: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Group_Stats.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_group_stats_template_bundle(project_name, disease_name, target_genes, groups)

    if not file_path.exists():
        content = f"""# qPCR 分组统计表模板｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/primer-table/new")
def qpcr_primer_table_new(title: str = Form(...)):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Primer_Table.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    bundle = build_qpcr_primer_table_bundle(project_name)

    if not file_path.exists():
        content = f"""# qPCR 引物信息标准表｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/primer-design/new")
def qpcr_primer_design_new(
    title: str = Form(...),
    species: str = Form(""),
    target_genes: str = Form(""),
    housekeeping_gene: str = Form(""),
    amplicon_range: str = Form(""),
    tm_range: str = Form(""),
    gc_range: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Primer_Design.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    bundle = build_qpcr_primer_design_bundle(
        project_name,
        species,
        target_genes,
        housekeeping_gene,
        amplicon_range,
        tm_range,
        gc_range,
    )

    if not file_path.exists():
        content = f"""# qPCR 引物设计建议包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/curve-interpretation/new")
def qpcr_curve_interpretation_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    amplification_notes: str = Form(""),
    melting_notes: str = Form(""),
    ntc_status: str = Form(""),
    efficiency_notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Curve_Interpretation.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    bundle = build_qpcr_curve_interpretation_bundle(
        project_name,
        target_genes,
        amplification_notes,
        melting_notes,
        ntc_status,
        efficiency_notes,
    )

    if not file_path.exists():
        content = f"""# qPCR 图谱讲解包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/error-analysis/new")
def qpcr_error_analysis_new(
    title: str = Form(...),
    issue_summary: str = Form(""),
    raw_ct_pattern: str = Form(""),
    possible_causes: str = Form(""),
    corrective_actions: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Error_Analysis.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_error_analysis_bundle(
        project_name,
        disease_name,
        issue_summary,
        raw_ct_pattern,
        possible_causes,
        corrective_actions,
    )

    if not file_path.exists():
        content = f"""# qPCR 误差分析与排错包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/ai-results/new")
def qpcr_ai_results_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    groups: str = Form(""),
    ddct_data: str = Form(""),
    stats_summary: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_AI_Results.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    system_prompt, user_prompt = build_qpcr_ai_results_prompt(
        project_name, disease_name, target_genes, groups, ddct_data, stats_summary
    )
    result = ai_json_or_prompt(system_prompt, user_prompt)
    content = format_ai_analysis_markdown(f"qPCR AI结果解读｜{title}", result)
    file_path.write_text(
        f"""## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{content}""",
        encoding="utf-8",
    )
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/ai-curve/new")
def qpcr_ai_curve_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    amplification_notes: str = Form(""),
    melting_notes: str = Form(""),
    ntc_status: str = Form(""),
    efficiency_notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_AI_Curve.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    system_prompt, user_prompt = build_qpcr_ai_curve_prompt(
        project_name,
        disease_name,
        target_genes,
        amplification_notes,
        melting_notes,
        ntc_status,
        efficiency_notes,
    )
    result = ai_json_or_prompt(system_prompt, user_prompt)
    content = format_ai_analysis_markdown(f"qPCR AI图谱讲解｜{title}", result)
    file_path.write_text(
        f"""## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{content}""",
        encoding="utf-8",
    )
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/ai-error/new")
def qpcr_ai_error_new(
    title: str = Form(...),
    issue_summary: str = Form(""),
    raw_ct_pattern: str = Form(""),
    possible_causes: str = Form(""),
    corrective_actions: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "05_数据分析" / "qPCR"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_AI_Error.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    system_prompt, user_prompt = build_qpcr_ai_error_prompt(
        project_name,
        disease_name,
        issue_summary,
        raw_ct_pattern,
        possible_causes,
        corrective_actions,
    )
    result = ai_json_or_prompt(system_prompt, user_prompt)
    content = format_ai_analysis_markdown(f"qPCR AI误差诊断｜{title}", result)
    file_path.write_text(
        f"""## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{content}""",
        encoding="utf-8",
    )
    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/stats-package/new")
def qpcr_stats_package_new(
    title: str = Form(...),
    target_genes: str = Form(""),
    ddct_data: str = Form(""),
    stats_summary: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Stats_Supplementary.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_stats_package_bundle(project_name, disease_name, target_genes, ddct_data, stats_summary)

    if not file_path.exists():
        content = f"""# qPCR 统计表与补充材料包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/reviewer/new")
def qpcr_reviewer_new(
    title: str = Form(...),
    reviewer_comment: str = Form(""),
    target_genes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Reviewer_Response.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_reviewer_bundle(project_name, disease_name, reviewer_comment, target_genes)

    if not file_path.exists():
        content = f"""# qPCR 审稿答复包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/mapping/new")
def qpcr_mapping_new(
    title: str = Form(...),
    main_figures: str = Form(""),
    supp_figures: str = Form(""),
    main_tables: str = Form(""),
    supp_tables: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Figure_Table_Mapping.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_qpcr_mapping_bundle(project_name, disease_name, main_figures, supp_figures, main_tables, supp_tables)

    if not file_path.exists():
        content = f"""# qPCR 图表编号映射表｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/qpcr/full-package/new")
def qpcr_full_package_new(
    title: str = Form(...),
    sample_type: str = Form(""),
    target_genes: str = Form(""),
    groups: str = Form(""),
    primers: str = Form(""),
    raw_ct_data: str = Form(""),
    ddct_data: str = Form(""),
    stats_summary: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "06_论文写作" / "WB_qPCR验证"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}_qPCR_Full_Package.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    image_writebacks = get_recent_qpcr_image_writebacks(limit=5)
    bundle = build_qpcr_full_package_bundle(
        project_name,
        disease_name,
        sample_type,
        target_genes,
        groups,
        primers,
        raw_ct_data,
        ddct_data,
        stats_summary,
    )
    image_writeback_block = build_recent_image_writeback_section(
        image_writebacks,
        heading="最近 qPCR 图片回填草稿（自动并入）",
    )

    if not file_path.exists():
        content = f"""# qPCR 投稿级全包｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}

{bundle}

{image_writeback_block}
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/flow", response_class=HTMLResponse)
def flow_index():
    files = list_md("03_实验记录/Flow")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project() or {}
    template = env.get_template("flow/index.html")
    return template.render(items=items, active_project=current_project)


@app.post("/flow/new")
def flow_new(
    title: str = Form(...),
    assay_type: str = Form("Annexin V / PI"),
    groups: str = Form(""),
    markers: str = Form(""),
    notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "Flow"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_flow_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# Flow 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 检测类型
{assay_type}

## 标志物 / 通道
{markers}

## 实验分组
```text
{groups}
```

## 原始读数模板
```text
Group\tRep1\tRep2\tRep3\tMean\tSD
Control\t\t\t\t\t
Model\t\t\t\t\t
Treatment-Low\t\t\t\t\t
Treatment-High\t\t\t\t\t
Positive control\t\t\t\t\t
```

## 门控与上机记录
- 门控策略：
- 采集事件数：
- 仪器参数：

## 备注
```text
{notes}
```

{bundle}

## Figure Legend 草稿
- Figure X. Flow cytometry analysis of {assay_type} in the indicated groups.
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/ros", response_class=HTMLResponse)
def ros_index():
    files = list_md("03_实验记录/ROS")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project() or {}
    template = env.get_template("ros/index.html")
    return template.render(items=items, active_project=current_project)


@app.post("/ros/new")
def ros_new(
    title: str = Form(...),
    probe: str = Form("DCFH-DA"),
    groups: str = Form(""),
    raw_data: str = Form(""),
    notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "ROS"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_ros_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# ROS 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 探针
{probe}

## 实验分组
```text
{groups}
```

## 原始荧光数据
```text
{raw_data}
```

## 备注
```text
{notes}
```

{bundle}

## Figure Legend 草稿
- Figure X. Intracellular ROS levels in the indicated groups detected using {probe}.
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/jc1", response_class=HTMLResponse)
def jc1_index():
    files = list_md("03_实验记录/JC1")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project() or {}
    template = env.get_template("jc1/index.html")
    return template.render(items=items, active_project=current_project)


@app.post("/jc1/new")
def jc1_new(
    title: str = Form(...),
    groups: str = Form(""),
    ratio_data: str = Form(""),
    notes: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "JC1"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_jc1_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# JC-1 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 实验分组
```text
{groups}
```

## 红 / 绿比值数据
```text
{ratio_data}
```

## 备注
```text
{notes}
```

{bundle}

## Figure Legend 草稿
- Figure X. JC-1 staining and mitochondrial membrane potential changes in the indicated groups.
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.get("/if", response_class=HTMLResponse)
def if_index():
    files = list_md("03_实验记录/IF")
    items = [{"name": f.name, "path": str(f.relative_to(ROOT)), "content": read(f)[:500]} for f in files[:30]]
    current_project = get_current_project() or {}
    template = env.get_template("if/index.html")
    return template.render(items=items, active_project=current_project)


@app.post("/if/new")
def if_new(
    title: str = Form(...),
    target_marker: str = Form(""),
    groups: str = Form(""),
    imaging_notes: str = Form(""),
    quant_data: str = Form(""),
):
    today = date.today().isoformat()
    folder = ROOT / "03_实验记录" / "IF"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{today}_{safe_name(title)}.md"
    current_project = get_current_project() or {}
    project_name = current_project.get("research_object", "") or current_project.get("name", "") or "the project"
    disease_name = current_project.get("disease", "") or "the disease model"
    bundle = build_if_experiment_bundle(project_name, disease_name)

    if not file_path.exists():
        content = f"""# IF 工作台记录｜{title}

## 日期
{today}

## 当前项目
- 项目名称：{current_project.get('name', '')}
- 研究对象：{current_project.get('research_object', '')}
- 疾病 / 模型：{current_project.get('disease', '')}
- 当前阶段：{current_project.get('stage', '')}

## 目标标志物
{target_marker}

## 实验分组
```text
{groups}
```

## 成像记录
```text
{imaging_notes}
```

## 定量数据
```text
{quant_data}
```

{bundle}

## Figure Legend 草稿
- Figure X. Immunofluorescence staining of {target_marker} in the indicated groups.
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)

@app.get("/literature-pool", response_class=HTMLResponse)
def literature_pool():
    files = list_md("04_文献笔记")
    pools = {
        "Introduction": [],
        "Discussion": [],
        "Methods": [],
        "Network Pharmacology": [],
        "Gene / Omics": [],
        "Docking / MD": [],
        "实验设计": []
    }

    rules = {
        "Introduction": "Introduction 可用",
        "Discussion": "Discussion 可用",
        "Methods": "Methods 可借鉴",
        "Network Pharmacology": "Network Pharmacology 可用",
        "Gene / Omics": "Gene / Omics 可用",
        "Docking / MD": "Docking / MD 可用",
        "实验设计": "实验设计可借鉴"
    }

    for f in files:
        content = read(f)
        for pool, key in rules.items():
            if f"- [x] {key}" in content:
                pools[pool].append({
                    "name": f.name,
                    "path": str(f.relative_to(ROOT)),
                    "content": content[:300]
                })

    template = env.get_template("literature_pool.html")
    return template.render(pools=pools, modules=MODULES)


@app.get("/literature-keywords", response_class=HTMLResponse)
def literature_keywords():
    files = list_md("04_文献笔记")
    keywords = ["PI3K", "AKT", "Nrf2", "MAPK", "NF-κB", "炎症", "氧化应激", "凋亡", "缺血性脑卒中", "天然产物"]
    pools = {k: [] for k in keywords}

    for f in files:
        content = read(f)
        lower = content.lower()
        for k in keywords:
            if k.lower() in lower:
                pools[k].append({
                    "name": f.name,
                    "path": str(f.relative_to(ROOT)),
                    "content": content[:300]
                })

    template = env.get_template("literature_keywords.html")
    return template.render(pools=pools, modules=MODULES)


@app.get("/projects-v2", response_class=HTMLResponse)
def projects_v2_page():
    projects = load_projects_v2()
    current_id = get_current_project_id()
    current = get_current_project()

    template = env.get_template("projects_v2/index.html")
    return template.render(
        projects=projects,
        current_id=current_id,
        current=current
    )


@app.post("/projects-v2/switch")
def projects_v2_switch(project_id: str = Form(...)):
    import json

    project_file = ROOT / "projects" / project_id / "project.json"
    if not project_file.exists():
        return HTMLResponse("项目不存在", status_code=404)

    current_file = ROOT / "projects" / "current_project.json"
    current_file.write_text(
        json.dumps({"project_id": project_id}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return RedirectResponse(url="/projects-v2", status_code=303)
