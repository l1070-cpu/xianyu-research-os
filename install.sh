#!/bin/bash
set -e

echo "🐟 初始化咸鱼日常打工 OS..."

if ! command -v conda &> /dev/null
then
  echo "未检测到 conda，请先安装 Miniconda。"
else
  conda env create -f environment.yml || echo "环境可能已存在，跳过创建。"
fi

echo "✅ 完成。下一步运行：conda activate xianyu-os"
