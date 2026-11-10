# -*- coding: utf-8 -*-
"""实验 9：动态重规划的多随机种子稳健性检验（DTE-RR-MS）

用途
----
第 8 号脚本的 D1 只在单一随机种子（20261108）下比较四种策略，配对差值容易受
"抽到哪 18 个任务、哪 120 名学习者"影响。本脚本把同一套 D1 协议在 10 个种子上
重复，回答两个问题：

  M1  完成率差值在种子间是否稳定（符号一致性与极差）；
  M2  把 10 个种子合并后，roll 相对 static / evolve / roll_nostab 的平均差值与区间。

设计
----
* 复用 8 号脚本的实现（importlib 载入，不复制代码），只改写模块级 SEED；
* 每个种子沿用 D1 的任务抽样与画像构造流程，学习器数量与路径数不变；
* 区间用两层自助：种子为重采样单位（外层），种子内配对差值为内层，
  避免把 21,600 个回合当成独立样本而低估不确定性。

运行
----
    python 9_dynamic_multiseed.py              # 10 个种子，约 1-2 分钟
    python 9_dynamic_multiseed.py --seeds 3    # 自检

输出
----
    Title2/dynamic_outputs/m1_multiseed.json
    Title2/dynamic_outputs/m1_multiseed.csv
"""

from __future__ import annotations

import os
import sys

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

import argparse
import csv
import importlib.util
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dynamic_outputs"
BASE_SEED = 20261108


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "dte", HERE / "8_dynamic_path_evolution.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dte"] = mod          # dataclass 需要模块已注册
    spec.loader.exec_module(mod)
    return mod


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def bootstrap_seed_level(per_seed, rng, n=10000):
    """以种子为重采样单位，返回配对差值的 95% 区间。"""
    if not per_seed:
        return [0.0, 0.0]
    k = len(per_seed)
    means = []
    for _ in range(n):
        means.append(mean([per_seed[rng.randrange(k)] for _ in range(k)]))
    means.sort()
    return [round(means[int(0.025 * n)], 2), round(means[int(0.975 * n) - 1], 2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    args = ap.parse_args()

    mod = load_engine()
    kg = mod.KG()
    planner = mod.Replanner(kg)

    rows = []
    seeds = [BASE_SEED + i for i in range(args.seeds)]
    for i, s in enumerate(seeds, 1):
        mod.SEED = s
        res = mod.experiment_main(kg, planner, quick=False)
        rec = {"seed": s}
        for st in ("static", "evolve", "roll", "roll_nostab"):
            rec[f"{st}_completion"] = res["overall"][st]["completion"]
            rec[f"{st}_mastery"] = res["overall"][st]["mastery"]
            rec[f"{st}_steps"] = res["overall"][st]["steps"]
            rec[f"{st}_dropout"] = res["overall"][st]["dropout"]
        for base in ("static", "evolve", "roll_nostab"):
            rec[f"d_roll_{base}"] = res["paired"][f"roll_vs_{base}"]["delta_completion"]
        rows.append(rec)
        print(f"  seed {s} ({i}/{len(seeds)}): "
              f"static {rec['static_completion']:.2f} | roll {rec['roll_completion']:.2f} | "
              f"Δ vs static {rec['d_roll_static']:+.2f} | Δ vs evolve {rec['d_roll_evolve']:+.2f}")

    rng = random.Random(BASE_SEED)
    summary = {}
    for base in ("static", "evolve", "roll_nostab"):
        ds = [r[f"d_roll_{base}"] for r in rows]
        summary[f"roll_vs_{base}"] = {
            "mean_delta": round(mean(ds), 2),
            "median_delta": round(sorted(ds)[len(ds) // 2], 2),
            "min": round(min(ds), 2),
            "max": round(max(ds), 2),
            "positive_seeds": sum(1 for d in ds if d > 0),
            "seeds": len(ds),
            "ci95_seed_level": bootstrap_seed_level(ds, rng),
        }

    for st in ("static", "evolve", "roll", "roll_nostab"):
        vals = [r[f"{st}_completion"] for r in rows]
        summary.setdefault("completion", {})[st] = {
            "mean": round(mean(vals), 2),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "sd": round((sum((v - mean(vals)) ** 2 for v in vals) / len(vals)) ** 0.5, 2),
        }
        dv = [r[f"{st}_dropout"] for r in rows]
        summary.setdefault("dropout", {})[st] = round(mean(dv), 2)
        sv = [r[f"{st}_steps"] for r in rows]
        summary.setdefault("steps", {})[st] = round(mean(sv), 2)

    summary["n_seeds"] = len(rows)
    summary["episodes_per_seed"] = 2160
    summary["episodes_total"] = 2160 * len(rows)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "m1_multiseed.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_seed": rows}, f,
                  ensure_ascii=False, indent=1)

    with open(OUT / "m1_multiseed.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n合并结果（种子级）")
    for base in ("static", "evolve", "roll_nostab"):
        s = summary[f"roll_vs_{base}"]
        print(f"  roll - {base:<11} {s['mean_delta']:+.2f}  "
              f"CI {s['ci95_seed_level']}  正号种子 {s['positive_seeds']}/{s['seeds']}")
    for st in ("static", "evolve", "roll", "roll_nostab"):
        c = summary["completion"][st]
        print(f"  {st:<11} 完成 {c['mean']:.2f} ± {c['sd']:.2f}")


if __name__ == "__main__":
    main()
