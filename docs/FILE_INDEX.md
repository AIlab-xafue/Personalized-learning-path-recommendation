# 文件说明 / File Index

本文件逐个说明仓库里每个脚本**做什么、吃什么、吐什么**。中文与英文并列，方便老师审阅与外部读者阅读。

This document describes **what each file does, what it reads, and what it produces**, in Chinese and English side by side.

> **运行约定 / Convention**：所有脚本都假定**当前工作目录为仓库根目录**。脚本内部的相对路径（如 `models/zhuanjiamodel`、`data/MOOCCube`）都可用环境变量覆盖，见 README 第 4.3 节。
> All scripts assume the **current working directory is the repository root**. Relative paths can be overridden by environment variables; see README §4.3.

---

## 0. 根目录文件 / Root files

| 文件 / File | 中文说明 | English |
|---|---|---|
| `README.md` | 中文主文档：研究问题、三阶段方法、目录结构、复现步骤、结果口径、已知限制 | Chinese main document: problem, method, layout, reproduction steps, how to read numbers, limitations |
| `README_EN.md` | 上文的英文版，信息等价 | English counterpart of the above |
| `LICENSE` | 代码采用 MIT；附 MOOCCube（CC0-1.0）数据声明 | MIT for code, plus a CC0-1.0 notice for the derived data |
| `requirements.txt` | 全部第三方依赖，按用途分组 | All third-party dependencies, grouped by purpose |
| `.gitignore` | 排除数据集、模型权重、虚拟环境、IDE 文件与本地密钥 | Excludes datasets, model weights, virtualenvs, IDE files and local secrets |
| `docs/FILE_INDEX.md` | 本文件 | This file |
| `docs/DATA.md` | 数据集与模型权重的获取方式与放置位置 | How to obtain the dataset and model weights, and where to put them |
| `docs/UPLOAD_GUIDE.md` | 从零把本仓库上传到 GitHub 的完整步骤 | Full walkthrough for publishing this repository on GitHub |
| `data/README.md` | 说明 `data/` 是外部数据落位目录，本身不含数据 | Explains that `data/` is a mount point and contains no data itself |

---

## 1. `1_prototype/` —— 阶段一：小规模原型 / Stage 1: small-scale prototype

这一阶段验证"能不能跑通"：把 MOOC 数据灌进图数据库、微调一个中文生成模型、跑通一次检索增强的路径生成。它是后续两阶段的工程基础，规模小、逻辑直白。

This stage proves feasibility: load MOOC data into a graph database, fine-tune a Chinese generative model, and run retrieval-augmented path generation once. It is the engineering foundation for the later stages — small in scale, straightforward in logic.

| 文件 / File | 中文说明 | English |
|---|---|---|
| `0.解析数据集转换成知识图谱.py` | 读取 `database/` 下 18 个 CSV，按实体/关系类型批量写入 Neo4j（批量 5000 条/事务）。**输入**：`database/*.csv`；**输出**：Neo4j 中的概念、课程、视频、用户及关系 | Reads the 18 CSVs under `database/` and batch-loads entities and relations into Neo4j (5000 rows per transaction). **In**: `database/*.csv`; **Out**: concepts, courses, videos, users and relations in Neo4j |
| `1.先修关系提取数据集.py` | 从图谱中按"双重先修关系"抽取问答对，构造微调语料（默认 3000 条）。**输入**：Neo4j；**输出**：`training_data_final.jsonl` | Extracts QA pairs via "dual prerequisite" traversal to build a fine-tuning corpus (3000 by default). **In**: Neo4j; **Out**: `training_data_final.jsonl` |
| `2.初步微调模型.py` | 用 `MT5ForConditionalGeneration` + `Trainer` 在本地基座模型上微调，产出策略模型。**输入**：`models/MT5_small`、上一步的 jsonl；**输出**：`models/zhuanjiamodel` | Fine-tunes `MT5ForConditionalGeneration` with `Trainer`. **In**: `models/MT5_small` and the jsonl above; **Out**: `models/zhuanjiamodel` |
| `3.初步使用模型.py` | 加载微调模型 + 实时查 Neo4j 检索先修知识，跑一次检索增强推理。**输入**：策略模型、Neo4j；**输出**：控制台路径 | Loads the fine-tuned model and queries Neo4j at inference time. **In**: policy model, Neo4j; **Out**: paths printed to console |
| `4.训练成本模型.py` | 训练一个"序列分类"头来估计学习成本/难度（`MT5ForSequenceClassification`）。**输入**：样本 jsonl；**输出**：`models/chengbenmodel` | Trains a sequence-classification head as a cost/difficulty estimator. **In**: sample jsonl; **Out**: `models/chengbenmodel` |
| `5.RL 训练框架.py` | 手写的最小 RLHF 循环：策略模型 + 成本模型 + 安全模型，不依赖 TRL，规避版本冲突。**输入**：三个模型 + 提示数据；**输出**：`models/finalsafemodel` | A hand-written minimal RLHF loop (policy + cost + safety model) with no TRL dependency, avoiding version conflicts. **Out**: `models/finalsafemodel` |
| `database/*.csv` | 由 MOOCCube 转出的 18 张表（概念、课程、视频、教师、学校及各类关系），共约 14 MB，可直接用于建图 | 18 tables converted from MOOCCube (concepts, courses, videos, teachers, schools and relations), ~14 MB, ready for graph loading |

**运行顺序 / Order**: `0` → `1` → `2` → `3`；`4`、`5` 为可选分支（成本模型与 RL 精调）。

---

## 2. `2_generation/` —— 阶段二：路径生成 / Stage 2: path generation

这一阶段回答"怎么让模型只在图上真实存在的边里走"。核心是三组对照：仅提示（基线）、仅硬约束、软硬融合。

This stage answers "how to force the model to walk only on edges that really exist". The core is a three-way comparison: prompt-only (baseline), hard-constraint-only, and fusion.

### 2.1 建图与缓存 / Graph construction and caching

| 文件 / File | 中文说明 | English |
|---|---|---|
| `0.数据集转知识图谱.py` | 全量 MOOCCube → Neo4j：遍历 `entities/` 与 `relations/` 下的 JSON/TSV 批量入库。**输入**：`data/MOOCCube`；**输出**：Neo4j 全量图 | Loads the full MOOCCube into Neo4j by walking `entities/` and `relations/`. **In**: `data/MOOCCube`; **Out**: full graph in Neo4j |
| `0.TSV文件导入关系.py` | 单独导入 `relations/prerequisite-dependency.json` 这一条先修关系链（文件名沿用历史叫法） | Imports only the `prerequisite-dependency.json` relation chain (the filename keeps its historical wording) |
| `0.补充先修关系.py` | 把 `additional_information/prerequisite_prediction.json`（算法预测的先修关系）作为 `PREREQUISITE_PRED` 补入，提升约束覆盖率 | Adds the predicted prerequisites as `PREREQUISITE_PRED` to increase constraint coverage |
| `0_delete_relations.cypher` | 一段 Cypher 脚本（**不是 Python**），分批删除 `KNOWS` 关系，用于清库重来 | A Cypher snippet (**not Python**) that deletes `KNOWS` relations in batches, for a clean rebuild |
| `1_build_kg_cache.py` | **关键基础设施**：从 Neo4j 导出全量先修关系到本地邻接表，推理时不再查库。**输入**：Neo4j；**输出**：`kg_transition_cache.json`（约 9 MB） | **Key infrastructure**: exports all prerequisite edges into a local adjacency table so inference never hits the database. **Out**: `kg_transition_cache.json` (~9 MB) |

### 2.2 生成方法 / Generation methods

| 文件 / File | 中文说明 | English |
|---|---|---|
| `2_soft_constraint_rag.py` | **基线**：把检索到的先修知识写进提示，不强制解码。用于复现"结构性幻觉"，给硬约束提供对照依据 | **Baseline**: injects retrieved prerequisites into the prompt with no decoding constraint. Reproduces structural hallucination and motivates the hard constraint |
| `3_hard_constraint_decoding.py` | **硬约束**：针对当前概念的合法后继动态构建 Token 级 Trie，通过 `prefix_allowed_tokens_fn` 把非法 Token 的 logits 置为 −∞ | **Hard constraint**: builds a token-level Trie over legal successors and masks illegal logits to −∞ via `prefix_allowed_tokens_fn` |
| `4_fusion_generation.py` | **本文方法**：软约束（个性化画像注入）+ 硬约束（Trie 掩码）+ 防环束搜索，三者协同 | **Ours**: soft constraint (persona injection) + hard constraint (Trie masking) + cycle-aware beam search |
| `4.融合_提示词多问题.py` | 融合脚本的多问题版本，用于一次生成多条候选路径 | A multi-question variant that generates several candidate paths in one pass |
| `4_fusion_generation_差异化画像对比试验.py` | 固定图谱与目标，只改学习者画像，检验生成结果的个性化差异 | Holds graph and goals fixed, varies only the learner profile, to test personalisation |

### 2.3 评估与对照 / Evaluation and comparisons

| 文件 / File | 中文说明 | English |
|---|---|---|
| `5_evaluate_legality.py` | 批量评估三组输出，计算 SL（结构合法率）、LR（无环率）、EPR（有效路径率）、AL（平均长度）等，汇总成论文表 | Batch-evaluates the three groups and computes SL / LR / EPR / AL, aggregated into the paper's table |
| `6_单门课适用实验.py` | 限定在"数据结构"一门课内做路径规划，含关键词黑名单以避免跨课程串味 | Path planning restricted to a single course (data structures), with a keyword blacklist to prevent cross-course drift |
| `7_单门课三组对比试验.py` | 课程内三组对比：Hard 为课程内随机游走，Fusion 为课程内规划游走 | In-course three-way comparison: Hard does random walk, Fusion does planned walk |
| `8_对比KGR (基于图的传统推荐).py` | 与图嵌入式学习路径推荐（KGR 一路）对比，说明其结构合法但语义不连贯 | Compares against graph-embedding path recommendation (the KGR line) |
| `9_对比"基于强化学习的路径推荐".py` | 与强化学习路径推荐对比，说明其稀疏奖励下易产生非法跳跃 | Compares against RL-based path recommendation, which suffers from sparse rewards |
| `10_对比"纯 Prompt Engineering (CoT Few-shot)".py` | 与纯提示/思维链对比，说明其依赖参数知识、易产生结构性幻觉 | Compares against pure prompting / CoT, which relies on parametric knowledge |
| `两个新基线.py` | 补充两个基线：A*/BFS+先修约束（纯图搜索）与 GRU/LSTM 序列推荐，并计算 SL/LR/EV/SC 四项指标 | Adds two baselines (A*/BFS with prerequisites, and GRU/LSTM) with SL / LR / EV / SC metrics |
| `束搜索宽度（Beam Size）进行消融实验.py` | 固定其他超参，扫描 `num_beams ∈ {1,3,5,8,10}`，为正文取 5 提供依据 | Scans `num_beams ∈ {1,3,5,8,10}` to justify the value 5 |
| `防环惩罚系数消融.py` | 扫描 `repetition_penalty ∈ {1.0,2.0,2.5,3.0}`，为正文取 2.5 提供依据 | Scans `repetition_penalty ∈ {1.0,2.0,2.5,3.0}` to justify 2.5 |

### 2.4 已提交的结果文件 / Committed result files

| 文件 / File | 说明 / Description |
|---|---|
| `generated_results_soft.txt` | 仅软约束的生成结果 / Generation output, soft constraint only |
| `generated_results_hard.txt` | 硬约束的生成结果 / Generation output, hard constraint |
| `generated_results_fusion.txt`、`generated_results_fusion_final.txt` | 融合方法的中间与最终结果 / Fusion output, intermediate and final |
| `generated_results_single_course.txt` | 单门课实验的生成结果 / Single-course generation output |
| `beam_size_ablation_results.csv` | 束宽消融结果 / Beam-width ablation results |
| `repetition_penalty_ablation_results.csv` | 防环惩罚消融结果 / Repetition-penalty ablation results |
| `baseline_astar_grurnn_results.csv` | A*/BFS 与 GRU/LSTM 两个基线的结果 / Results of the two new baselines |
| `kg_transition_cache.json` | 约束查找表，可由 `1_build_kg_cache.py` 重建 / Constraint lookup table, rebuildable |

---

## 3. `3_dual_state/` —— 阶段三：双态执行与动态演化 / Stage 3: dual-state execution and evolution

这一阶段回答"路径排出来之后，学生真的学不会/学烦了怎么办"。学习者由模拟器生成，因此**纯 CPU 即可复现**。

This stage answers "what happens when the student actually gets stuck or frustrated". Learners come from a simulator, so the whole stage runs on **CPU only**.

### 3.1 环境、模拟器与画像 / Environment, simulator, profile

| 文件 / File | 中文说明 | English |
|---|---|---|
| `1.构建目标导向的环境与图谱.py` | `GoalDrivenKG`：用 networkx 载入 `kg_transition_cache1.json` 构建有向图，提供后继查询与可达判断 | `GoalDrivenKG`: loads the adjacency JSON into a networkx `DiGraph` and serves successor/reachability queries |
| `2.构建高保真用户模拟器.py` | `GoalUserSimulator`：带疲劳累积与"剧本先修"限制的学习者模拟器，逐步响应学习动作 | `GoalUserSimulator`: a learner simulator with fatigue accumulation and scripted prerequisite rules |
| `3.构建智能体与动态画像.py` | `EnhancedUserProfile`：掌握度、焦虑、学习效率、时间估计、资源偏好等个性化量化指标 | `EnhancedUserProfile`: mastery, anxiety, efficiency, time estimation and resource preference |
| `4.极速生成路径-多交互主实验.py` | 多轮交互主实验，检验能力与焦虑如何影响路径推进 | Main multi-round interaction experiment |
| `5.双版本主实验.py` | V10 版：区分"能力不足失败"与"情绪焦虑失败"，前者降难度、后者换资源 | V10: separates cognitive failure from affective failure and responds differently |
| `6.批量多学生实验.py` | 100 名模拟学生的批量对比：Static / Cognitive-Only / Fusion | Batch comparison over 100 simulated students |

### 3.2 核心实验 / Core experiments

| 文件 / File | 中文说明 | English |
|---|---|---|
| `7_dual_state_extended_experiments.py` | 可复现的补充实验：主实验、消融、人群异质性、敏感性与统计检验，输出 6 个数据文件 + 1 张框架图。**仅需 numpy/networkx/scipy/matplotlib** | Reproducible supplementary experiments: main, ablation, cohort, sensitivity and significance tests. Outputs 6 data files + 1 figure. **Needs only numpy/networkx/scipy/matplotlib** |
| `8_dynamic_path_evolution.py` | **核心脚本**：双时间尺度状态演化 + 滚动重规划（DTE-RR），含 D1 主对比、D2 异质性、D3 触发频率、D4 观测滞后、D5 预算收紧、D6 状态突变。**仅需 networkx** | **Core script**: dual-timescale state evolution + rolling replanning (DTE-RR), covering D1 main comparison, D2 heterogeneity, D3 trigger frequency, D4 observation lag, D5 budget tightening, D6 state shock |
| `9_dynamic_multiseed.py` | 把 D1 协议在 10 个随机种子上重复，检验增益符号是否稳定（用 importlib 载入 8 号脚本，不复制代码） | Repeats the D1 protocol over 10 seeds to test sign stability (loads script 8 via importlib, no code duplication) |
| `11_path_source_sensitivity.py` | 初始路径来源敏感性：目标集 / 合法链 / 最短链三种来源下，动态增益是否仍成立 | Path-source sensitivity: does the dynamic gain hold for goal-set, legal-chain and shortest-chain inputs |
| `12_multiseed_robustness.py` | 针对边缘结果的多种子复核：Δ1 = roll − static，Δ2 = roll − evolve | Multi-seed recheck for the borderline result: Δ1 = roll − static, Δ2 = roll − evolve |
| `13_export_subject_tasks.py` | 在全图 410 个概念上挑出五个学科任务包（每个 6 个目标），逐条做 `nx.has_path` 可达校验 | Picks five subject bundles (6 goals each) from the 410-concept graph, validating every goal with `nx.has_path` |

### 3.3 平台数据导出 / Platform data export

| 文件 / File | 中文说明 | English |
|---|---|---|
| `10_export_platform_data.py` | 复用 8 号脚本的模型"原样"跑一遍，把每一步状态留下，导出成前端可读的 JSON；同时生成"数据结构"两跳邻域的演示子图 | Re-runs script 8 verbatim while recording every step, exporting front-end JSON plus a demo subgraph |
| `paper_revision/patch_cn_paper.py` | 辅助脚本：把状态演化与滚动重规划的内容改写进中文论文稿并标红（依赖本地排版工具 `_docx_kit`，未随仓库分发） | Helper: patches the Chinese manuscript with the new sections, changes highlighted (depends on the local `_docx_kit`, not distributed) |
| `paper_revision/patch_en_paper.py` | 同上，英文稿版本 | Same, for the English manuscript |

### 3.4 已提交的结果 / Committed results

| 目录 / Directory | 内容 / Contents |
|---|---|
| `dual_state_outputs/` | 7 号脚本输出：主实验、消融、人群、敏感性的逐种子 CSV，统计检验表，汇总 JSON，以及 3 张图 |
| `dynamic_outputs/` | 8 号脚本输出：`d1_main`（主对比）、`d2_heterogeneity`、`d3_frequency`、`d4_lag_prior`、`d5_budget`、`d6_shock` 及 `meta.json`（记录种子、图规模 410 节点/905 边与全部超参）；`m1_multiseed` 为 9 号脚本的十种子汇总 |
| `thesis_outputs/` | 9/11/12 号脚本输出：多种子稳健性汇总、路径来源敏感性表与配对检验 |

### 3.5 说明文档 / Stage notes

| 文件 / File | 中文说明 | English |
|---|---|---|
| `README_dynamic_experiments.md` | 动态演化实验的设计说明与参数含义 | Design notes and parameter meanings for the dynamic experiments |
| `README_补充实验_中期.md` | 中期答辩前补充实验的说明 | Notes on the supplementary experiments added before the midterm defence |

---

## 4. `platform/` —— 可视化演示平台 / Demo platform

纯静态前端 + Python 标准库服务，**离线可用**，答辩现场双击即可。

Pure static front end plus a stdlib-only Python server. Works **fully offline**, which matters for a live defence.

| 文件 / File | 中文说明 | English |
|---|---|---|
| `index.html` | 单页应用，六个页签：概览 / 学习者画像 / 静态⇄动态 / 知识图谱 / 实验证据 / 方法与论文 | Single-page app with six tabs: overview, learner profile, static⇄dynamic, knowledge graph, evidence, method |
| `server.py` | 本地 HTTP 服务（仅标准库），默认 `127.0.0.1:8770`，自动打开浏览器 | Local HTTP server (stdlib only) on `127.0.0.1:8770`, opens the browser automatically |
| `启动平台.bat` | Windows 一键启动（`chcp 65001` + `cd /d %~dp0`） | One-click launcher on Windows |
| `assets/app.css` | 学术型浅色主题 | Academic light theme |
| `assets/app.js` | 交互、图表渲染、回放控制 | Interaction, charts, replay control |
| `assets/engine.js` | 与 Python 对齐的 JavaScript 仿真引擎，用于双轨回放（**只演示机制，不报告结论**） | JavaScript port of the simulation engine for dual-track replay (**demonstration only, not for reporting results**) |
| `assets/echarts.min.js` | 本地 ECharts，避免联网 | Local ECharts, no network required |
| `data/graph.json` | 演示子图：410 个概念、905 条先修边 | Demo subgraph: 410 concepts, 905 prerequisite edges |
| `data/task.json` | 演示任务（起点 + 6 个目标）与 4 个学生原型 | Demo task and four student archetypes |
| `data/subjects.json` | 五个学科任务包（由 13 号脚本导出） | Five subject bundles (exported by script 13) |
| `data/trajectories.json` | 单次回放参考轨迹 | Reference replay trajectory |
| `data/aggregate.json` | D1/D2/D3/D5/D6 聚合结果，直接拷贝自 `dynamic_outputs/` | Aggregated results copied from `dynamic_outputs/` |
| `README.md` | 平台自身的详细说明（页签、数据来源、三轮修订记录、演示脚本） | Detailed platform notes: tabs, data provenance, revision history, demo script |

---

## 5. `scripts/` —— 辅助脚本 / Utilities

| 文件 / File | 中文说明 | English |
|---|---|---|
| `download_mt5.py` | 用 `huggingface_hub.snapshot_download` 把 `google/mt5-small` 完整下载到 `models/MT5_small` | Downloads `google/mt5-small` into `models/MT5_small` via `snapshot_download` |

---

## 6. 一图看清脚本依赖 / Dependency at a glance

```
scripts/download_mt5.py
        │
        ▼
models/MT5_small ──► 1_prototype/2.初步微调模型.py ──► models/zhuanjiamodel
                                                              │
data/MOOCCube ──► 2_generation/0.数据集转知识图谱.py ──► Neo4j ──► 1_build_kg_cache.py
                                                              │              │
                                                              │              ▼
                                                              │   kg_transition_cache.json
                                                              │              │
                                                              ▼              ▼
                                        2_soft / 3_hard / 4_fusion_generation.py
                                                              │
                                                              ▼
                                                  5_evaluate_legality.py

        （以上需要 GPU + Neo4j；以下只需 CPU）
                     ┌────────────────────────────────────────┐
                     │ 3_dual_state/7、8、9、11、12 号脚本      │
                     │ 输入：脚本内构造的模拟图与模拟学习者     │
                     │ 输出：*_outputs/ 下 CSV / JSON / PNG     │
                     └────────────────────────────────────────┘
                                       │
                                       ▼
                        10 / 13 号脚本 ──► platform/data/*.json
                                       │
                                       ▼
                              platform/server.py
```

---

## 7. 哪几个文件最值得先看 / Where to start reading

1. `2_generation/3_hard_constraint_decoding.py` —— 硬约束的实现只有几十行，是本文最核心的工程技巧（Trie + logits 掩码）。
2. `3_dual_state/8_dynamic_path_evolution.py` —— 滚动重规划的完整逻辑（状态更新、四项代价、稳定性正则、触发条件）。
3. `platform/assets/engine.js` —— 把上面两件事用 JavaScript 重写了一遍，读它能最快理解"路径怎么被改"。

---

*本文件随仓库结构变化同步更新。若你增删了脚本，请同时修改本表与 README 的目录树。*
*Keep this table and the README tree in sync when files are added or removed.*
