# -*- coding: utf-8 -*-
"""
补充实验 12：动态增益的多种子稳健性检验

问题
----
第 4 章与 8 号脚本报告过 "roll 相对 static 完成率 +2.08 个百分点，95% 区间
[-0.05, 4.31]"。该区间的下界紧贴 0，属于边缘结果。若换一个抽样种子，符号是否
稳定？这决定论文应当把"滚动重规划"写成"已证实的提升"还是"有条件的机制"。

做法
----
固定执行器与学习者生成规则不变，只改变抽样种子（任务集合与学习者初始画像随之
变化），对每个种子分别计算：
    Δ1 = roll − static
    Δ2 = roll − evolve
在同一随机流下逐个体配对，10,000 次自助给出 95% 区间。

判读
----
若 Δ1 在多数种子上为正、但区间普遍跨 0，则只能报告"方向一致、幅度不稳定"；
若出现负值，必须在论文中明确写出符号不稳定，不能以单一种子的 +2.08 作为结论。

运行
----
    set PYTHONHASHSEED=0 && python 12_multiseed_robustness.py
输出：thesis_outputs/multiseed_robustness.json
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
OUT = HERE / "thesis_outputs"
OUT.mkdir(exist_ok=True)

SEEDS = (20261108, 20261109, 20261110, 20261111, 20261112, 20261113)
N_TASKS = 18
N_LEARNERS = 20


def load_dte():
    spec = importlib.util.spec_from_file_location(
        "dte", HERE / "8_dynamic_path_evolution.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dte"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_seed(dte, kg, planner, seed: int) -> Dict:
    rng = random.Random(seed)
    problems = [kg.sample_problem(rng, 6) for _ in range(N_TASKS)]
    acc: Dict[str, List] = {k: [] for k in ("static", "evolve", "roll")}
    for path in problems:
        for proto in dte.PROTOTYPES:
            for _ in range(N_LEARNERS):
                base = dte.blend(rng, proto)
                for k in acc:
                    lr = dte.copy_learner(base)
                    ep = dte.run_episode(kg, planner, lr, list(path), k,
                                         random.Random(rng.randint(1, 10 ** 9)))
                    ep.peak_emotion = round(getattr(lr, "_peak", lr.emotion), 4)
                    acc[k].append(ep)

    def comp(k):
        return [100.0 if e.completed else 0.0 for e in acc[k]]

    out = {}
    for name, a, b in (("roll_minus_static", "roll", "static"),
                       ("roll_minus_evolve", "roll", "evolve")):
        diffs = [x - y for x, y in zip(comp(a), comp(b))]
        ci = dte.bootstrap_ci(diffs, random.Random(seed), 5000)
        out[name] = {
            "delta": round(dte.mean(diffs), 2),
            "ci95": [round(v, 2) for v in ci],
            "win_rate": round(100.0 * sum(1 for d in diffs if d > 0) / len(diffs), 2),
        }
    out["completion"] = {k: round(dte.mean(comp(k)), 2) for k in acc}
    out["mastery"] = {k: round(dte.mean([e.mastery for e in acc[k]]), 2) for k in acc}
    out["dropout"] = {
        k: round(dte.mean([100.0 if e.dropout else 0.0 for e in acc[k]]), 2)
        for k in acc
    }
    out["steps"] = {k: round(dte.mean([e.steps for e in acc[k]]), 2) for k in acc}
    return out


def main() -> None:
    dte = load_dte()
    kg = dte.KG()
    planner = dte.Replanner(kg)
    res = {}
    for seed in SEEDS:
        r = run_seed(dte, kg, planner, seed)
        res[str(seed)] = r
        print(f"seed {seed}: 完成 static {r['completion']['static']:.2f} "
              f"evolve {r['completion']['evolve']:.2f} roll {r['completion']['roll']:.2f} | "
              f"Δ(roll-static) {r['roll_minus_static']['delta']:+.2f} "
              f"{r['roll_minus_static']['ci95']} | "
              f"Δ(roll-evolve) {r['roll_minus_evolve']['delta']:+.2f} "
              f"{r['roll_minus_evolve']['ci95']}")

    ds = [res[str(s)]["roll_minus_static"]["delta"] for s in SEEDS]
    de = [res[str(s)]["roll_minus_evolve"]["delta"] for s in SEEDS]
    summary = {
        "n_seeds": len(SEEDS),
        "delta_static": {
            "mean": round(dte.mean(ds), 2), "min": min(ds), "max": max(ds),
            "n_positive": sum(1 for d in ds if d > 0),
        },
        "delta_evolve": {
            "mean": round(dte.mean(de), 2), "min": min(de), "max": max(de),
            "n_positive": sum(1 for d in de if d > 0),
        },
    }
    payload = {"seeds": list(SEEDS), "per_seed": res, "summary": summary,
               "config": {"n_tasks": N_TASKS, "n_learners_per_proto": N_LEARNERS}}
    (OUT / "multiseed_robustness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 汇总 ===")
    print(f"Δ(roll-static): 均值 {summary['delta_static']['mean']:+.2f} pp，"
          f"范围 {summary['delta_static']['min']:+.2f} ~ {summary['delta_static']['max']:+.2f}，"
          f"{summary['delta_static']['n_positive']}/{len(SEEDS)} 个种子为正")
    print(f"Δ(roll-evolve): 均值 {summary['delta_evolve']['mean']:+.2f} pp，"
          f"范围 {summary['delta_evolve']['min']:+.2f} ~ {summary['delta_evolve']['max']:+.2f}，"
          f"{summary['delta_evolve']['n_positive']}/{len(SEEDS)} 个种子为正")


if __name__ == "__main__":
    main()
