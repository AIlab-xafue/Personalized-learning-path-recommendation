# -*- coding: utf-8 -*-
"""导出实验 13：多学科学习任务包（SUBJ-EXPORT）

背景
----
可视化平台原来只挂了一个学习任务（起点「信息交换」+ 6 个计算机网络目标），
答辩时容易被理解成"只对一门课有效"。本脚本在全图 410 个概念的 MOOCCube
先修图上，另外挑选 4 组学科语义自洽的任务包，与原有任务一共 5 组，
供平台按学科切换、并排比较"同一名学习者在不同学科上走出的不同路径"。

设计原则
--------
* **不新造概念、不改图**：所有起点与目标都取自全图已有的 410 个概念，
  边也只使用原始先修边，平台执行的仍是同一个 Replanner；
* **可达性必须真实**：每条目标的每一跳都要求"起点 → 目标"存在有向路径，
  否则平台会排出跨学科的非法路径。脚本对每个目标做 nx.has_path 校验，
  不可达的组合直接报错退出，不写进 JSON；
* **局部子图只用于绘图**：view 是"起点 + 目标 + 最短路径中间节点 + 一跳邻居"，
  平台的计算始终在全图上进行，与第 4 章口径一致。

运行
----
    python 13_export_subject_tasks.py

输出
----
    ../platform/data/subjects.json
"""

from __future__ import annotations

import os
import sys

if os.environ.get("PYTHONHASHSEED") != "0":
    _env = dict(os.environ)
    _env["PYTHONHASHSEED"] = "0"
    os.execve(sys.executable, [sys.executable] + sys.argv, _env)

import importlib.util
import json
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "platform" / "data"


def load_dyn():
    spec = importlib.util.spec_from_file_location(
        "dte_rr", HERE / "8_dynamic_path_evolution.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dte_rr"] = mod
    spec.loader.exec_module(mod)
    return mod


# 五个任务包：起点与目标均可在全图中找到，且逐条校验有向可达
PACKS = [
    {
        "id": "net",
        "name": "计算机网络",
        "short": "计算机网络",
        "desc": "数据通信与交换：差错控制、路由选择与资源共享",
        "start": "信息交换",
        "targets": ["差错检验", "动态分配", "连接点", "缓冲",
                    "路由信息协议", "资源共享"],
    },
    {
        "id": "ds",
        "name": "数据结构与算法",
        "short": "数据结构",
        "desc": "从程序设计基础走向数据结构与算法：邻接矩阵、图遍历与查找",
        "start": "程序设计",
        "targets": ["数据结构", "算法", "邻接矩阵", "深度优先搜索",
                    "平均查找长度", "中序遍历"],
    },
    {
        "id": "math",
        "name": "数学与概率统计",
        "short": "数学",
        "desc": "高等数学与概率统计：多项式、概率分布、回归与级数",
        "start": "数学",
        "targets": ["多项式", "概率分布", "线性回归", "矩阵表示",
                    "微分方程", "级数求和"],
    },
    {
        "id": "os",
        "name": "操作系统与计算机系统",
        "short": "操作系统",
        "desc": "存储层次与进程：存取时间、缓存、缓冲与进程间通信",
        "start": "操作系统",
        "targets": ["存取时间", "数据组织", "缓存", "缓冲",
                    "进程间通信", "累加器"],
    },
    {
        "id": "logic",
        "name": "数理逻辑与离散数学",
        "short": "数理逻辑",
        "desc": "命题与谓词、逻辑表达式与布尔代数",
        "start": "数理逻辑",
        "targets": ["蕴涵", "逻辑表达式", "逻辑符号", "量化",
                    "布尔代数", "等价类"],
    },
]


def build_view(kg, start: str, targets: list[str], cap: int = 34) -> list[str]:
    """绘图用局部子图：起点、目标、最短路径中间节点，再补一跳邻居。"""
    core = {start, *targets}
    for t in targets:
        try:
            path = nx.shortest_path(kg.g, start, t)
            core.update(path[:-1])
        except nx.NetworkXNoPath:
            pass
    view = set(core)
    for n in list(core):
        view |= set(kg.pred(n)) | set(kg.succ(n))
    # 核心节点必须在，其余按度数从高到低补到 cap 个，保证图不空
    extra = sorted(view - core, key=lambda x: -(kg.g.in_degree(x) + kg.g.out_degree(x)))
    keep = list(core) + extra[: max(0, cap - len(core))]
    return sorted(keep)


def main() -> None:
    mod = load_dyn()
    kg = mod.KG()
    nodes = set(kg.g.nodes)
    out, errors = [], []
    for p in PACKS:
        if p["start"] not in nodes:
            errors.append(f"{p['id']}: 起点「{p['start']}」不在图中")
            continue
        hops, bad = {}, []
        for t in p["targets"]:
            if t not in nodes:
                bad.append(t)
                continue
            if not nx.has_path(kg.g, p["start"], t):
                bad.append(t)
                continue
            hops[t] = len(nx.shortest_path(kg.g, p["start"], t)) - 1
        if bad:
            errors.append(f"{p['id']}: 不可达目标 {bad}")
            continue

        hs = list(hops.values())
        # 只记录可达性统计；具体路径由平台前端按当前画像规划，避免两套实现混用
        lr = mod.Learner(0.6, 0.45, 0.5, 0.58, 0.26, 50, 0.30)
        plan = mod.Replanner(kg).plan(lr, p["start"], list(p["targets"]),
                                      0.35, 4, set(), {p["start"]})
        demo = {
            "maxHop": max(hs), "avgHop": round(sum(hs) / len(hs), 2),
            "steps": len([p["start"], *plan]),
            "dAvg": round(sum(kg.d(n) for n in p["targets"]) / len(p["targets"]), 3),
        }

        out.append({
            "id": p["id"], "name": p["name"], "short": p["short"], "desc": p["desc"],
            "start": p["start"], "targets": p["targets"],
            "hops": hops,
            "view": build_view(kg, p["start"], p["targets"]),
            "demo": demo,
        })
        print(f"[{p['id']}] {p['start']} → {len(p['targets'])} 目标，"
              f"最远 {demo['maxHop']} 跳 / 平均 {demo['avgHop']} 跳 / "
              f"目标均难 {demo['dAvg']:.2f}")

    if errors:
        print("\n以下任务包不合法，未写入：")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    doc = {
        "meta": {
            "source": "MOOCCube prerequisite-dependency.json（全图 410 概念 / 905 边）",
            "note": "各任务包的起点与目标均为图中原有概念，且逐条校验有向可达；"
                    "view 仅用于绘图，规划在全图上执行。",
            "count": len(out),
        },
        "subjects": out,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    f = DATA / "subjects.json"
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {f.relative_to(ROOT)}，共 {len(out)} 个任务包")


if __name__ == "__main__":
    main()
