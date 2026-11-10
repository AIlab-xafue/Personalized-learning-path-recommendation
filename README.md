# 知识图谱约束下的个性化学习路径推荐

**Knowledge-Graph-Constrained Personalized Learning Path Recommendation**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Data: MOOCCube](https://img.shields.io/badge/Data-MOOCCube%20(CC0)-green)](docs/DATA.md)

[English](README_EN.md) | 简体中文

---

本仓库是一门硕士学位论文及其两篇小论文的配套代码。它把"给一名学生排一条合法且可执行的学习路径"拆成三个前后衔接的环节——**生成、执行、演化**——并给出每一环的可复现实验脚本、实验输出与一个可离线运行的演示平台。

> **一句话概括**：先让模型在知识图谱的合法边界内生成路径（不幻觉），再让它按学生的认知状态与情绪负荷在执行期局部修补（不改整条路），最后在跨轮次上滚动重规划（该改才改）。

---

## 目录

- [1. 解决什么问题](#1-解决什么问题)
- [2. 方法：三个环节](#2-方法三个环节)
- [3. 仓库结构](#3-仓库结构)
- [4. 快速开始](#4-快速开始)
- [5. 数据与模型](#5-数据与模型)
- [6. 结果口径](#6-结果口径)
- [7. 文件说明](#7-文件说明)
- [8. 引用](#8-引用)
- [9. 许可](#9-许可)
- [10. 已知限制](#10-已知限制)

---

## 1. 解决什么问题

MOOC 场景下的学习路径推荐有两个长期分家的做法：

- **图方法**（最短路、拓扑排序、图嵌入推荐）保证路径在图上是合法的，但它不读文本、不懂语义，容易排出"结构正确、教学上讲不通"的序列；
- **大模型方法**（提示工程、微调生成）能读懂课程语义，但它会**结构性幻觉**——生成知识图谱里根本不存在的先修边。

第一段代码要回答的是：能不能让生成模型**只在图上真实存在的边里走**，同时保留语言模型的语义规划能力。

第二段代码要回答的是：路径排出来之后，学生真实学习会卡住、会烦躁、会中途放弃，**这条静态路径怎么在执行期被修补**，以及修补到什么程度就该整条重排。

---

## 2. 方法：三个环节

### 2.1 生成：软硬约束协同解码

| 成分 | 做什么 | 实现位置 |
|---|---|---|
| 软约束 | 把检索到的先修知识写进提示，给模型"往哪走"的方向感 | `2_soft_constraint_rag.py` |
| 硬约束 | 用前缀树（Trie）把当前概念的所有非法后继 Token 的 logits 置为 −∞ | `3_hard_constraint_decoding.py` |
| 防环束搜索 | 多束并行 + 重复惩罚，解决束搜索的短视与绕圈 | `4_fusion_generation.py` |

关键设计是**先离线把图变成查找表**：`1_build_kg_cache.py` 从 Neo4j 导出邻接表 `kg_transition_cache.json`，推理时不再查库，把约束判断降为常数时间。

### 2.2 执行：双态画像与类型化路由

学生状态被拆成两个量：**认知准备度**与**情感负荷**。二者分开更新，因为"学不会"和"学烦了"是两种失败，处理方式完全不同：

- 负荷越过阈值 → 切换资源形态（视频/多模态）做**恢复**；
- 认知失败 → 插入先修补救 → **回到被阻塞的目标**；
- 其余情况 → 原路径上重试。

"目标保持"是这一环的硬性要求：任何支持动作之后都必须回到原目标，且补救成功**不计入**掌握。

### 2.3 演化：滚动重规划

跨轮次看，学生状态会漂移。重规划的目标函数在四项代价（失败风险、难度失配、绕行成本、重复访问）之外加了一项**稳定性正则**，用来抑制"每轮都改道"的抖动。触发条件是稀疏的：开局、每若干轮复核、连续失败、负荷跨阈值。

---

## 3. 仓库结构

```
moocube-lpr/
├── README.md                 本文件（中文）
├── README_EN.md              English version
├── LICENSE                   MIT（代码）+ CC0 数据声明
├── requirements.txt          运行依赖
├── .gitignore
│
├── docs/
│   ├── FILE_INDEX.md         ★ 逐文件说明（中英对照）
│   ├── DATA.md               数据集与模型权重获取
│   └── UPLOAD_GUIDE.md       ★ 从零上传到 GitHub 的完整步骤
│
├── 1_prototype/              阶段一：小规模原型（Neo4j + mT5 微调 + 简化 RL）
│   ├── 0.解析数据集转换成知识图谱.py
│   ├── 1.先修关系提取数据集.py
│   ├── 2.初步微调模型.py
│   ├── 3.初步使用模型.py
│   ├── 4.训练成本模型.py
│   ├── 5.RL 训练框架.py
│   └── database/             由 MOOCCube 转出的 18 个 CSV（约 14 MB）
│
├── 2_generation/             阶段二：路径生成（软/硬约束解码、基线、消融）
│   ├── 0.*.py                建图：TSV 导入、数据集转 KG、补先修关系
│   ├── 1_build_kg_cache.py   导出约束查找表
│   ├── 2_soft_constraint_rag.py     基线：仅提示
│   ├── 3_hard_constraint_decoding.py 硬约束：Trie 掩码
│   ├── 4_fusion_generation.py       本文：软硬融合 + 防环束搜索
│   ├── 5_evaluate_legality.py       评估：SL / LR / EPR / AL
│   ├── 6-10 + 两个新基线.py          对照实验（KGR / RL / CoT / A* / GRU）
│   ├── *消融实验.py                  束宽与重复惩罚的取值依据
│   └── kg_transition_cache.json      约束查找表（约 9 MB，可重建）
│
├── 3_dual_state/             阶段三：双态执行与动态演化
│   ├── 1-6.*.py              从环境、模拟器、画像到批量实验
│   ├── 7_dual_state_extended_experiments.py   补充实验（含消融与统计检验）
│   ├── 8_dynamic_path_evolution.py            ★ 滚动重规划主实验（DTE-RR）
│   ├── 9-12_*.py             多种子稳健性、路径来源敏感性
│   ├── 13_export_subject_tasks.py            五学科任务包导出
│   ├── 10_export_platform_data.py            为平台导出 JSON
│   └── *_outputs/            ★ 已跑好的实验结果（CSV / JSON / PNG）
│
├── platform/                 可视化演示平台（纯静态 + stdlib 服务）
│   ├── index.html            单页应用，六个页签
│   ├── server.py             本地 HTTP 服务，零第三方依赖
│   ├── assets/               app.js / engine.js / app.css / echarts.min.js
│   └── data/                 graph / task / subjects / trajectories / aggregate
│
├── scripts/
│   └── download_mt5.py       下载基座模型 google/mt5-small
│
└── data/                     外部数据放置目录（内容不随仓库分发）
    ├── README.md             数据从哪来、放哪里
    └── MOOCCube/relations/
        └── prerequisite-dependency.json   先修关系表，55 KB，随仓库提供，
                                           使第 3 阶段无需下载全量数据集
```

`docs/FILE_INDEX.md` 里有逐文件的中英文说明，包括每个脚本的输入、输出与对应论文章节。

---

## 4. 快速开始

### 4.1 零依赖体验：先看演示平台

演示平台只用 Python 标准库，不需要装任何包、不需要数据库、不需要 GPU：

```bash
git clone https://github.com/<your-username>/moocube-lpr.git
cd moocube-lpr/platform
python server.py            # 自动打开 http://127.0.0.1:8770
```

`platform/data/` 里已经放好了图谱、任务、回放轨迹与聚合结果，克隆下来即可运行。

> 直接双击 `index.html` 会白屏：页面用 `fetch` 读 `data/*.json`，浏览器不允许 `file://` 跨源请求，必须通过上面的本地服务访问。

### 4.2 轻量复现：第 3 阶段实验（CPU，无需 GPU 与数据库）

第 3 阶段的脚本只依赖 `numpy`、`networkx`、`matplotlib`，学习者由模拟器生成。它们唯一的外部输入是先修关系表，而这份文件只有 55 KB，**已随仓库提供**（`data/MOOCCube/relations/prerequisite-dependency.json`）。所以**不需要下载 3.9 GB 数据集、不需要 Neo4j、不需要模型权重**：

```bash
pip install numpy networkx scipy matplotlib

cd 3_dual_state

# 补充实验：消融、人群异质性、统计检验（约 1-2 分钟）
python 7_dual_state_extended_experiments.py

# 主实验：状态演化 + 滚动重规划（DTE-RR）
python 8_dynamic_path_evolution.py

# 多种子稳健性：把同一协议在 10 个种子上重复
python 9_dynamic_multiseed.py
```

输出写到 `3_dual_state/*_outputs/`，与仓库中已提交的结果可直接对比。

### 4.3 完整复现：第 1、2 阶段（需 Neo4j + GPU）

前置条件：

1. 安装 **Neo4j 5.x** 并启动，记住连接地址与口令；
2. 按 [docs/DATA.md](docs/DATA.md) 下载 MOOCCube 到 `data/MOOCCube/`；
3. 设置环境变量：

```bash
# Windows (PowerShell)
$env:NEO4J_PASSWORD = "你的口令"
$env:MOOCCUBE_DIR   = "data/MOOCCube"

# Linux / macOS
export NEO4J_PASSWORD="你的口令"
export MOOCCUBE_DIR="data/MOOCCube"
```

下载并微调基座模型：

```bash
python scripts/download_mt5.py                       # → models/MT5_small
python 1_prototype/2.初步微调模型.py                  # → models/zhuanjiamodel
```

建图并生成约束缓存（**所有脚本请在仓库根目录下运行**）：

```bash
python 2_generation/0.数据集转知识图谱.py             # MOOCCube → Neo4j
python 2_generation/1_build_kg_cache.py              # Neo4j → 邻接表 JSON
```

跑三组对照并评估：

```bash
python 2_generation/2_soft_constraint_rag.py         # 基线：仅提示
python 2_generation/3_hard_constraint_decoding.py    # 硬约束
python 2_generation/4_fusion_generation.py           # 本文方法
python 2_generation/5_evaluate_legality.py           # 汇总成表
```

---

## 5. 数据与模型

**本仓库不包含数据集与模型权重**，原因只有一个：体积。MOOCCube 解压后约 3.9 GB，四个微调模型合计约 9.6 GB，两者都远超 GitHub 对单文件 100 MiB 的硬限制与仓库 1 GB 的建议上限。

| 内容 | 体积 | 处理方式 |
|---|---|---|
| MOOCCube 原始数据 | 约 3.9 GB | 自行下载到 `data/MOOCCube/`，见 [docs/DATA.md](docs/DATA.md) |
| `mt5-small` 基座 | 约 1.1 GB | `python scripts/download_mt5.py` |
| 三个微调模型 | 约 8.5 GB | 用 `1_prototype/2.初步微调模型.py` 自行训练 |
| `kg_transition_cache*.json` | 各约 9 MB | **已随仓库提供**，也可由 Neo4j 重建 |
| 全部实验结果 | 约 3 MB | **已随仓库提供** |

MOOCCube 由清华大学知识工程实验室以 CC0-1.0 许可发布，可自由再分发；但其体积不适合放进 Git 仓库，因此这里只提供下载指引。

---

## 6. 结果口径

仓库里有两套数字，**不要混用**：

| 来源 | 用途 | 是否可复现结论 |
|---|---|---|
| `3_dual_state/dynamic_outputs/*.json` | Python 实验的真实输出，论文表格数值来源 | 是 |
| `platform/assets/engine.js` 的双轨回放 | JavaScript 复刻，用于**演示机制** | 否，随机流实现不同（LCG vs Python `random`），单次回放步数不会与论文逐位一致 |

几条从输出中可以直接读到的结论：

- 硬约束把**幻觉率降到 0**：加入 Trie 掩码后，生成的每一条边都在图谱中真实存在；
- 但"合法"不等于"不绕圈"：只加掩码时无环率仍有缺口，需要防环惩罚补齐——这也是 `4_fusion_generation.py` 里两项机制同时存在的理由；
- 动态重规划的完成率增益在**1–3 个百分点**量级，且部分随机种子下的置信区间**跨零**；论文因此把结论限定为"重规划相对仅演化的增益更稳定"，而不是"动态全面优于静态"。

具体数值请直接读 `3_dual_state/*_outputs/` 下的 CSV 与 JSON，README 不再转述，以免与表格脱节。

---

## 7. 文件说明

逐文件的中英文说明见 **[docs/FILE_INDEX.md](docs/FILE_INDEX.md)**，包含每个脚本的作用、输入、输出与对应的论文章节。

上传到自己的 GitHub 仓库的操作步骤见 **[docs/UPLOAD_GUIDE.md](docs/UPLOAD_GUIDE.md)**。

---

## 8. 引用

如果本仓库的代码或思路对你的研究有帮助，请引用：

```bibtex
@mastersthesis{chen2026learningpath,
  author  = {Chen, Yu},
  title   = {Knowledge-Graph-Constrained Personalized Learning Path
             Recommendation with Dual-State Execution and Rolling Replanning},
  school  = {Xi'an University of Finance and Economics},
  year    = {2026},
  type    = {Master's thesis}
}
```

所用数据集的原始文献：

> Yu, Jifan, et al. "MOOCCube: A Large-Scale Data Repository for NLP Applications in MOOCs." *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics*, 2020, pp. 2357–2366.

---

## 9. 许可

- **代码**：MIT，见 [LICENSE](LICENSE)
- **data/ 下的 CSV**：源自 MOOCCube（CC0-1.0），可自由使用与再分发

---

## 10. 已知限制

写在这里，是为了避免读者把结论读得比证据更满：

1. **学习者状态是模拟的**。第 3 阶段的全部数值来自规则化的学习者模拟器，不是真实教学实验。它证明的是机制在给定假设下自洽，不能替代课堂效果验证。
2. **图谱规模有限**。生成阶段采样了 747 个概念，演示子图为 410 个概念、905 条先修边，都是 MOOCCube 的子集，未在全量图上验证。
3. **动态增益幅度不大**。完成率提升在 1–3 个百分点量级，部分区间跨零，属于有条件成立的机制而非显著优于所有基线。
4. **学科划分是人工的**。第 3 阶段导出的五个学科任务包按概念语义人工归类，图本身不带宽严的课程标签，边界并不闭合。
5. **模型权重需自行训练**。仓库未附带微调权重，复现第 2 阶段需要按第 4.3 节的步骤自行训练，结果会随随机种子与硬件略有差异。
