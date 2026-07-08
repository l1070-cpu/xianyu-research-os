# Docking Capability Pack｜分子对接能力包

## 输入
- 配体结构
- 靶点蛋白
- PDB ID

## 标准工作流
PubChem 下载配体 → PDB 下载蛋白 → OpenBabel 转换 → AutoDock Vina 对接 → PyMOL 可视化 → 结合能整理。

## 输出
- docking_results.xlsx
- binding_pose.png
- interaction_figure.png
