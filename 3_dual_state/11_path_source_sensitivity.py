# -*- coding: utf-8 -*-
"""
补充实验 11：初始路径来源对双态执行增益的影响（第 3 章 ↔ 第 4 章的接口检验）

为什么需要这组实验
------------------
第 3 章解决"生成什么路径"，第 4 章解决"执行期怎么改"。第 4 章的所有数值都建立在
一类初始路径上：由 sample_problem 抽出的"起点 + 若干目标"，目标之间不要求构成链。
审稿人自然会问：如果初始路径不是这种形式，而是结构上更连贯的链，第 4 章的动态增益
还成立吗？本实验只回答这一个问题。

三种初始路径来源（同一批学生、同一随机流、逐个体配对）
------------------------------------------------------
  S1 目标集   ：起点 + 6 个可达目标，目标间不要求相邻（第 4 章原口径）
  S2 合法链   ：从同一批起点出发，沿图谱真实边做无重复随机游走，长度 7 的连续链
  S3 最短链   ：从起点到某个远端目标的 BFS 最短路径，必要时用后继补齐到长度 7

两种执行策略
------------
  static ：入学时规划一次，执行期只做重试/补救/恢复（第 4 章原方法）
  roll   ：双时间尺度演化 + 滚动重规划（第 4 章扩展方法）

判读原则
--------
若动态增益在 S1/S2/S3 上方向一致且区间相近，说明结论对初始路径形态不敏感；
若只在 S1 上成立，则必须在论文中把适用范围限定为"目标集型任务"。
本脚本不修改任何既有实验的输出，结果写入 thesis_outputs/。

运行
----
    set PYTHONHASHSEED=0 && python 11_path_source_sensitivity.py
    python 11_path_source_sensitivity.py --quick
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import networkx as nx

HERE = Path(__file__).resolve().parent
OUT = HERE / "thesis_outputs"
OUT.mkdir(exist_ok=True)

SEED = 20261109
STRATEGIES = ("static", "roll")
SOURCES = ("S1_target_set", "S2_legal_chain", "S3_shortest_chain")
PATH_LEN = 7


def load_dte():
    spec = importlib.util.spec_from_file_location(
        "dte", HERE / "8_dynamic_path_evolution.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dte"] = mod
    spec.loader.exec_module(mod)
    return mod


def easy_starts(kg, n: int, rng: random.Random) -> List[str]:
    """与第 4 章 sample_problem 同一取法：出度大于 0 且结构难度低于 0.45。"""
    starts = [x for x in kg.g.nodes if kg.g.out_degree(x) > 0 and kg.d(x) < 0.45]
    rng.shuffle(starts)
    return starts[:n]


def legal_chain(kg, start: str, length: int, rng: random.Random) -> Optional[List[str]]:
    """沿真实边做无重复随机游走；走不通时返回 None，由调用方换起点。"""
    path = [start]
    seen = {start}
    while len(path) < length:
        cand = [s for s in kg.succ(path[-1]) if s not in seen]
        if not cand:
            return None
        nxt = rng.choice(cand)
        path.append(nxt)
        seen.add(nxt)
    return path


def shortest_chain(kg, start: str, length: int, rng: random.Random) -> Optional[List[str]]:
    """
    从起点到某个远端目标的 BFS 最短路径。若最短路径短于目标长度，
    用随机后继补齐，保证三种来源的路径长度一致，避免长度混入比较。
    """
    reach = [n for n in nx.descendants(kg.g, start) if n not in (start,)]
    if not reach:
        return None
    far = max(rng.sample(reach, min(20, len(reach))), key=lambda n: kg.g.in_degree(n))
    try:
        core = nx.shortest_path(kg.g, start, far)
    except nx.NetworkXNoPath:
        return None
    if len(core) >= length:
        return core[:length]
    path, seen = list(core), set(core)
    while len(path) < length:
        cand = [s for s in kg.succ(path[-1]) if s not in seen]
        if not cand:
            return None
        path.append(rng.choice(cand))
        seen.add(path[-1])
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    dte = load_dte()
    kg = dte.KG()
    planner = dte.Replanner(kg)
    print(f"[kg] 节点 {kg.g.number_of_nodes()}，边 {kg.g.number_of_edges()}")

    rng = random.Random(SEED)
    n_tasks = 8 if args.quick else 18
    n_learners = 10 if args.quick else 20

    starts = easy_starts(kg, n_tasks * 4, rng)
    tasks: Dict[str, List[List[str]]] = {s: [] for s in SOURCES}

    for st in starts:
        if len(tasks["S1_target_set"]) < n_tasks:
            try:
                prob = kg.sample_problem(rng, 6)
                tasks["S1_target_set"].append(prob)
            except RuntimeError:
                pass
        if len(tasks["S2_legal_chain"]) < n_tasks:
            ch = legal_chain(kg, st, PATH_LEN, rng)
            if ch:
                tasks["S2_legal_chain"].append(ch)
        if len(tasks["S3_shortest_chain"]) < n_tasks:
            ch = shortest_chain(kg, st, PATH_LEN, rng)
            if ch:
                tasks["S3_shortest_chain"].append(ch)
        if all(len(tasks[s]) >= n_tasks for s in SOURCES):
            break

    for s in SOURCES:
        print(f"[task] {s}: {len(tasks[s])} 条")

    # 合法性自检：S2/S3 的相邻边必须全部命中；S1 不要求相邻
    def edge_hit(seq: Sequence[str]) -> float:
        e = list(zip(seq[:-1], seq[1:]))
        if not e:
            return 0.0
        return 100.0 * sum(1 for a, b in e if kg.g.has_edge(a, b)) / len(e)

    hit = {s: round(dte.mean([edge_hit(p) for p in tasks[s]]), 2) for s in SOURCES}
    print(f"[check] 相邻边命中率 {hit}")

    rows: Dict[str, Dict[str, List]] = {s: {k: [] for k in STRATEGIES} for s in SOURCES}
    for s in SOURCES:
        for path in tasks[s]:
            for proto in dte.PROTOTYPES:
                for _ in range(n_learners):
                    base = dte.blend(rng, proto)
                    for k in STRATEGIES:
                        lr = dte.copy_learner(base)
                        ep = dte.run_episode(kg, planner, lr, list(path), k,
                                             random.Random(rng.randint(1, 10 ** 9)))
                        ep.peak_emotion = round(getattr(lr, "_peak", lr.emotion), 4)
                        rows[s][k].append(ep)

    def agg(eps: List) -> Dict:
        if not eps:
            return {}
        m = dte.mean
        return {
            "n": len(eps),
            "completion": round(m([100.0 if e.completed else 0.0 for e in eps]), 2),
            "mastery": round(m([e.mastery for e in eps]), 2),
            "peak_emotion": round(m([e.peak_emotion for e in eps]), 4),
            "steps": round(m([e.steps for e in eps]), 2),
            "dropout": round(m([100.0 if e.dropout else 0.0 for e in eps]), 2),
            "mismatch_rate": round(m([
                100.0 * e.mismatch_steps / max(1, e.steps) for e in eps]), 2),
            "replans": round(m([e.switches for e in eps]), 2),
            "divergence": round(m([m(e.divergence) if e.divergence else 0.0 for e in eps]), 4),
        }

    table, paired = {}, {}
    for s in SOURCES:
        table[s] = {k: agg(rows[s][k]) for k in STRATEGIES}
        diffs = [(100.0 if a.completed else 0.0) - (100.0 if b.completed else 0.0)
                 for a, b in zip(rows[s]["roll"], rows[s]["static"])]
        paired[s] = {
            "delta_completion": round(dte.mean(diffs), 2),
            "ci95": [round(v, 2) for v in dte.bootstrap_ci(diffs, random.Random(SEED), 5000)],
            "win_rate": round(100.0 * sum(1 for d in diffs if d > 0) / max(1, len(diffs)), 2),
            "n_pairs": len(diffs),
        }

    # 长度敏感性：仅对结构连贯来源 S2 做，检验长路径下动态增益是否变大
    length_table = {}
    for L in (5, 7, 9):
        seqs = []
        for st in starts:
            if len(seqs) >= n_tasks:
                break
            ch = legal_chain(kg, st, L, rng)
            if ch:
                seqs.append(ch)
        if not seqs:
            continue
        acc = {k: [] for k in STRATEGIES}
        for path in seqs:
            for proto in dte.PROTOTYPES:
                for _ in range(n_learners):
                    base = dte.blend(rng, proto)
                    for k in STRATEGIES:
                        lr = dte.copy_learner(base)
                        ep = dte.run_episode(kg, planner, lr, list(path), k,
                                             random.Random(rng.randint(1, 10 ** 9)))
                        ep.peak_emotion = round(getattr(lr, "_peak", lr.emotion), 4)
                        acc[k].append(ep)
        length_table[str(L)] = {k: agg(acc[k]) for k in STRATEGIES}

    result = {
        "meta": {
            "seed": SEED, "quick": args.quick, "path_len": PATH_LEN,
            "n_tasks": {s: len(tasks[s]) for s in SOURCES},
            "n_learners_per_proto": n_learners,
            "edge_hit_percent": hit,
            "note": "S1 不要求相邻，S2/S3 沿真实边；三组任务集合不同，仅组内配对。",
        },
        "table": table,
        "paired_static_vs_roll": paired,
        "length_sensitivity_S2": length_table,
    }
    (OUT / "path_source_sensitivity.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "path_source_sensitivity.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "strategy", "completion", "mastery", "peak_emotion",
                    "steps", "dropout", "mismatch_rate", "replans"])
        for s in SOURCES:
            for k in STRATEGIES:
                r = table[s][k]
                w.writerow([s, k, r["completion"], r["mastery"], r["peak_emotion"],
                            r["steps"], r["dropout"], r["mismatch_rate"], r["replans"]])

    print("\n=== 完成率 ===")
    for s in SOURCES:
        st, ro = table[s]["static"], table[s]["roll"]
        p = paired[s]
        print(f"{s:<18} 静态 {st['completion']:5.2f}%  动态 {ro['completion']:5.2f}%  "
              f"差值 {p['delta_completion']:+.2f} pp  CI {p['ci95']}  胜率 {p['win_rate']}%")
    print("\n=== 长度敏感性（S2） ===")
    for L, d in length_table.items():
        print(f"L={L}: 静态 {d['static']['completion']:.2f}%  动态 {d['roll']['completion']:.2f}%")
    print(f"\n已写出 {OUT / 'path_source_sensitivity.json'}")


if __name__ == "__main__":
    main()
