# 数据与模型获取 / Data and Models

本仓库**不包含**数据集与模型权重，因为它们的体积远超 GitHub 的限制。本文件说明去哪里拿、拿到以后放哪里。

This repository **does not include** the dataset or the model weights, because their size far exceeds GitHub's limits. This document explains where to get them and where to put them.

---

## 1. 为什么不在仓库里 / Why not in the repository

GitHub 官方文档对仓库与文件大小的规定（2026 年 11 月核对）：

| 限制项 | 阈值 |
|---|---|
| 单个文件警告 | 50 MiB |
| 单个文件硬性阻止 | **100 MiB**（超过直接拒绝 push，需改用 Git LFS） |
| 通过网页界面上传 | 单个文件不得超过 25 MiB |
| 仓库建议大小 | 理想 < 1 GB，强烈建议 < 5 GB |

对照本项目：

| 内容 | 体积 | 是否入库 |
|---|---|---|
| MOOCCube 原始数据（解压后） | 约 3.9 GB | 否 |
| `google/mt5-small` 基座 | 约 1.1 GB | 否 |
| 三个微调模型合计 | 约 8.5 GB | 否 |
| `kg_transition_cache*.json` | 每个约 9 MB | **是** |
| `1_prototype/database/*.csv` | 约 14 MB | **是** |
| 全部实验结果 | 约 3 MB | **是** |

单个最大的数据文件 `user_video_act.json` 就有 **1.63 GB**，是 100 MiB 上限的 16 倍，因此不存在"压缩一下塞进去"的可能。

---

## 2. MOOCCube 数据集 / The MOOCCube dataset

### 2.1 来源 / Source

MOOCCube 由清华大学知识工程实验室（THU-KEG）构建，配套论文发表于 ACL 2020，采用 **CC0-1.0** 许可（公有领域贡献），可自由使用与再分发。

- 项目主页：<https://github.com/thukg/MOOCCube>
- 数据下载：<http://moocdata.cn/data/MOOCCube>
- 论文：Yu, Jifan, et al. "MOOCCube: A Large-Scale Data Repository for NLP Applications in MOOCs." *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*, 2020, pp. 2357–2366.

> 注意：该数据集包含学堂在线（XuetangX）的真实用户行为记录。虽然许可是 CC0，但涉及个人学习行为数据，**建议只用于研究，不要二次发布用户级原始记录**。

### 2.2 下载与放置 / Download and placement

1. 打开 <http://moocdata.cn/data/MOOCCube>，下载主仓库压缩包（约 1 GB 压缩，解压后约 3.9 GB）；
2. 解压；
3. 把得到的 `MOOCCube/` 目录整体放到本仓库的 `data/` 下：

```
moocube-lpr/
└── data/
    └── MOOCCube/
        ├── entities/                 concept.json, course.json, video.json, user.json, paper.json ...
        ├── relations/                concept-concept.json, course-concept.json, user-video.json ...
        ├── additional_information/   prerequisite_prediction.json, concept_infomation.json ...
        └── MOOCQA/                   multi_hop/, tuples/ ...
```

4. 如果你的数据放在别处，设置环境变量即可，**不必改代码**：

```bash
# Windows PowerShell
$env:MOOCCUBE_DIR = "E:/datasets/MOOCCube"
# Linux / macOS
export MOOCUBE_DIR="/data/MOOCCube"
```

### 2.3 本仓库实际用到的文件 / Files actually used

不必等全量数据下载完就能开工，建图只需要以下几类：

| 用途 | 文件 |
|---|---|
| 概念与先修关系（核心） | `relations/prerequisite-dependency.json`、`additional_information/prerequisite_prediction.json` |
| 实体 | `entities/concept.json`、`entities/course.json`、`entities/video.json` |
| 关系 | `relations/concept-paper.json`、`relations/course-concept.json`、`relations/video-concept.json` |

---

## 3. 模型权重 / Model weights

### 3.1 基座模型 / Base model

```bash
python scripts/download_mt5.py
```

脚本会调用 `huggingface_hub.snapshot_download` 把 `google/mt5-small` 拉到 `models/MT5_small`。若访问 Hugging Face 有困难，可先设置镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com      # Linux / macOS
$env:HF_ENDPOINT = "https://hf-mirror.com"    # Windows PowerShell
```

### 3.2 微调模型 / Fine-tuned models

仓库不附带三个微调权重，需要用阶段一的脚本自行训练：

| 模型 | 训练脚本 | 输出目录 | 作用 |
|---|---|---|---|
| 策略模型 | `1_prototype/2.初步微调模型.py` | `models/zhuanjiamodel` | 生成学习路径 |
| 成本模型 | `1_prototype/4.训练成本模型.py` | `models/chengbenmodel` | 估计概念学习成本 |
| 安全模型 | `1_prototype/5.RL 训练框架.py` | `models/finalsafemodel` | RL 精调后的策略 |

每个模型的目录可用环境变量覆盖：

```bash
MOOCUBE_POLICY_MODEL   默认 models/zhuanjiamodel
MOOCUBE_COST_MODEL     默认 models/chengbenmodel
MOOCUBE_SAFE_MODEL     默认 models/finalsafemodel
MOOCUBE_BASE_MODEL     默认 models/MT5_small
```

---

## 4. 约束查找表 / Constraint lookup table

`kg_transition_cache.json`（约 9 MB）与 `kg_transition_cache1.json` 是图的邻接表，**已随仓库提供**，所以复现阶段三、跑演示平台都不需要数据库。

如果想从原始数据重建：

```bash
python 2_generation/1_build_kg_cache.py     # 需要先建好 Neo4j 图
```

它的结构是一张字典：键为当前概念，值为合法后继列表。

```json
{
  "支持向量机": ["线性代数", "凸优化", "统计学习基础"],
  "线性代数": ["矩阵运算", "向量空间"]
}
```

---

## 5. 复现环境 / Environment

| 阶段 | 依赖 | 是否需要 GPU |
|---|---|---|
| 阶段一 原型 | `neo4j` / `py2neo` / `transformers` / `torch` / `datasets` | 微调时需要 |
| 阶段二 生成 | 上述 + `sentence-transformers`（仅两个新基线需要） | 推理时建议有 |
| 阶段三 双态 | `numpy` / `networkx` / `scipy` / `matplotlib` | **不需要** |
| 演示平台 | 仅 Python 标准库 | **不需要** |

Python 3.10 及以上。安装全部依赖：

```bash
pip install -r requirements.txt
```

`torch` 请按自己的 CUDA 版本单独安装，见 <https://pytorch.org/get-started/locally/>。

---

## 6. 许可与引用 / License and citation

- MOOCCube 原始数据：**CC0-1.0**，可自由使用与再分发
- 本仓库代码：**MIT**
- 本仓库 `data/` 下的派生 CSV：沿用 CC0-1.0

引用数据集请标注：

> Yu, Jifan, et al. "MOOCCube: A Large-Scale Data Repository for NLP Applications in MOOCs." *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*, 2020, pp. 2357–2366.
