# 文件说明（全量清单） / File Index (complete manifest)

本文件逐个说明仓库里**每一个文件**做什么、吃什么、吐什么。中文与英文并列，方便老师审阅与外部读者阅读。

**覆盖范围**：仓库共 **119 个文件**，本文档**逐个列出，无遗漏、无通配符**。可用 `python docs/check_file_index.py` 自行核对（脚本会比对 `git ls-files` 与本文档，报告是否有文件未被说明）。

This document describes **every single file** in the repository — what it does, what it reads, what it writes — in Chinese and English side by side.

**Coverage**: the repository holds **119 files**, all listed below **individually, with no wildcards**. Run `python docs/check_file_index.py` to verify that no tracked file is left undocumented.

> **运行约定 / Convention**：除特别注明外，脚本都假定**当前工作目录为所处分阶段目录**（如 `cd 3_dual_state`），而不是仓库根目录。脚本内的数据路径都可用环境变量覆盖，见 README 第 4.3 节。
> Unless noted otherwise, scripts assume the **current working directory is their own stage folder** (e.g. `cd 3_dual_state`). Data paths can be overridden by environment variables; see README §4.3.

---

## 0. 全仓库一览 / Repository at a glance

| 目录 / Directory | 文件数 / Files | 体积 / Size | 一句话 / In one line |
|---|---:|---:|---|
| 根目录 / root | 7 | 0.04 MB | 说明文档、许可、依赖清单、Git 配置 / Docs, licence, dependencies, Git config |
| `docs/` | 4 | 0.06 MB | 文件说明、数据获取、上传指南 / File index, data guide, upload guide |
| `data/` | 2 | 0.06 MB | 外部数据落位说明 + 一个 55 KB 先修表 / Data mount point plus one small prerequisite table |
| `1_prototype/` | 24 | 13.24 MB | 阶段一：建图、微调、跑通一次生成 / Stage 1: graph, fine-tuning, one generation pass |
| `2_generation/` | 28 | 10.14 MB | 阶段二：软/硬约束解码与五组对照 / Stage 2: constrained decoding and comparisons |
| `3_dual_state/` | 40 | 10.38 MB | 阶段三：双态执行、滚动重规划、结果文件 / Stage 3: dual-state execution, replanning, outputs |
| `platform/` | 13 | 1.50 MB | 离线演示平台（前端 + 标准库服务）/ Offline demo platform |
| `scripts/` | 1 | 0.00 MB | 模型权重下载 / Model weight download |
| **合计 / Total** | **119** | **35.43 MB** | |

---

## 1. 根目录 / Root files (7)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `README.md` | 中文主文档：研究问题、三阶段方法、目录结构、复现步骤、结果口径、已知限制 | Chinese main document: problem, method, layout, reproduction, how to read the numbers, limitations |
| `README_EN.md` | 上文的英文版，信息等价 | English counterpart, same content |
| `LICENSE` | 代码采用 MIT；另附 MOOCCube（CC0-1.0）与模型权重的许可说明 | MIT for code, plus licence notices for MOOCCube (CC0-1.0) and the model weights |
| `CITATION.cff` | 引用元数据。GitHub 首页会据此显示「Cite this repository」按钮；含题名、作者、单位与 MOOCCube 原始文献 | Citation metadata. Makes GitHub show a "Cite this repository" button; includes title, author, affiliation and the MOOCCube reference |
| `requirements.txt` | 全部 13 个第三方依赖，按「建图 / 生成 / 实验 / 绘图 / 服务」分组并注明哪些可省 | All 13 third-party dependencies, grouped by purpose, noting which are optional |
| `.gitignore` | 排除虚拟环境、IDE 配置、模型权重、大数据集；对 `data/MOOCCube/` 采用「整体忽略 + 白名单放行单个先修表」的写法 | Excludes virtualenvs, IDE files, model weights and the large dataset; uses ignore-all-plus-whitelist for `data/MOOCCube/` |
| `.gitattributes` | 统一换行为 LF、`.bat` 保持 CRLF、二进制不转换；并声明 `echarts.min.js` 为第三方库，避免仓库被判定成以 JavaScript 为主 | Normalises line endings (LF, CRLF for `.bat`), marks binaries, and flags `echarts.min.js` as vendored so the repo is not counted as JavaScript-dominant |

---

## 2. `docs/` —— 文档 / Documentation (4)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `FILE_INDEX.md` | 本文件：119 个文件逐个说明 | This file: every one of the 119 files |
| `DATA.md` | 数据集与模型权重的来源、许可、体积、放置路径、校验方式；说明为什么这两样不随仓库分发 | Source, licence, size, target path and verification for the dataset and weights; why they are not bundled |
| `UPLOAD_GUIDE.md` | 从零上传到 GitHub 的完整步骤：建仓、三种认证方式、推送、打 Release、常见报错排查、开源前自检清单 | End-to-end GitHub publishing walkthrough: repo creation, three auth methods, push, releases, troubleshooting, pre-release checklist |
| `check_file_index.py` | 一致性自检脚本：读取 `git ls-files`，检查每个文件是否在本文档中被提到，并报告未被说明的文件。**不依赖第三方库** | Consistency checker: reads `git ls-files`, verifies every file is mentioned in this document, and reports anything undocumented. **No third-party dependency** |

---

## 3. `data/` —— 外部数据落位 / Data mount point (2)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `README.md` | 说明 `data/` 是外部数据的放置位置，仓库本身不含 3.9 GB 原始数据；给出应当出现的子目录结构 | Explains that `data/` is where external data goes and that the 3.9 GB raw dataset is not bundled; shows the expected sub-directory layout |
| `MOOCCube/relations/prerequisite-dependency.json` | **唯一随仓库分发的数据文件**（55 KB、1027 行）。MOOCCube 官方概念先修关系三元组，阶段三全部实验依赖它；有了它，阶段三无需下载 3.9 GB 数据集即可复现 | **The only data file shipped with the repo** (55 KB, 1027 lines). The official MOOCCube concept-prerequisite triples that all Stage-3 experiments rely on; with it, Stage 3 reproduces without the 3.9 GB download |

---

## 4. `1_prototype/` —— 阶段一：小规模原型 / Stage 1: small-scale prototype (24)

这一阶段验证「能不能跑通」：把 MOOC 数据灌进图数据库、微调一个中文生成模型、跑通一次检索增强的路径生成。规模小、逻辑直白，是后续两阶段的工程基础。

This stage proves feasibility: load MOOC data into a graph database, fine-tune a Chinese generative model, and run retrieval-augmented path generation once. Small in scale and straightforward — the engineering foundation for the later stages.

### 4.1 脚本 / Scripts (6)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `0.解析数据集转换成知识图谱.py` | 读取 `database/` 下 18 个 CSV，按实体/关系类型批量写入 Neo4j（5000 条/事务）。**输入**：`database/*.csv`；**输出**：Neo4j 中的概念、课程、视频、用户及全部关系 | Reads the 18 CSVs under `database/` and batch-loads entities and relations into Neo4j (5000 rows per transaction). **In**: the CSVs; **Out**: concepts, courses, videos, users and relations in Neo4j |
| `1.先修关系提取数据集.py` | 从图谱中按「双重先修关系」抽取问答对，构造微调语料（默认 3000 条）。**输入**：Neo4j；**输出**：`training_data_final.jsonl`（体积约 3 MB，**不入库**，见第 9 节） | Extracts QA pairs via dual-prerequisite traversal to build a fine-tuning corpus (3000 by default). **In**: Neo4j; **Out**: `training_data_final.jsonl` (~3 MB, **not committed**, see §9) |
| `2.初步微调模型.py` | 用 `MT5ForConditionalGeneration` + `Trainer` 在本地基座模型上微调，产出策略模型。**输入**：`models/MT5_small` + 上一步 jsonl；**输出**：`models/zhuanjiamodel` | Fine-tunes `MT5ForConditionalGeneration` with `Trainer`. **In**: `models/MT5_small` and the jsonl above; **Out**: `models/zhuanjiamodel` |
| `3.初步使用模型.py` | 加载微调模型 + 实时查 Neo4j 检索先修知识，跑一次检索增强推理。**输入**：策略模型、Neo4j；**输出**：控制台打印的路径 | Loads the fine-tuned model and queries Neo4j at inference time. **In**: policy model, Neo4j; **Out**: paths printed to console |
| `4.训练成本模型.py` | 训练一个序列分类头来估计学习成本/难度（`MT5ForSequenceClassification`）。**输入**：样本 jsonl；**输出**：`models/chengbenmodel` | Trains a sequence-classification head as a cost/difficulty estimator. **In**: sample jsonl; **Out**: `models/chengbenmodel` |
| `5.RL 训练框架.py` | 手写的最小 RLHF 循环：策略模型 + 成本模型 + 安全模型，不依赖 TRL，规避版本冲突。**输入**：三个模型 + 提示数据；**输出**：`models/finalsafemodel` | A hand-written minimal RLHF loop (policy + cost + safety model) with no TRL dependency, avoiding version conflicts. **Out**: `models/finalsafemodel` |

**运行顺序 / Order**：`0` → `1` → `2` → `3`；`4`、`5` 为可选分支（成本模型与 RL 精调）。

### 4.2 数据表 / Data tables (18)

`database/` 下是由 MOOCCube 转出的 18 张 CSV，共约 13.2 MB、27.5 万行，可直接用于建图。`id | name` 为实体表，`start_id | end_id` 为关系表。

`database/` holds 18 CSVs converted from MOOCCube — about 13.2 MB and 275k rows, ready for graph loading. `id | name` are entity tables; `start_id | end_id` are relation tables.

| 文件 / File | 行数 / Rows | 中文说明 | English |
|---|---:|---|---|
| `database/concept.csv` | 700 | 概念实体表：概念 ID 与名称 | Concept entities: ID and name |
| `database/course.csv` | 706 | 课程实体表 | Course entities |
| `database/video.csv` | 1 405 | 视频（知识点讲解片段）实体表 | Video (lecture clip) entities |
| `database/paper.csv` | 5 927 | 论文实体表（MOOCCube 中的文献资源） | Paper entities (literature resources in MOOCCube) |
| `database/teacher.csv` | 1 733 | 教师实体表 | Teacher entities |
| `database/school.csv` | 194 | 学校实体表 | School entities |
| `database/user.csv` | 4 723 | 用户（学习者）实体表 | User (learner) entities |
| `database/rel_prerequisite_dependency.csv` | 216 | **概念→概念 先修关系**：本阶段的核心边，后续所有路径合法性都建立在它之上 | **Concept-to-concept prerequisites**: the core edge type; all path legality rests on it |
| `database/rel_course_concept.csv` | 10 346 | 课程→概念 包含关系 | Course-to-concept containment |
| `database/rel_course_video.csv` | 1 591 | 课程→视频 包含关系 | Course-to-video containment |
| `database/rel_video_concept.csv` | 4 040 | 视频→概念 讲解关系（视频在讲哪个概念） | Video-to-concept: which concept a clip teaches |
| `database/rel_concept_paper.csv` | 5 927 | 概念→论文 关联关系 | Concept-to-paper association |
| `database/rel_field_concept.csv` | 44 | 领域→概念 归属关系 | Field-to-concept membership |
| `database/rel_school_course.csv` | 703 | 学校→课程 开设关系 | School-to-course offering |
| `database/rel_school_teacher.csv` | 2 046 | 学校→教师 任职关系 | School-to-teacher employment |
| `database/rel_teacher_course.csv` | 2 349 | 教师→课程 授课关系 | Teacher-to-course teaching |
| `database/rel_user_course.csv` | 24 933 | 用户→课程 选课行为（用于统计课程热度与人群分布） | User-to-course enrolment (used for popularity and cohort statistics) |
| `database/rel_user_video.csv` | 225 362 | 用户→视频 观看行为（**仓库中最大的文件，9.76 MB**），是成本模型的样本来源 | User-to-video viewing (**largest file in the repo, 9.76 MB**), the sample source for the cost model |

---

## 5. `2_generation/` —— 阶段二：路径生成 / Stage 2: path generation (28)

这一阶段回答「怎么让模型只在图上真实存在的边里走」。核心是三组对照：仅提示（基线）、仅硬约束、软硬融合。

This stage answers "how to force the model to walk only on edges that really exist". The core is a three-way comparison: prompt-only (baseline), hard-constraint-only, and fusion.

### 5.1 建图与缓存 / Graph construction and caching (5)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `0.数据集转知识图谱.py` | 全量 MOOCCube → Neo4j：遍历 `entities/` 与 `relations/` 下的 JSON/TSV 批量入库。**输入**：`data/MOOCCube`；**输出**：Neo4j 全量图 | Loads the full MOOCCube into Neo4j by walking `entities/` and `relations/`. **In**: `data/MOOCCube`; **Out**: the full graph in Neo4j |
| `0.TSV文件导入关系.py` | 单独导入 `relations/prerequisite-dependency.json` 这一条先修关系链（文件名沿用历史叫法，实际读的是 JSON） | Imports only the `prerequisite-dependency.json` relation chain (the filename keeps its historical wording; it actually reads JSON) |
| `0.补充先修关系.py` | 把 `additional_information/prerequisite_prediction.json`（算法预测的先修关系）作为 `PREREQUISITE_PRED` 补入，提高约束覆盖率 | Adds the predicted prerequisites as `PREREQUISITE_PRED` to raise constraint coverage |
| `0_delete_relations.cypher` | 一段 Cypher 脚本（**不是 Python**，扩展名曾误用 `.py`），分批删除 `KNOWS` 关系，用于清库重来 | A Cypher snippet (**not Python**; it once carried a `.py` extension by mistake) that deletes `KNOWS` relations in batches, for a clean rebuild |
| `1_build_kg_cache.py` | **关键基础设施**：从 Neo4j 导出全量先修关系到本地邻接表，推理时不再查库。**输入**：Neo4j；**输出**：`kg_transition_cache.json`（约 9 MB） | **Key infrastructure**: exports all prerequisite edges into a local adjacency table so inference never hits the database. **Out**: `kg_transition_cache.json` (~9 MB) |

### 5.2 生成方法 / Generation methods (5)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `2_soft_constraint_rag.py` | **基线**：把检索到的先修知识写进提示，不强制解码。用于复现「结构性幻觉」，给硬约束提供对照依据 | **Baseline**: injects retrieved prerequisites into the prompt without constraining decoding. Reproduces structural hallucination and motivates the hard constraint |
| `3_hard_constraint_decoding.py` | **硬约束**：针对当前概念的合法后继动态构建 Token 级 Trie，通过 `prefix_allowed_tokens_fn` 把非法 Token 的 logits 置为 −∞ | **Hard constraint**: builds a token-level Trie over legal successors and masks illegal logits to −∞ via `prefix_allowed_tokens_fn` |
| `4_fusion_generation.py` | **本文方法**：软约束（个性化画像注入）+ 硬约束（Trie 掩码）+ 防环束搜索，三者协同 | **Ours**: soft constraint (persona injection) + hard constraint (Trie masking) + cycle-aware beam search |
| `4.融合_提示词多问题.py` | 融合脚本的多问题版本，一次生成多条候选路径 | A multi-question variant that generates several candidate paths in one pass |
| `4_fusion_generation_差异化画像对比试验.py` | 固定图谱与目标，只改学习者画像，检验生成结果的个性化差异 | Holds graph and goals fixed and varies only the learner profile, to test personalisation |

### 5.3 评估与对照 / Evaluation and comparisons (9)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `5_evaluate_legality.py` | 批量评估三组输出，计算 SL（结构合法率）、LR（无环率）、EPR（有效路径率）、AL（平均长度）等，汇总成论文表 | Batch-evaluates the three groups and computes SL / LR / EPR / AL, aggregated into the paper's table |
| `6_单门课适用实验.py` | 限定在「数据结构」一门课内做路径规划，含关键词黑名单以避免跨课程串味 | Path planning restricted to a single course (data structures), with a keyword blacklist to prevent cross-course drift |
| `7_单门课三组对比试验.py` | 课程内三组对比：Hard 为课程内随机游走，Fusion 为课程内规划游走 | In-course three-way comparison: Hard does a random walk, Fusion a planned walk |
| `8_对比KGR (基于图的传统推荐).py` | 与图嵌入式学习路径推荐（KGR 一路）对比，说明其结构合法但语义不连贯 | Compares against graph-embedding path recommendation (the KGR line): structurally valid but semantically disjoint |
| `9_对比“基于强化学习的路径推荐”.py` | 与强化学习路径推荐对比，说明其稀疏奖励下易产生非法跳跃 | Compares against RL-based path recommendation, which under sparse rewards tends to make illegal jumps |
| `10_对比“纯 Prompt Engineering (CoT  Few-shot)”.py` | 与纯提示 / 思维链对比，说明其依赖参数知识、易产生结构性幻觉（文件名中 Few-shot 前是两个空格，属历史命名，勿改） | Compares against pure prompting / CoT, which relies on parametric knowledge and hallucinates structure (two spaces before Few-shot in the filename — historical, do not rename) |
| `两个新基线.py` | 补充两个基线：A*/BFS + 先修约束（纯图搜索）与 GRU/LSTM 序列推荐，并计算 SL/LR/EV/SC 四项指标 | Adds two baselines — A*/BFS with prerequisites (pure graph search) and a GRU/LSTM sequence recommender — with SL / LR / EV / SC metrics |
| `束搜索宽度（Beam Size）进行消融实验.py` | 固定其他超参，扫描 `num_beams ∈ {1,3,5,8,10}`，为正文取 5 提供依据 | Scans `num_beams ∈ {1,3,5,8,10}` to justify the value 5 |
| `防环惩罚系数消融.py` | 扫描 `repetition_penalty ∈ {1.0,2.0,2.5,3.0}`，为正文取 2.5 提供依据 | Scans `repetition_penalty ∈ {1.0,2.0,2.5,3.0}` to justify 2.5 |

### 5.4 已提交的结果文件 / Committed result files (9)

| 文件 / File | 体积 / Size | 说明 / Description |
|---|---:|---|
| `kg_transition_cache.json` | 8.9 MB | 约束查找表（概念→合法后继），可由 `1_build_kg_cache.py` 从 Neo4j 重建 / Constraint lookup table, rebuildable from Neo4j |
| `generated_results_soft.txt` | 72 KB | 仅软约束的生成结果原文 / Raw generations, soft constraint only |
| `generated_results_hard.txt` | 34 KB | 仅硬约束的生成结果原文 / Raw generations, hard constraint only |
| `generated_results_fusion.txt` | 33 KB | 融合方法的中间结果 / Fusion output, intermediate |
| `generated_results_fusion_final.txt` | 33 KB | 融合方法的最终结果（论文引用的是这一份）/ Fusion output, final (the one cited in the paper) |
| `generated_results_single_course.txt` | 1 KB | 单门课实验的生成结果 / Single-course generation output |
| `beam_size_ablation_results.csv` | 0.5 KB | 束宽消融：五档 `num_beams` 下的 SL / LR / EPR / AL / 耗时 / Beam Coverage / 唯一路径数 | Beam-width ablation: SL / LR / EPR / AL / runtime / beam coverage / unique paths across five settings |
| `repetition_penalty_ablation_results.csv` | 0.3 KB | 防环惩罚消融：四档 `repetition_penalty` 下的四项指标 | Repetition-penalty ablation: four metrics across four settings |
| `baseline_astar_grurnn_results.csv` | 0.5 KB | A*/BFS 与 GRU/LSTM 两个新基线的结果，含 SL/LR/EV/SC | Results of the two new baselines with SL / LR / EV / SC |

> 表内 9 个文件，其中 `kg_transition_cache.json` 由 5.1 节的 `1_build_kg_cache.py` 生成，此处只记体积。

---

## 6. `3_dual_state/` —— 阶段三：双态执行与动态演化 / Stage 3: dual-state execution and evolution (40)

这一阶段回答「路径排出来之后，学生真的学不会 / 学烦了怎么办」。学习者由模拟器生成，因此**纯 CPU 即可复现**。

This stage answers "what happens when the student actually gets stuck or frustrated". Learners come from a simulator, so the whole stage runs on **CPU only**.

### 6.1 环境、模拟器与画像 / Environment, simulator, profile (6)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `1.构建目标导向的环境与图谱.py` | `GoalDrivenKG`：用 networkx 载入 `kg_transition_cache1.json` 构建有向图，提供后继查询与可达判断 | `GoalDrivenKG`: loads the adjacency JSON into a networkx `DiGraph` and serves successor and reachability queries |
| `2.构建高保真用户模拟器.py` | `GoalUserSimulator`：带疲劳累积与「剧本先修」限制的学习者模拟器，逐步响应学习动作 | `GoalUserSimulator`: a learner simulator with fatigue accumulation and scripted prerequisite rules |
| `3.构建智能体与动态画像.py` | `EnhancedUserProfile`：掌握度、焦虑、学习效率、时间估计、资源偏好等个性化量化指标 | `EnhancedUserProfile`: mastery, anxiety, efficiency, time estimation and resource preference |
| `4.极速生成路径-多交互主实验.py` | 多轮交互主实验，检验能力与焦虑如何影响路径推进 | Main multi-round interaction experiment: how ability and anxiety affect progress |
| `5.双版本主实验.py` | V10 版：区分「能力不足失败」与「情绪焦虑失败」，前者降难度、后者换资源 | V10: separates cognitive failure from affective failure and responds differently to each |
| `6.批量多学生实验.py` | 100 名模拟学生的批量对比：Static / Cognitive-Only / Fusion | Batch comparison over 100 simulated students: Static / Cognitive-Only / Fusion |

### 6.2 核心实验 / Core experiments (6)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `7_dual_state_extended_experiments.py` | 可复现的补充实验：主实验、消融、人群异质性、视频成功率敏感性、统计检验；输出 6 个数据文件 + 3 张图。**仅需 numpy/networkx/scipy/matplotlib** | Reproducible supplementary experiments: main, ablation, cohort, video-sensitivity and significance tests; outputs 6 data files and 3 figures. **Needs only numpy/networkx/scipy/matplotlib** |
| `8_dynamic_path_evolution.py` | **核心脚本**：双时间尺度状态演化 + 滚动重规划（DTE-RR），含 D1 主对比、D2 异质性、D3 触发频率、D4 观测滞后、D5 预算收紧、D6 状态突变。**仅需 networkx**，支持 `--quick` | **Core script**: dual-timescale state evolution plus rolling replanning (DTE-RR), covering D1 main comparison, D2 heterogeneity, D3 trigger frequency, D4 observation lag, D5 budget tightening, D6 state shock. **Needs only networkx**; supports `--quick` |
| `9_dynamic_multiseed.py` | 把 D1 协议在 10 个随机种子上重复，检验增益符号是否稳定（用 importlib 载入 8 号脚本，不复制代码） | Repeats the D1 protocol over 10 seeds to test sign stability (loads script 8 via importlib, no code duplication) |
| `11_path_source_sensitivity.py` | 初始路径来源敏感性：目标集 / 合法链 / 最短链三种来源下，动态增益是否仍成立 | Path-source sensitivity: does the dynamic gain hold for goal-set, legal-chain and shortest-chain inputs |
| `12_multiseed_robustness.py` | 针对边缘结果的多种子复核：Δ1 = roll − static，Δ2 = roll − evolve，并给配对检验 | Multi-seed recheck for the borderline result: Δ1 = roll − static, Δ2 = roll − evolve, with paired tests |
| `13_export_subject_tasks.py` | 在全图 410 个概念上挑出五个学科任务包（每个 6 个目标），逐条做 `nx.has_path` 可达校验 | Picks five subject bundles (6 goals each) from the 410-concept graph, validating every goal with `nx.has_path` |

### 6.3 平台数据导出 / Platform data export (1)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `10_export_platform_data.py` | 复用 8 号脚本的模型「原样」跑一遍，把每一步状态留下，导出成前端可读的 JSON；同时生成「数据结构」两跳邻域的演示子图。**输出**：`platform/data/*.json` 中的 graph / task / trajectories / aggregate | Re-runs script 8 verbatim while recording every step, exporting front-end JSON plus a two-hop demo subgraph. **Out**: graph / task / trajectories / aggregate in `platform/data/` |

### 6.4 论文修订辅助 / Manuscript patching helpers (2)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `paper_revision/patch_cn_paper.py` | 辅助脚本：把状态演化与滚动重规划的内容改写进中文论文稿并标红。依赖队列外的私有排版模块 `_docx_kit`，可用环境变量 `DOCX_KIT_DIR` 指向自己的副本；**不开源也能读**，属于过程留痕 | Helper: patches the Chinese manuscript with the new sections, changes highlighted. Depends on the out-of-tree `_docx_kit`; point `DOCX_KIT_DIR` at your own copy. Kept as a record of process — readable even without the module |
| `paper_revision/patch_en_paper.py` | 同上，英文稿版本，同样用 `DOCX_KIT_DIR` | Same for the English manuscript, also via `DOCX_KIT_DIR` |

### 6.5 已提交的结果 / Committed results (23)

#### 6.5.1 `kg_transition_cache1.json`（1）

| 文件 / File | 体积 / Size | 说明 / Description |
|---|---:|---|
| `kg_transition_cache1.json` | 8.4 MB | 阶段三用的先修邻接表。与阶段二的 `kg_transition_cache.json` 同源但规模不同（阶段三只用 410 个概念的子图），**阶段三全部脚本默认读这一份** / The adjacency table used by Stage 3; same origin as Stage 2's but restricted to the 410-concept subgraph. **All Stage-3 scripts read this one by default** |

#### 6.5.2 `dual_state_outputs/` —— 7 号脚本输出（9）

| 文件 / File | 体积 / Size | 中文说明 | English |
|---|---:|---|---|
| `main_experiment_per_seed.csv` | 2.3 KB | 主实验逐种子结果（30 行），列：实验名、种子、人群、策略、视频成功率、目标完成率、最终掌握度、峰值焦虑、平均步数、退出率 | Main experiment per seed (30 rows): experiment, seed, cohort, strategy, video success rate, goal completion, final mastery, peak anxiety, average steps, dropout rate |
| `ablation_per_seed.csv` | 3.2 KB | 消融逐种子结果（40 行），同列结构 | Ablation per seed (40 rows), same columns |
| `cohort_per_seed.csv` | 7.4 KB | 三类人群（高/中/低准备度）逐种子结果（90 行） | Three cohorts (high/mid/low readiness) per seed (90 rows) |
| `sensitivity_per_seed.csv` | 6.4 KB | 视频成功率敏感性扫描逐种子结果（80 行） | Video-success-rate sensitivity sweep per seed (80 rows) |
| `statistical_tests.csv` | 2.1 KB | 配对统计检验（15 行），列：实验、对比、指标、基线均值、本文均值、差值、配对 t、p 值、Cohen's dz | Paired significance tests (15 rows): comparison, metric, baseline mean, proposed mean, difference, paired t, p-value, Cohen's dz |
| `experiment_summary.json` | 17.5 KB | 全部结果的汇总结构，键：`path`（运行的脚本路径）、`settings`、`main`、`ablation`、`cohort`、`sensitivity`、`tests`。**论文表 4-x 的数字来自这里** | Aggregated structure with keys `path`, `settings`, `main`, `ablation`, `cohort`, `sensitivity`, `tests`. **The numbers in the paper's tables come from here** |
| `figure1_dual_state_framework.png` | 414 KB | 双态框架示意图：状态更新、类型化路由、目标保持三段 | Dual-state framework diagram: state update, typed routing, goal preservation |
| `figure2_main_outcomes.png` | 148 KB | 主实验结果对比图（三策略 × 四项指标） | Main-outcome comparison (three strategies × four metrics) |
| `figure3_video_sensitivity.png` | 142 KB | 视频成功率敏感性曲线 | Video-success-rate sensitivity curves |

#### 6.5.3 `dynamic_outputs/` —— 8、9 号脚本输出（10）

| 文件 / File | 体积 / Size | 中文说明 | English |
|---|---:|---|---|
| `d1_main.json` | 6.5 KB | **D1 主对比**。键：`n_paths`、`n_learners_per_proto`、`problems_sample`、`overall`（三策略总体指标 + 相对静态的增量 + 95% 区间）、`by_prototype`、`paired`。**论文第 5 章的主表就取这里** | **D1 main comparison.** Keys: `n_paths`, `n_learners_per_proto`, `problems_sample`, `overall` (per-strategy metrics, deltas vs static, 95% intervals), `by_prototype`, `paired`. **Source of the main table in Chapter 5** |
| `d1_main.csv` | 1.5 KB | 上一文件的宽表版，便于直接用 Excel / pandas 打开 | A flat-table rendering of the same results, convenient for Excel or pandas |
| `d2_heterogeneity.json` | 1.3 KB | **D2 异质性**：`grid` 为「认知准备度 × 情感负荷」九宫格上各策略的增益，用于说明增益集中在哪些人群 | **D2 heterogeneity**: `grid` gives per-strategy gain over a cognitive-readiness × affective-load grid, showing where the gain concentrates |
| `d3_frequency.json` | 0.7 KB | **D3 触发频率**：`frequency` 记录触发间隔取 1 / 4 / 8 / 12 轮时的完成率，用来支撑「每八轮复核」这一默认值 | **D3 trigger frequency**: completion rate at intervals of 1 / 4 / 8 / 12 rounds, justifying the default of eight |
| `d4_lag_prior.json` | 0.6 KB | **D4 观测滞后**：`lag`（状态延迟几轮才被观测到）与 `prior`（先验强度）两组的稳健性 | **D4 observation lag**: robustness under `lag` (delay before a state change is observed) and `prior` strength |
| `d5_budget.json` | 0.4 KB | **D5 预算收紧**：允许的改道次数受限时，增益如何衰减 | **D5 budget tightening**: how the gain decays when the number of allowed replans is capped |
| `d6_shock.json` | 0.5 KB | **D6 状态突变**：中途突变学生的状态后，重规划与静态的差距，是增益最大的一组 | **D6 state shock**: gap between replanning and static after a mid-course state shock — the largest gain observed |
| `m1_multiseed.json` | 7.2 KB | **9 号脚本输出**：`summary`（十种子均值/区间/符号一致性）与 `per_seed`（逐种子 Δ） | **Output of script 9**: `summary` (10-seed mean, interval, sign consistency) and `per_seed` (per-seed deltas) |
| `m1_multiseed.csv` | 2.6 KB | 上一文件的逐种子表 | The per-seed table of the above |
| `meta.json` | 0.3 KB | 运行元信息：随机种子、是否 `--quick`、耗时、图规模（410 节点 / 905 边）、全部超参。**复现时先看这个文件** | Run metadata: seed, `--quick` flag, runtime, graph size (410 nodes / 905 edges), all hyper-parameters. **Check this first when reproducing** |

#### 6.5.4 `thesis_outputs/` —— 11、12 号脚本输出（3）

| 文件 / File | 体积 / Size | 中文说明 | English |
|---|---:|---|---|
| `multiseed_robustness.json` | 4.9 KB | **12 号脚本输出**：`seeds`、`per_seed`、`summary`、`config`。给出 Δ1（重规划 − 静态）与 Δ2（重规划 − 仅演化）的均值、范围与区间 | **Output of script 12**: `seeds`, `per_seed`, `summary`, `config`. Gives mean, range and interval for Δ1 (roll − static) and Δ2 (roll − evolve) |
| `path_source_sensitivity.json` | 3.9 KB | **11 号脚本输出**：`meta`、`table`、`paired_static_vs_roll`、`length_sensitivity_S2`。三种路径来源下的成对比较 | **Output of script 11**: `meta`, `table`, `paired_static_vs_roll`, `length_sensitivity_S2`. Paired comparisons across the three path sources |
| `path_source_sensitivity.csv` | 0.5 KB | 上一文件的 6 行汇总表（来源 × 策略），列含完成率、掌握度、峰值情绪、步数、退出率、失配率、改道次数 | The 6-row summary table of the above (source × strategy): completion, mastery, peak emotion, steps, dropout, mismatch rate, replans |

### 6.6 阶段说明 / Stage notes (2)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `README_dynamic_experiments.md` | 动态演化实验的设计说明与参数含义（D1–D6 各测什么、为什么这样设） | Design notes and parameter meanings for the dynamic experiments (what D1–D6 each test and why) |
| `README_补充实验_中期.md` | 中期答辩前补充实验的说明与结果解读 | Notes and interpretation for the supplementary experiments added before the midterm defence |

---

## 7. `platform/` —— 可视化演示平台 / Demo platform (13)

纯静态前端 + Python 标准库服务，**离线可用**，答辩现场双击即可。

Pure static front end plus a stdlib-only Python server. Works **fully offline**, which matters for a live defence.

### 7.1 入口与服务 / Entry point and server (4)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `index.html` | 单页应用，六个页签：概览 / 学习者画像 / 静态⇄动态 / 知识图谱 / 实验证据 / 方法与论文 | Single-page app with six tabs: overview, learner profile, static⇄dynamic, knowledge graph, evidence, method |
| `server.py` | 本地 HTTP 服务（仅标准库），默认 `127.0.0.1:8770`，自动打开浏览器；`--port` 可改端口、`--no-browser` 不弹窗 | Local HTTP server (stdlib only) on `127.0.0.1:8770`, opens the browser automatically; `--port` and `--no-browser` supported |
| `启动平台.bat` | Windows 一键启动（`chcp 65001` 解决中文乱码 + `cd /d %~dp0` 定位到脚本所在目录） | One-click launcher on Windows (`chcp 65001` for encoding, `cd /d %~dp0` to anchor the working directory) |
| `README.md` | 平台自身的详细说明：页签职责、数据来源、三轮修订记录、演示时的讲解脚本 | Detailed platform notes: what each tab does, data provenance, revision history, and a demo script |

### 7.2 前端资源 / Front-end assets (4)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `assets/app.css` | 学术型浅色主题：字号、表格、卡片样式 | Academic light theme: typography, tables, cards |
| `assets/app.js` | 交互逻辑、图表渲染、双轨回放的播放控制 | Interaction, chart rendering, replay controls |
| `assets/engine.js` | 与 Python 对齐的 JavaScript 仿真引擎，用于双轨回放（**只演示机制，不报告结论**） | JavaScript port of the simulation engine for dual-track replay (**demonstration only, not for reporting results**) |
| `assets/echarts.min.js` | 本地 ECharts 5.4.2，避免联网（第三方库，`.gitattributes` 已标 `linguist-vendored`） | Local ECharts 5.4.2, no network required (third-party; flagged as `linguist-vendored`) |

### 7.3 数据 / Data (5)

| 文件 / File | 体积 / Size | 中文说明 | English |
|---|---:|---|---|
| `data/graph.json` | 92 KB | 演示子图：410 个概念、905 条先修边 | Demo subgraph: 410 concepts, 905 prerequisite edges |
| `data/task.json` | 6 KB | 演示任务（起点 + 6 个目标）与 4 个学生原型 | Demo task (start plus six goals) and four student archetypes |
| `data/subjects.json` | 3 KB | 五个学科任务包，由 13 号脚本导出 | Five subject bundles, exported by script 13 |
| `data/trajectories.json` | 29 KB | 单次回放的参考轨迹（逐步状态与决策） | Reference replay trajectory: per-step state and decisions |
| `data/aggregate.json` | 4 KB | D1/D2/D3/D5/D6 聚合结果，直接拷贝自 `dynamic_outputs/` | Aggregated D1/D2/D3/D5/D6 results, copied from `dynamic_outputs/` |

---

## 8. `scripts/` —— 辅助脚本 / Utilities (1)

| 文件 / File | 中文说明 | English |
|---|---|---|
| `download_mt5.py` | 用 `huggingface_hub.snapshot_download` 把 `google/mt5-small` 完整下载到 `models/MT5_small`（约 1.2 GB）。国内网络可先设 `HF_ENDPOINT=https://hf-mirror.com` | Downloads `google/mt5-small` into `models/MT5_small` (~1.2 GB) via `snapshot_download`. Behind the GFW, set `HF_ENDPOINT=https://hf-mirror.com` first |

---

## 9. 运行后才生成、**不在仓库里**的文件 / Generated at run time, **not** in the repo

这些文件由脚本产出或被 `.gitignore` 排除，克隆后看不到，属正常。本节列全，避免误判为「缺文件」。

These are produced by scripts or excluded by `.gitignore`; they are absent after cloning by design. Listed here so their absence is not mistaken for a missing file.

| 路径 / Path | 由谁生成 / Produced by | 为何不入库 / Why excluded |
|---|---|---|
| `training_data_final.jsonl` | `1_prototype/1.先修关系提取数据集.py` | 约 3 MB 的中间语料，内容可由 Neo4j 重新抽取 / ~3 MB intermediate corpus, re-extractable from Neo4j |
| `models/` 整个目录 | `scripts/download_mt5.py`、`1_prototype/2.初步微调模型.py` 等 | 权重共约 9.6 GB，远超 GitHub 限制 / ~9.6 GB of weights, far beyond GitHub limits |
| `data/MOOCCube/entities/`、`relations/` 下其余文件 | 用户按 `docs/DATA.md` 自行下载 | 原始数据集约 3.9 GB / raw dataset ~3.9 GB |
| `__pycache__/`、`*.pyc` | Python 解释器 | 编译缓存，无意义 / compiled cache, meaningless to ship |
| `.venv/`、`.idea/` | 本地环境与 IDE | 与机器绑定 / machine-specific |

---

## 10. 一图看清脚本依赖 / Dependency at a glance

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
                     │ 输入：kg_transition_cache1.json + 模拟器 │
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

## 11. 哪几个文件最值得先看 / Where to start reading

1. `2_generation/3_hard_constraint_decoding.py` —— 硬约束的实现只有几十行，是本文最核心的工程技巧（Trie + logits 掩码）。
2. `3_dual_state/8_dynamic_path_evolution.py` —— 滚动重规划的完整逻辑（状态更新、四项代价、稳定性正则、触发条件）。
3. `platform/assets/engine.js` —— 把上面两件事用 JavaScript 重写了一遍，读它能最快理解「路径怎么被改」。

---

*本文件由 `docs/check_file_index.py` 校验：它会比对 `git ls-files` 与本文档，报告任何未被说明的文件。增删文件后请同时更新本表与 README 的目录树。*
*Verified by `docs/check_file_index.py`, which diffs `git ls-files` against this document and reports anything undocumented. Keep this table and the README tree in sync when files change.*
