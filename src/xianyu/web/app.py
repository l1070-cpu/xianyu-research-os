from pathlib import Path
from dotenv import load_dotenv
import re
import csv
import os
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

def safe_name(name):
    return name.replace(" ", "_").replace("/", "_")


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

        content = f"""# 论文写作｜{title}

## 日期
{today}

## 写作部分
{section_map.get(section_type, "Discussion")}

## 本部分目的

## 已有数据 / 图表

## 核心结论

## 需要引用的文献
{extra_results_context}{extra_discussion_context}{extra_methods_context}{extra_introduction_context}{extra_abstract_context}{extra_cover_context}{extra_highlights_context}{extra_conclusion_context}{extra_keywords_context}{extra_title_context}

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
def writing_network_cover_letter_new(title: str = Form(...)):
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

    if not file_path.exists():
        content = f"""# Cover Letter 草稿｜{title}

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

{cover_letter_bundle}

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
def writing_network_graphical_abstract_new(title: str = Form(...)):
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

    if not file_path.exists():
        content = f"""# Graphical Abstract 要点｜{title}

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

{graphical_abstract_bundle}

## 画图执行备注
- 推荐版式：
- 推荐主色：
- 需要保留的核心元素：

## 修改记录
"""
        file_path.write_text(content, encoding="utf-8")

    return RedirectResponse(url=f"/file?path={file_path.relative_to(ROOT)}", status_code=303)


@app.post("/writing/network-highlights/new")
def writing_network_highlights_new(title: str = Form(...)):
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

    if not file_path.exists():
        content = f"""# Highlights 草稿｜{title}

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

{highlights_bundle}

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
