# -*- coding: utf-8 -*-
"""实验 10：为可视化平台与学位论文图表导出数据（PLT-EXPORT）

用途
----
把第 8 号脚本（DTE-RR）的模型"原样"跑一遍，但把过程中每一步的状态留下来，
导出成前端可以直接读取的 JSON。它不产生新的科学结论，只做两件事：

  1. 生成一个规模可控、语义相对纯净的演示子图（MOOCCube 先修关系中
     "数据结构"的两跳邻域），供平台展示知识图谱与路径；
  2. 在同一名模拟学习者、同一学习任务上，逐步记录 static / evolve / roll
     三类策略的能力、情绪、路径与干预动作，供平台做"静态 → 动态"对照回放。

设计原则
--------
* 复用第 8 号脚本的 KG / Learner / Replanner / run_episode，不复制模型代码，
  保证平台里看到的机制与论文第 4 章、第 8 号脚本完全一致；
* 固定随机种子，输出可复现；
* 只读取第 8 号脚本已经产出的 dynamic_outputs/*.json 作为聚合指标来源，
  不在本脚本里重算总体结论，避免与论文表格口径不一致。

运行
----
    python 10_export_platform_data.py

输出
----
    ../platform/data/graph.json
    ../platform/data/task.json
    ../platform/data/trajectories.json
    ../platform/data/aggregate.json
"""

from __future__ import annotations

import os
import sys

# 与第 8、9 号脚本一致：固定字符串哈希顺序，否则子图节点排序会漂移
if os.environ.get("PYTHONHASHSEED") != "0":
    _env = dict(os.environ)
    _env["PYTHONHASHSEED"] = "0"
    if os.name == "nt":
        # Windows 没有真正的 exec：os.execve 会让父进程静默退出、输出丢失，
        # 因此改为启动子进程并等待其结束，再以相同退出码离开。
        # 注：不要用 os.spawnve，它在 Python 3.13 + Windows 上会 access violation。
        import subprocess
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=_env))
    os.execve(sys.executable, [sys.executable] + sys.argv, _env)

import importlib.util
import json
import random
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLATFORM = ROOT / "platform"
DATA = PLATFORM / "data"
SEED = 20261108


def load_dyn():
    """以模块方式载入第 8 号脚本。"""
    spec = importlib.util.spec_from_file_location(
        "dte_rr", HERE / "8_dynamic_path_evolution.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dte_rr"] = mod
    spec.loader.exec_module(mod)
    return mod


def dagify(sub):
    """按固定顺序保留边，跳过会形成回路的边，得到演示用的有向无环视图。

    原始先修关系由人工标注与算法预测合并而来，存在少量回边（如"计算效率 →
    数据结构"）。第 4 章的实验直接在原始有向图上执行，不做删边处理；这里仅
    为可视化把回边剔除，并在 meta 中记录剔除数量，避免"看起来像回路"的误读。
    """
    dag = nx.DiGraph()
    dag.add_nodes_from(sub.nodes)
    dropped = []
    for u, v in sorted(sub.edges):
        if u == v:
            continue
        if nx.has_path(dag, v, u):
            dropped.append((u, v))
            continue
        dag.add_edge(u, v)
    return dag, dropped


def restrict(mod, base, root: str, depth: int = 2):
    """截取 root 的 depth 跳后继邻域，并在子图上重算结构难度。"""
    keep = {root}
    frontier = [root]
    for _ in range(depth):
        nxt = []
        for u in frontier:
            for v in base.g.successors(u):
                if v not in keep:
                    keep.add(v)
                    nxt.append(v)
        frontier = nxt

    sub = base.g.subgraph(keep).copy()
    # 去掉孤立点，保持视图干净
    sub.remove_nodes_from([n for n in list(sub.nodes) if sub.degree(n) == 0])
    sub, dropped = dagify(sub)

    kg = object.__new__(mod.KG)
    kg.g = sub
    anc = {n: len(nx.ancestors(sub, n)) for n in sub.nodes}
    mx = max(anc.values()) or 1
    import math
    kg.diff = {
        n: round(0.25 + (math.log1p(c) / math.log1p(mx)) * 0.60, 4)
        for n, c in anc.items()
    }
    kg._succ = {n: list(sub.successors(n)) for n in sub.nodes}
    kg._pred = {n: list(sub.predecessors(n)) for n in sub.nodes}
    kg.dropped_edges = dropped
    return kg


CURATED_TARGETS = ["有根树", "阶乘", "自环", "邻边", "区域", "病态", "输入向量"]


def pick_targets(kg, start: str, k: int = 6):
    """优先使用人工挑选的语义清晰目标，缺失时按难度分层补足。"""
    reach = set(nx.descendants(kg.g, start))
    picks = [t for t in CURATED_TARGETS if t in reach][:k]
    rest = sorted((n for n in reach if n not in picks), key=lambda n: (kg.d(n), n))
    for n in rest:
        if len(picks) >= k:
            break
        picks.append(n)
    return picks


PERSONAS = [
    {
        "id": "p1",
        "name": "焦虑敏感型",
        "desc": "情绪基线高、失败敏感，最容易在长路径中途退出",
        "conscientiousness": 0.35,
        "neuroticism": 0.75,
        "openness": 0.50,
        "ability": 0.45,
        "emotion": 0.38,
        "budget": 50,
    },
    {
        "id": "p2",
        "name": "稳健均衡型",
        "desc": "能力与情绪均处中位，按部就班推进（默认演示对象）",
        "conscientiousness": 0.60,
        "neuroticism": 0.45,
        "openness": 0.50,
        "ability": 0.58,
        "emotion": 0.26,
        "budget": 50,
    },
    {
        "id": "p3",
        "name": "探索进阶型",
        "desc": "基础扎实、开放度高，希望快速抵达高阶目标",
        "conscientiousness": 0.80,
        "neuroticism": 0.25,
        "openness": 0.70,
        "ability": 0.70,
        "emotion": 0.18,
        "budget": 50,
    },
    {
        "id": "p4",
        "name": "时间紧迫型",
        "desc": "时间压力大、交互预算紧，最考验「先学哪个」的取舍",
        "conscientiousness": 0.50,
        "neuroticism": 0.65,
        "openness": 0.40,
        "ability": 0.50,
        "emotion": 0.42,
        "budget": 30,
    },
]


def run_one(mod, kg, planner, persona, strategy, task, seed):
    """跑一名学习者在一种策略下的一次完整学习过程，返回轨迹与汇总。"""
    lr = mod.Learner(
        conscientiousness=persona["conscientiousness"],
        neuroticism=persona["neuroticism"],
        openness=persona["openness"],
        ability=persona["ability"],
        emotion=persona["emotion"],
        budget=persona["budget"],
    )
    trace = []
    rng = random.Random(seed)
    planner._prev_head = None
    ep = mod.run_episode(kg, planner, lr, task, strategy, rng, trace=trace)
    return {
        "strategy": strategy,
        "summary": {
            "completed": bool(ep.completed),
            "completion": 100.0 if ep.completed else 0.0,
            "mastery": round((len(ep.__dict__.get("divergence", [])) * 0 + ep.mastery), 2),
            "steps": ep.steps,
            "peak_emotion": ep.peak_emotion,
            "dropout": bool(ep.dropout),
            "switches": ep.switches,
            "remedial": ep.remedial,
            "rest": ep.rest,
            "mismatch_steps": ep.mismatch_steps,
            "final_emotion": round(lr.emotion, 4),
            "final_ability": round(lr.ability, 4),
        },
        "trace": trace,
    }


def main() -> None:
    mod = load_dyn()
    kg = mod.KG()                      # 全部 410 个概念 / 905 条先修边，与第 4 章一致
    planner = mod.Replanner(kg)
    rng = random.Random(SEED)
    task = kg.sample_problem(rng, 6)   # 起点 + 6 个待掌握目标，与 D1 协议同源
    start, targets = task[0], task[1:]

    # 视图节点：任务节点及其一、二阶邻居，用于前端绘图（引擎仍在全图上运行）
    view = set(task)
    for t in task:
        view |= set(kg.pred(t)) | set(kg.succ(t))
    view_nodes = sorted(view)
    view_edges = [(u, v) for u, v in kg.g.edges if u in view and v in view]

    DATA.mkdir(parents=True, exist_ok=True)

    # ---------------- 图（全量，供引擎） ----------------
    nodes = [{
        "id": n,
        "difficulty": kg.d(n),
        "indegree": kg.g.in_degree(n),
        "outdegree": kg.g.out_degree(n),
        "isStart": n == start,
        "isTarget": n in targets,
        "inView": n in view,
    } for n in sorted(kg.g.nodes)]
    edges = [{"source": u, "target": v, "inView": (u in view and v in view)}
             for u, v in sorted(kg.g.edges)]
    graph = {
        "meta": {
            "source": "MOOCCube prerequisite-dependency.json",
            "scope": "全图（410 个概念）执行路径规划；绘图仅显示任务相关局部子图",
            "nodes": len(nodes),
            "edges": len(edges),
            "viewNodes": len(view_nodes),
            "viewEdges": len(view_edges),
        },
        "nodes": nodes,
        "edges": edges,
        "view": view_nodes,
    }

    # ---------------- 任务与画像 ----------------
    task_doc = {
        "start": start,
        "targets": targets,
        "path": task,
        "personas": PERSONAS,
        "rounds": 50,
        "view": view_nodes,
        "seed": SEED,
    }

    # ---------------- 轨迹 ----------------
    traj = {"meta": {"seed": SEED, "task": task}, "runs": {}}
    for p in PERSONAS:
        traj["runs"][p["id"]] = {}
        for si, strategy in enumerate(["static", "evolve", "roll", "roll_nostab"]):
            traj["runs"][p["id"]][strategy] = run_one(
                mod, kg, planner, p, strategy, task,
                seed=SEED + 1000 * (si + 1) + int(p["id"][1:]))

    # ---------------- 聚合 ----------------
    agg = {"source": "Title2/dynamic_outputs", "blocks": {}}
    for name in ["d1_main", "d2_heterogeneity", "d3_frequency", "d5_budget", "d6_shock"]:
        f = HERE / "dynamic_outputs" / f"{name}.json"
        if f.exists():
            agg["blocks"][name] = json.loads(f.read_text(encoding="utf-8"))
    agg["paper1"] = {
        "SL": 100.0, "LR": 100.0, "EV": 100.0, "EPR": 97.99,
        "note": "第一篇论文（河南师范大学学报拟录用）主实验结果",
    }

    for name, obj in [("graph", graph), ("task", task_doc),
                      ("trajectories", traj), ("aggregate", agg)]:
        (DATA / f"{name}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote data/{name}.json")

    print(f"\n全图：{len(nodes)} 个概念 / {len(edges)} 条先修边；绘图局部子图 {len(view_nodes)} 个节点")
    print("任务：" + " → ".join(task))
    for p in PERSONAS:
        row = []
        for s in ["static", "evolve", "roll"]:
            r = traj["runs"][p["id"]][s]["summary"]
            row.append(f"{s}:完成{int(r['completed'])} 步{r['steps']} "
                       f"峰{r['peak_emotion']:.2f} 变更{r['switches']}")
        print(f"  {p['name']}: " + "; ".join(row))


if __name__ == "__main__":
    main()
