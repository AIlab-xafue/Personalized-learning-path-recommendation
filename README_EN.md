# Knowledge-Graph-Constrained Personalized Learning Path Recommendation

**知识图谱约束下的个性化学习路径推荐**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Data: MOOCCube](https://img.shields.io/badge/Data-MOOCCube%20(CC0)-green)](docs/DATA.md)

English | [简体中文](README.md)

---

This repository accompanies a master's thesis and two conference papers. It
decomposes "build a learning path that is both legal on the knowledge graph and
workable for a real student" into three linked stages — **generation,
execution, evolution** — and ships reproducible experiment scripts, committed
results, and an offline demo platform for each stage.

> **In one sentence**: first make the model generate paths strictly inside the
> legal boundary of the knowledge graph (no hallucination), then repair the path
> locally during execution according to the student's cognitive state and
> affective load (without rewriting the whole plan), and finally replan across
> rounds only when it is worth it.

---

## Contents

- [1. Problem](#1-problem)
- [2. Method](#2-method)
- [3. Repository layout](#3-repository-layout)
- [4. Quick start](#4-quick-start)
- [5. Data and models](#5-data-and-models)
- [6. How to read the numbers](#6-how-to-read-the-numbers)
- [7. File index](#7-file-index)
- [8. Citation](#8-citation)
- [9. License](#9-license)
- [10. Limitations](#10-limitations)

---

## 1. Problem

Learning-path recommendation in MOOCs has two long-separated traditions:

- **Graph methods** (shortest path, topological ordering, graph-embedding
  recommenders) guarantee a structurally legal path, but they never read the
  course text. The result is often structurally correct and pedagogically
  nonsensical.
- **LLM methods** (prompt engineering, fine-tuned generation) understand course
  semantics but suffer from **structural hallucination** — they emit
  prerequisite edges that do not exist in the knowledge graph.

Stage 1 of this work asks whether a generative model can be forced to walk only
on edges that actually exist, while keeping its semantic planning ability.

Stage 2 asks how a static path should be repaired when a student gets stuck,
gets frustrated, or drops out — and at what point the whole plan should be
replanned instead.

---

## 2. Method

### 2.1 Generation — soft and hard constraints working together

| Component | Role | File |
|---|---|---|
| Soft constraint | Inject retrieved prerequisite knowledge into the prompt to give direction | `2_soft_constraint_rag.py` |
| Hard constraint | Build a token-level prefix tree (Trie) and set the logits of all illegal successors to −∞ | `3_hard_constraint_decoding.py` |
| Cycle-aware beam search | Multi-beam decoding plus repetition penalty to fix short-sightedness and loops | `4_fusion_generation.py` |

The key engineering choice is to **turn the graph into a lookup table offline**:
`1_build_kg_cache.py` exports an adjacency table from Neo4j once, so inference
never touches the database and the constraint check becomes O(1).

### 2.2 Execution — dual-state profile and typed routing

Student state is split into two quantities — **cognitive readiness** and
**affective load** — updated separately, because "cannot understand" and "cannot
stand it" are different failures and require different responses:

- Load crosses a threshold → switch the resource modality (video / multimodal) to **recover**;
- Cognitive failure → insert a prerequisite remedy → **return to the blocked goal**;
- Otherwise → retry on the original path.

**Goal preservation** is mandatory here: after any support action the learner
must return to the original goal, and a successful remedy does **not** count as
mastery.

### 2.3 Evolution — rolling replanning

Across rounds, state drifts. The replanning objective adds a **stability
regulariser** on top of four cost terms (risk, difficulty mismatch, detour,
revisiting) to suppress the jitter of replanning every single round. Triggers are
deliberately sparse: at start, every few rounds, on consecutive failures, and
when load crosses a threshold.

---

## 3. Repository layout

```
moocube-lpr/
├── README.md                 Chinese (main)
├── README_EN.md              This file
├── LICENSE                   MIT (code) + CC0 data notice
├── requirements.txt
├── .gitignore
│
├── docs/
│   ├── FILE_INDEX.md         ★ Per-file description, Chinese + English
│   ├── DATA.md               Where to get the dataset and model weights
│   └── UPLOAD_GUIDE.md       ★ Step-by-step guide to publishing on GitHub
│
├── 1_prototype/              Stage 1: small-scale prototype
│   ├── 0.解析数据集转换成知识图谱.py   Parse dataset into a knowledge graph
│   ├── 1.先修关系提取数据集.py          Extract prerequisite pairs for fine-tuning
│   ├── 2.初步微调模型.py                Fine-tune mT5
│   ├── 3.初步使用模型.py                Run inference against Neo4j
│   ├── 4.训练成本模型.py                Train the cost (difficulty) model
│   ├── 5.RL 训练框架.py                 Minimal RLHF loop, no TRL dependency
│   └── database/             18 CSV files converted from MOOCCube (~14 MB)
│
├── 2_generation/             Stage 2: path generation, baselines, ablations
│   ├── 0.*.py                Graph construction (TSV import, dataset→KG, prereqs)
│   ├── 1_build_kg_cache.py   Export the constraint lookup table
│   ├── 2_soft_constraint_rag.py      Baseline: prompt only
│   ├── 3_hard_constraint_decoding.py Hard constraint: Trie masking
│   ├── 4_fusion_generation.py        Ours: fusion + cycle-aware beam search
│   ├── 5_evaluate_legality.py        Metrics: SL / LR / EPR / AL
│   ├── 6-10 + 两个新基线.py          Comparisons: KGR / RL / CoT / A* / GRU
│   ├── *消融实验.py                  Ablations for beam width and repetition penalty
│   └── kg_transition_cache.json      Constraint table (~9 MB, rebuildable)
│
├── 3_dual_state/             Stage 3: dual-state execution and dynamic evolution
│   ├── 1-6.*.py              Environment, simulator, profile, batch experiments
│   ├── 7_dual_state_extended_experiments.py  Ablation, cohort, statistics
│   ├── 8_dynamic_path_evolution.py           ★ Main DTE-RR experiment
│   ├── 9-12_*.py             Multi-seed robustness, path-source sensitivity
│   ├── 13_export_subject_tasks.py            Five subject task bundles
│   ├── 10_export_platform_data.py            Export JSON for the platform
│   └── *_outputs/            ★ Committed results (CSV / JSON / PNG)
│
├── platform/                 Offline demo platform (static + stdlib server)
│   ├── index.html            Single-page app, six tabs
│   ├── server.py             Local HTTP server, zero third-party deps
│   ├── assets/               app.js / engine.js / app.css / echarts.min.js
│   └── data/                 graph / task / subjects / trajectories / aggregate
│
├── scripts/
│   └── download_mt5.py       Fetch the google/mt5-small base model
│
└── data/                     External data goes here (contents not distributed)
    ├── README.md             Where the data comes from and where to put it
    └── MOOCCube/relations/
        └── prerequisite-dependency.json   Prerequisite table, 55 KB, bundled
                                           so Stage 3 needs no full dataset
```

See `docs/FILE_INDEX.md` for a per-file description with inputs, outputs, and
the corresponding thesis chapter.

---

## 4. Quick start

### 4.1 Zero-dependency demo

The platform uses only the Python standard library — no packages, no database,
no GPU:

```bash
git clone https://github.com/<your-username>/moocube-lpr.git
cd moocube-lpr/platform
python server.py            # opens http://127.0.0.1:8770
```

`platform/data/` already contains the graph, tasks, replay trajectories and
aggregate results, so a fresh clone runs out of the box.

> Opening `index.html` directly will show a blank page: it uses `fetch` to read
> `data/*.json`, and browsers block cross-origin requests from `file://`. Use the
> local server above.

### 4.2 Lightweight reproduction — Stage 3 (CPU only)

Stage 3 scripts depend only on `numpy`, `networkx` and `matplotlib`, and learners
are produced by a simulator. Their only external input is the prerequisite
relation table, a 55 KB file that **ships with this repository**
(`data/MOOCCube/relations/prerequisite-dependency.json`). So **no 3.9 GB dataset,
no Neo4j, no model weights** are needed:

```bash
pip install numpy networkx scipy matplotlib

cd 3_dual_state
python 7_dual_state_extended_experiments.py   # ablation, cohort, statistics
python 8_dynamic_path_evolution.py            # main DTE-RR experiment
python 9_dynamic_multiseed.py                 # robustness over 10 seeds
```

Outputs go to `3_dual_state/*_outputs/` and can be diffed against the committed
results directly.

### 4.3 Full reproduction — Stages 1 and 2 (Neo4j + GPU)

Prerequisites:

1. Install **Neo4j 5.x** and start it; note the Bolt URI and password.
2. Download MOOCCube into `data/MOOCCube/` per [docs/DATA.md](docs/DATA.md).
3. Export environment variables:

```bash
# Windows (PowerShell)
$env:NEO4J_PASSWORD = "your-password"
$env:MOOCCUBE_DIR   = "data/MOOCCube"

# Linux / macOS
export NEO4J_PASSWORD="your-password"
export MOOCCUBE_DIR="data/MOOCCube"
```

Download and fine-tune the base model:

```bash
python scripts/download_mt5.py                    # → models/MT5_small
python 1_prototype/2.初步微调模型.py               # → models/zhuanjiamodel
```

Build the graph and export the constraint cache (**run all scripts from the
repository root**):

```bash
python 2_generation/0.数据集转知识图谱.py          # MOOCCube → Neo4j
python 2_generation/1_build_kg_cache.py           # Neo4j → adjacency JSON
```

Run the three-way comparison and evaluate:

```bash
python 2_generation/2_soft_constraint_rag.py      # baseline: prompt only
python 2_generation/3_hard_constraint_decoding.py # hard constraint
python 2_generation/4_fusion_generation.py        # ours
python 2_generation/5_evaluate_legality.py        # aggregate into a table
```

---

## 5. Data and models

**This repository ships neither the dataset nor the model weights**, for one
reason: size. MOOCCube is about 3.9 GB extracted, and the four fine-tuned models
total about 9.6 GB. Both exceed GitHub's hard 100 MiB per-file limit and the
1 GB recommended repository size.

| Item | Size | How to obtain |
|---|---|---|
| MOOCCube raw data | ~3.9 GB | Download into `data/MOOCCube/`, see [docs/DATA.md](docs/DATA.md) |
| `mt5-small` base | ~1.1 GB | `python scripts/download_mt5.py` |
| Three fine-tuned models | ~8.5 GB | Train with `1_prototype/2.初步微调模型.py` |
| `kg_transition_cache*.json` | ~9 MB each | **Included**, also rebuildable from Neo4j |
| All experiment outputs | ~3 MB | **Included** |

MOOCCube is released by THU-KEG under CC0-1.0 and may be freely redistributed,
but its size makes it unsuitable for a Git repository, so only a download
pointer is provided here.

---

## 6. How to read the numbers

Two sets of numbers exist in this repository. **Do not mix them.**

| Source | Purpose | Reproduces paper conclusions? |
|---|---|---|
| `3_dual_state/dynamic_outputs/*.json` | Real Python output; the source of all table values | Yes |
| Dual-track replay in `platform/assets/engine.js` | JavaScript re-implementation, for **demonstrating the mechanism** | No — the RNG differs (LCG vs Python `random`), so a single replay will not match the paper step by step |

What the committed outputs actually support:

- Hard constraints drive the **hallucination rate to 0**: with Trie masking every
  emitted edge exists in the graph.
- Legal is not the same as loop-free: masking alone still leaves a gap in the
  acyclic rate, which the repetition penalty closes. That is why
  `4_fusion_generation.py` carries both mechanisms.
- The completion-rate gain from dynamic replanning is on the order of **1–3
  percentage points**, and the confidence interval **crosses zero** for some
  seeds. The thesis therefore claims a *more stable* gain for replanning over
  evolution-only, not blanket superiority over static planning.

Read the CSVs and JSONs under `3_dual_state/*_outputs/` for exact values; this
README deliberately does not restate them.

---

## 7. File index

Per-file descriptions in Chinese and English: **[docs/FILE_INDEX.md](docs/FILE_INDEX.md)**.

Step-by-step instructions for publishing this repository to your own GitHub
account: **[docs/UPLOAD_GUIDE.md](docs/UPLOAD_GUIDE.md)**.

---

## 8. Citation

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

Dataset:

> Yu, Jifan, et al. "MOOCCube: A Large-Scale Data Repository for NLP
> Applications in MOOCs." *Proceedings of the 58th Annual Meeting of the
> Association for Computational Linguistics*, 2020, pp. 2357–2366.

---

## 9. License

- **Code**: MIT, see [LICENSE](LICENSE)
- **CSV files under `data/`**: derived from MOOCCube (CC0-1.0), free to reuse

---

## 10. Limitations

Stated here so that the claims are not read more broadly than the evidence:

1. **Learners are simulated.** All Stage-3 numbers come from a rule-based learner
   simulator, not a real teaching intervention. They show the mechanism is
   self-consistent under stated assumptions; they are not classroom evidence.
2. **The graph is a subset.** Generation samples 747 concepts; the demo subgraph
   has 410 concepts and 905 prerequisite edges. Neither is validated on the full
   MOOCCube graph.
3. **The dynamic gain is modest.** Completion-rate improvements are on the order
   of 1–3 percentage points, with intervals crossing zero for some seeds.
4. **Subject boundaries are hand-drawn.** The five subject task bundles are
   manually categorised by concept semantics; the graph carries no course labels,
   so the boundaries are not closed.
5. **Weights must be retrained.** Fine-tuned weights are not included; Stage 2
   reproduction requires the steps in §4.3, and results will vary slightly with
   seed and hardware.
