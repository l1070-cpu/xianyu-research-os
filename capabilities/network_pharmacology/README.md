# Network Pharmacology Capability Pack｜网络药理学能力包

## 输入
- 成分表
- 疾病名称
- 靶点数据库结果

## 标准工作流
成分 → 靶点预测 → 疾病靶点 → 交集 → STRING PPI → GO/KEGG → Cytoscape 网络 → 核心靶点筛选。

## 输出
- compound_target.xlsx
- disease_target.xlsx
- intersect_target.xlsx
- GO_result.xlsx
- KEGG_result.xlsx
- PPI_network
- Cytoscape 图
