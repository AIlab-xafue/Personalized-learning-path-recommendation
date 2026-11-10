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
├── README.md                             中文主文档
├── README_EN.md                          English version
├── LICENSE                               MIT（代码）+ CC0 数据声明
├── CITATION.cff                          引用元数据，GitHub 显示「Cite」按钮
├── requirements.txt                      第三方依赖，按用途分组
├── .gitignore                            排除模型、数据集、虚拟环境
├── .gitattributes                        统一换行；标注 echarts 为第三方库
├── docs/                                 说明、数据、上传指南、覆盖自检
│   ├── FILE_INDEX.md                     ★ 119 个文件逐个说明（中英对照）
│   ├── DATA.md
│   ├── UPLOAD_GUIDE.md                   ★ 从零上传到 GitHub 的完整步骤
│   └── check_file_index.py               自检：是否有文件未被说明
├── data/                                 外部数据落位（只带一个 55 KB 先修表）
│   ├── README.md                         数据从哪来、放哪里
│   └── MOOCCube/                         原始数据集下载到这里（不入库）
│       └── relations/
│           └── prerequisite-dependency.json 先修关系表 55 KB，让阶段三免下载 3.9 GB
├── 1_prototype/                          阶段一：小规模原型（Neo4j + mT5 微调 + 简化 RL）
│   ├── 0.解析数据集转换成知识图谱.py
│   ├── 1.先修关系提取数据集.py
│   ├── 2.初步微调模型.py
│   ├── 3.初步使用模型.py
│   ├── 4.训练成本模型.py
│   ├── 5.RL 训练框架.py
│   └── database/                         由 MOOCCube 转出的 18 张表（约 13 MB）
│       ├── concept.csv
│       ├── course.csv
│       ├── video.csv
│       ├── paper.csv
│       ├── teacher.csv
│       ├── school.csv
│       ├── user.csv
│       ├── rel_prerequisite_dependency.csv
│       ├── rel_course_concept.csv
│       ├── rel_course_video.csv
│       ├── rel_video_concept.csv
│       ├── rel_concept_paper.csv
│       ├── rel_field_concept.csv
│       ├── rel_school_course.csv
│       ├── rel_school_teacher.csv
│       ├── rel_teacher_course.csv
│       ├── rel_user_course.csv
│       └── rel_user_video.csv
├── 2_generation/                         阶段二：路径生成（软/硬约束解码、基线、消融、结果）
│   ├── 0.数据集转知识图谱.py
│   ├── 0.TSV文件导入关系.py
│   ├── 0.补充先修关系.py
│   ├── 0_delete_relations.cypher
│   ├── 1_build_kg_cache.py               ★ 导出约束查找表（Neo4j → 本地）
│   ├── 2_soft_constraint_rag.py
│   ├── 3_hard_constraint_decoding.py     ★ 硬约束：Trie + logits 掩码
│   ├── 4_fusion_generation.py            ★ 本文方法：软硬融合 + 防环束搜索
│   ├── 4.融合_提示词多问题.py
│   ├── 4_fusion_generation_差异化画像对比试验.py
│   ├── 5_evaluate_legality.py            ★ 指标：SL / LR / EPR / AL
│   ├── 6_单门课适用实验.py
│   ├── 7_单门课三组对比试验.py
│   ├── 8_对比KGR (基于图的传统推荐).py
│   ├── 9_对比“基于强化学习的路径推荐”.py
│   ├── 10_对比“纯 Prompt Engineering (CoT  Few-shot)”.py
│   ├── 两个新基线.py
│   ├── 束搜索宽度（Beam Size）进行消融实验.py
│   ├── 防环惩罚系数消融.py
│   ├── kg_transition_cache.json          约束表 8.9 MB，可重建
│   ├── generated_results_soft.txt
│   ├── generated_results_hard.txt
│   ├── generated_results_fusion.txt
│   ├── generated_results_fusion_final.txt
│   ├── generated_results_single_course.txt
│   ├── beam_size_ablation_results.csv
│   ├── repetition_penalty_ablation_results.csv
│   └── baseline_astar_grurnn_results.csv
├── 3_dual_state/                         阶段三：双态执行与动态演化
│   ├── 1.构建目标导向的环境与图谱.py
│   ├── 2.构建高保真用户模拟器.py
│   ├── 3.构建智能体与动态画像.py
│   ├── 4.极速生成路径-多交互主实验.py
│   ├── 5.双版本主实验.py
│   ├── 6.批量多学生实验.py
│   ├── 7_dual_state_extended_experiments.py
│   ├── 8_dynamic_path_evolution.py       ★ 滚动重规划主实验（DTE-RR，D1–D6）
│   ├── 9_dynamic_multiseed.py            十种子稳健性（复用 8 号脚本）
│   ├── 10_export_platform_data.py        为平台导出 JSON
│   ├── 11_path_source_sensitivity.py
│   ├── 12_multiseed_robustness.py
│   ├── 13_export_subject_tasks.py        五学科任务包导出
│   ├── kg_transition_cache1.json         阶段三用邻接表 8.4 MB（410 概念子图）
│   ├── README_dynamic_experiments.md     D1–D6 设计说明
│   ├── README_补充实验_中期.md           中期补充实验说明
│   ├── paper_revision/                   论文修订辅助（依赖外部 _docx_kit，可读不跑）
│   │   ├── patch_cn_paper.py
│   │   └── patch_en_paper.py
│   ├── dual_state_outputs/               7 号脚本输出：9 个文件
│   │   ├── experiment_summary.json
│   │   ├── main_experiment_per_seed.csv
│   │   ├── ablation_per_seed.csv
│   │   ├── cohort_per_seed.csv
│   │   ├── sensitivity_per_seed.csv
│   │   ├── statistical_tests.csv
│   │   ├── figure1_dual_state_framework.png
│   │   ├── figure2_main_outcomes.png
│   │   └── figure3_video_sensitivity.png
│   ├── dynamic_outputs/                  8、9 号脚本输出：10 个文件
│   │   ├── meta.json                     种子、耗时、图规模、全部超参
│   │   ├── d1_main.json
│   │   ├── d1_main.csv
│   │   ├── d2_heterogeneity.json
│   │   ├── d3_frequency.json
│   │   ├── d4_lag_prior.json
│   │   ├── d5_budget.json
│   │   ├── d6_shock.json
│   │   ├── m1_multiseed.json
│   │   └── m1_multiseed.csv
│   └── thesis_outputs/                   11、12 号脚本输出：3 个文件
│       ├── multiseed_robustness.json
│       ├── path_source_sensitivity.json
│       └── path_source_sensitivity.csv
├── platform/                             离线演示平台（纯静态 + 标准库服务）
│   ├── index.html                        单页应用，六个页签
│   ├── server.py                         本地服务，零第三方依赖
│   ├── 启动平台.bat                      Windows 一键启动
│   ├── README.md
│   ├── assets/                           前端资源
│   │   ├── app.js
│   │   ├── engine.js                     ★ JS 版仿真引擎（双轨回放）
│   │   ├── app.css
│   │   └── echarts.min.js
│   └── data/                             平台数据（由 10、13 号脚本导出）
│       ├── graph.json                    410 概念 / 905 边
│       ├── task.json
│       ├── subjects.json
│       ├── trajectories.json
│       └── aggregate.json
└── scripts/                              辅助脚本
    └── download_mt5.py                   下载基座模型 google/mt5-small
```

上面的树是**全量清单**——仓库 119 个文件一个未省略。每个文件做什么、吃什么、吐什么，见 `docs/FILE_INDEX.md`（中英对照，含 18 张数据表逐表说明与 22 个结果文件逐文件说明）。增删文件后可运行 `python docs/check_file_index.py` 自检是否有文件漏写。

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
