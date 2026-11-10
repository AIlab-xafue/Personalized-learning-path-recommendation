# -*- coding: utf-8 -*-
"""
实验 8：学习者状态双时间尺度演化与学习路径滚动重规划（DTE-RR）

本脚本用于第二篇论文的修订版与学位论文第4章的扩展实验，回答四个问题：

  D1  把"静态规划 + 执行期局部修补"换成"状态演化 + 滚动重规划"，完成率与掌握率
      是否提升，提升来自哪一部分（演化本身 / 重规划 / 稳定性正则）。
  D2  增益是否依赖学习者异质性：尽责性与神经质的不同组合下，动态增益如何变化。
  D3  重规划频率的权衡：重规划越频繁，路径适配越好，但轨迹抖动也越强。
  D4  观测滞后与自评偏差下，滚动重规划的鲁棒性边界。
  D5  时间预算收紧时，动态重规划的价值是否变大。

设计原则：
  1. 图谱、结构难度、失败概率形式、状态更新量与前序实验（7 号脚本）保持一致，
     使新旧结果可比；新增部分只做"加法"，不改动原有机制。
  2. 所有对照使用同一批初始画像与同一随机种子，按学生个体配对比较。
  3. 每个数字都可复现：固定种子，输出 JSON 与 CSV，不手写任何结果。

运行：
    python 8_dynamic_path_evolution.py            # 全部实验，约 3-6 分钟
    python 8_dynamic_path_evolution.py --quick    # 小样本自检，约 20 秒

输出目录：Title2/dynamic_outputs/
"""

from __future__ import annotations

import os
import sys

# 固定字符串哈希顺序：图谱前驱/候选在平局时的排序取决于集合迭代顺序，
# 不同进程的哈希随机化会让同一种子产生不同结果。若未设置，则以固定值重启本进程。
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
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
PREREQ = Path(os.environ.get(
    "MOOCCUBE_DIR", str(ROOT / "data" / "MOOCCube")
)) / "relations" / "prerequisite-dependency.json"
OUT = Path(__file__).resolve().parent / "dynamic_outputs"
OUT.mkdir(exist_ok=True)

SEED = 20261108
GAP_PENALTY = 0.25          # 持续缺口惩罚，与第4章式(4-8)一致
ALPHA_GOAL = 0.80           # 目标尝试的情感失败系数
ALPHA_REM = 0.36            # 补救尝试的情感失败系数
DROPOUT = 0.95              # 退出阈值
SWITCH = 0.70               # 转恢复的资源切换阈值
WINDOW = 5                  # 慢尺度更新窗口（轮）


# ---------------------------------------------------------------- 基础工具
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def lcs_len(a: Sequence[str], b: Sequence[str]) -> int:
    """最长公共子序列长度，用于度量两条路径的相似度。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def path_divergence(old: Sequence[str], new: Sequence[str]) -> float:
    """重规划幅度：1 - LCS/max(len)，取值 0（完全不变）到 1（完全不同）。"""
    if not old or not new:
        return 0.0
    return round(1.0 - lcs_len(old, new) / max(len(old), len(new)), 4)


# ---------------------------------------------------------------- 知识图谱
class KG:
    """先修图 + 结构难度，与第4章式(4-5)一致。"""

    def __init__(self, path: Path = PREREQ) -> None:
        self.g = nx.DiGraph()
        with path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) != 2:
                    continue
                s, t = (self._name(v) for v in parts)
                if s and t and s != t:
                    self.g.add_edge(s, t)
        if not self.g:
            raise ValueError("先修关系文件为空")

        anc = {n: len(nx.ancestors(self.g, n)) for n in self.g.nodes}
        mx = max(anc.values()) or 1
        self.diff = {
            n: round(0.25 + (math.log1p(c) / math.log1p(mx)) * 0.60, 4)
            for n, c in anc.items()
        }
        self._succ = {n: list(self.g.successors(n)) for n in self.g.nodes}
        self._pred = {n: list(self.g.predecessors(n)) for n in self.g.nodes}

    @staticmethod
    def _name(cid: str) -> str:
        v = cid.strip()
        if v.startswith("K_"):
            v = v[2:]
        return v.rsplit("_", 1)[0] if "_" in v else v

    def d(self, n: str) -> float:
        return self.diff.get(n, 0.50)

    def succ(self, n: str) -> List[str]:
        return self._succ.get(n, [])

    def pred(self, n: str) -> List[str]:
        return self._pred.get(n, [])

    def easier_pred(self, n: str) -> Optional[str]:
        """严格先修：难度至少低 0.05 的直接前驱中最容易者。"""
        cand = [p for p in self.pred(n) if self.d(p) <= self.d(n) - 0.05]
        return min(cand, key=self.d) if cand else None

    def sample_problem(self, rng: random.Random, n_targets: int = 9) -> List[str]:
        """
        抽取一个学习任务：起点 + 若干待掌握目标。

        与"随机抽一条链"不同，目标之间不要求构成链，只要从起点可达。这样
        "先学哪个、走哪条路"就成为真正可优化的自由度，静态计划与动态重规划
        的差别才有观察空间。目标按难度分层抽取，保证任务本身有梯度。
        """
        starts = [n for n in self.g.nodes
                  if self.g.out_degree(n) > 0 and self.d(n) < 0.45]
        rng.shuffle(starts)
        for s0 in starts:
            reach = sorted(nx.descendants(self.g, s0), key=self.d)
            if len(reach) < n_targets * 4:
                continue
            third = len(reach) // 3
            picks: List[str] = []
            for bucket in (reach[:third], reach[third:2 * third], reach[2 * third:]):
                take = min(3, len(bucket))
                if take:
                    picks.extend(rng.sample(bucket, take))
            if len(picks) < n_targets:
                continue
            if len(picks) > n_targets:
                picks = rng.sample(picks, n_targets)
            rng.shuffle(picks)
            return [s0] + picks
        raise RuntimeError("未能抽取到合适的学习任务")


# ---------------------------------------------------------------- 学习者画像
@dataclass
class Learner:
    """四维学习者状态：性格（慢）、能力（累积）、情绪（快）、条件（外生）。"""

    conscientiousness: float     # 尽责性 C，调制能力增长率与补救效力
    neuroticism: float           # 神经质 N，调制情绪基线与失败敏感度
    openness: float              # 开放性 O，调制资源模态（视频）效力
    ability: float               # 能力 a_t
    emotion: float               # 情绪负荷 e_t
    budget: int = 60             # 条件：交互预算
    pressure: float = 0.30       # 条件：时间压力 τ

    # ---- 派生量
    @property
    def emotion_baseline(self) -> float:
        """情绪基线：神经质与时间压力共同抬高，见式(4-11)。"""
        return clamp(0.12 + 0.40 * self.neuroticism + 0.15 * self.pressure)

    @property
    def reversion(self) -> float:
        """情绪回归速率：情绪稳定者回落更快。"""
        return 0.08 + 0.12 * (1.0 - self.neuroticism)

    @property
    def fail_gain(self) -> float:
        """单次失败的情绪增量。"""
        return 0.12 + 0.06 * self.neuroticism

    @property
    def growth_rate(self) -> float:
        """能力增长率 η，见式(4-12)。"""
        return 0.03 + 0.05 * self.conscientiousness

    @property
    def video_efficacy(self) -> float:
        """资源模态效力：开放性正向、神经质负向。"""
        return clamp(0.60 + 0.25 * self.openness + 0.10 * (1 - self.neuroticism), 0.30, 0.95)

    def fast_update(self, event: str) -> None:
        """快尺度：情绪每轮更新，含向基线回归项。"""
        e = self.emotion + self.reversion * (self.emotion_baseline - self.emotion)
        if event == "FAIL":
            e += self.fail_gain
        elif event == "REST":
            e -= 0.25
        elif event == "PASS":
            e -= 0.04
        elif event == "REM":
            e -= 0.03
        self.emotion = clamp(e)

    def slow_update(self, window_success: float) -> None:
        """慢尺度：能力按饱和曲线增长，仅在窗口成功率过半时生效。"""
        gain = self.growth_rate * (1.0 - self.ability) * max(0.0, window_success - 0.50)
        self.ability = clamp(self.ability + gain)


# ---------------------------------------------------------------- 概率模型
def p_affective(learner: Learner, remedial: bool) -> float:
    """情感相关失败概率，式(4-7)。"""
    alpha = ALPHA_REM if remedial else ALPHA_GOAL
    return clamp(alpha * learner.emotion)


def p_success(learner: Learner, difficulty: float, gap: bool,
              remedial: bool, modulated: bool = True,
              prep: float = 0.0) -> float:
    """
    条件成功概率。

    在原有的能力—难度项之外加入先修准备度 prep：目标的前驱概念被掌握得越多，
    学习该目标越容易。这一项使"先学哪个"具有因果作用，也是路径顺序能够影响
    学习结果的前提。prep 为已掌握的直接前驱比例。

    modulated=False 时关闭性格对补救效力的加成，用于静态对照保持参数中性。
    """
    bonus = 0.04 * learner.conscientiousness if (remedial and modulated) else 0.0
    val = (learner.ability - 0.60 * difficulty + 0.40 + 0.35 * prep
           + bonus - (GAP_PENALTY if gap else 0.0))
    return clamp(val, 0.05, 0.95)


def readiness(kg: "KG", node: str, mastered: set) -> float:
    """先修准备度：直接前驱中已被掌握的比例；无前驱时视为完全准备。"""
    preds = kg.pred(node)
    if not preds:
        return 1.0
    return sum(1 for u in preds if u in mastered) / len(preds)


def risk(learner: Learner, node: str, kg: KG, gap: bool = False,
         remedial: bool = False, modulated: bool = True,
         prep: float = 0.0) -> float:
    """预计失败概率 = 情感失败 + 未情感失败时的认知失败。"""
    pa = p_affective(learner, remedial)
    ps = p_success(learner, kg.d(node), gap, remedial, modulated, prep)
    return pa + (1.0 - pa) * (1.0 - ps)


# ---------------------------------------------------------------- 规划器
class Replanner:
    """滚动重规划器：在剩余目标上做宽度受限的束搜索。"""

    def __init__(self, kg: KG) -> None:
        self.kg = kg
        self._cache: Dict[Tuple[str, str], List[str]] = {}
        self._prev_head: Optional[str] = None
        self.hop_threshold = 0.45
        self.replan_every = 4

    def target_difficulty(self, learner: Learner) -> float:
        """理想难度 d*：能力越强可接受越难，情绪越高应降低难度。"""
        return clamp(0.30 + 0.45 * learner.ability - 0.25 * learner.emotion, 0.25, 0.85)

    def _bridge(self, start: str, goal: str) -> List[str]:
        """返回 start 到 goal 的最短通路中间节点（不含两端）。"""
        if start == goal:
            return []
        key = (start, goal)
        if key in self._cache:
            return self._cache[key]
        try:
            p = nx.shortest_path(self.kg.g, start, goal)
            out = p[1:-1]
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            out = []
        self._cache[key] = out
        return out

    def score(self, learner: Learner, node: str, start: str,
              visited: Optional[set] = None,
              mastered: Optional[set] = None) -> float:
        """目标代价：预计失败风险 + 难度失配 + 绕行成本 + 重复访问惩罚。"""
        lam_risk, lam_diff, lam_bridge = 1.0, 1.2, 0.30
        if node == start or node in self.kg.succ(start):
            bridge = 0
        else:
            b = self._bridge(start, node)
            bridge = len(b) if b else 6
        prep = readiness(self.kg, node, mastered or set())
        j = (lam_risk * risk(learner, node, self.kg, prep=prep)
             + lam_diff * abs(self.kg.d(node) - self.target_difficulty(learner))
             + lam_bridge * min(bridge, 6))
        if visited and node in visited:
            j += 0.35
        return j

    def plan(self, learner: Learner, start: str, remaining: Iterable[str],
             lam_stab: float = 0.35, max_bridge: int = 4,
             visited: Optional[set] = None,
             mastered: Optional[set] = None) -> List[str]:
        """
        在当前状态上求解一条覆盖全部剩余目标的路径。

        1. 按"风险低、难度匹配、绕行少"排序，决定先攻克哪个目标；
        2. 稳定性正则：若上一轮的首目标与最优目标代价相差不足 lam_stab，保留原首目标；
        3. 依次把目标拼成路径，必要时插入最短通路上的桥梁节点。

        排序依赖当前的能力与情绪，因此同一任务在不同状态下会得到不同路径——
        这是"状态驱动重规划"与"固定序列"的实质差别。
        """
        order = [r for r in remaining if r != start]
        if not order:
            return []
        mastered = mastered or set()
        order.sort(key=lambda v: self.score(learner, v, start, visited, mastered))
        if self._prev_head and self._prev_head in order:
            gap = (self.score(learner, self._prev_head, start, visited, mastered)
                   - self.score(learner, order[0], start, visited, mastered))
            if gap < lam_stab:
                order.remove(self._prev_head)
                order.insert(0, self._prev_head)

        seq: List[str] = []
        cur = start
        for t in order:
            if t == cur:
                seq.append(t)
                continue
            if t in self.kg.succ(cur):
                seq.append(t)
                cur = t
                continue
            # 能力足够时直接挑战目标，跳过桥梁——"能力驱动的路径压缩"
            if risk(learner, t, self.kg, prep=readiness(self.kg, t, mastered)) <= self.hop_threshold:
                seq.append(t)
                cur = t
                continue
            bridges = self._bridge(cur, t)
            if bridges and len(bridges) <= max_bridge:
                seq.extend(bridges)
                seq.append(t)
                cur = t
            else:
                seq.append(t)
                cur = t
        self._prev_head = seq[0] if seq else None
        return seq


# ---------------------------------------------------------------- 执行器
@dataclass
class Episode:
    """一名学习者在一条路径上的一次完整执行记录。"""

    strategy: str
    completed: bool = False
    mastery: float = 0.0
    peak_emotion: float = 0.0
    steps: int = 0
    dropout: bool = False
    mismatch_steps: int = 0        # 状态—路径失配轮数
    replans: int = 0
    divergence: List[float] = field(default_factory=list)
    stable: int = 0                # 连续两轮计划未变的次数
    switches: int = 0              # 路径变更次数
    remedial: int = 0
    rest: int = 0


def run_episode(kg: KG, planner: Replanner, learner: Learner, initial: List[str],
                strategy: str, rng: random.Random,
                replan_every: int = 8, lam_stab: float = 0.50,
                lag: int = 0, warm_plan: Optional[List[str]] = None,
                shock: Optional[Dict] = None,
                trace: Optional[List[Dict]] = None) -> Episode:
    """
    执行一次学习过程。

    计划中的每个元素都带有角色：
        target  原路径上的待掌握概念，成功后才计入掌握集合
        bridge  为达成目标而临时插入的前置概念，成功后只前进计划、不计入掌握

    这与第4章"补救不推进目标指针"的原则一致，也避免把桥梁节点误算为学习成果。

    strategy:
        static      静态路径 + 局部修补（第4章原方法）；性格不参与参数调制
        evolve      静态路径 + 局部修补 + 双时间尺度演化（只加演化）
        roll        演化 + 滚动重规划（本方法）
        roll_nostab 演化 + 滚动重规划，关闭稳定性正则（消融）

    lag:       策略观测到的情绪滞后轮数（0 表示实时观测）。
    warm_plan: 静态基线使用的初始计划，即"入学时按初始画像一次性生成"的路径；
               动态策略忽略该参数，改为逐轮重规划。
    shock:     中途状态扰动，如 {"step": 20, "emotion": 0.35}，用于检验动态响应。
    trace:     可选的逐步追踪容器。传入空列表时，每轮追加一条记录，供可视化平台与
               过程分析使用。该参数不参与任何随机数抽取，因此不改变实验数值。
    """
    ep = Episode(strategy=strategy)
    use_evolve = strategy != "static"
    use_roll = strategy in ("roll", "roll_nostab")
    stab = 0.0 if strategy == "roll_nostab" else lam_stab

    targets = list(initial[1:])
    target_set = set(targets)
    learned = {initial[0]}      # 所有已通过的概念（含桥梁），用于计算先修准备度
    mastered = set()            # 只有原定目标，用于计算完成率
    # 静态基线：按初始状态一次性规划，之后不再改动
    if warm_plan is None and not use_roll:
        planner._prev_head = None
        warm_plan = planner.plan(learner, initial[0], targets, lam_stab=0.0,
                                 mastered=set(learned)) or list(targets)
        planner._prev_head = None
    plan: List[str] = list(warm_plan) if not use_roll else list(targets)
    cur = initial[0]
    planner._prev_head = None

    blocked: Optional[str] = None
    remediated: set = set()
    last_action = "GOAL"
    hist: List[str] = [initial[0]]
    window: List[int] = []
    emotion_hist: List[float] = [learner.emotion]
    learner._peak = learner.emotion
    stuck = 0
    prev_emotion = learner.emotion

    def observe() -> float:
        if lag <= 0:
            return learner.emotion
        return emotion_hist[max(0, len(emotion_hist) - 1 - lag)]

    def done() -> bool:
        return len(mastered) >= len(target_set)

    def rec(step: int, node: str, role: str, action: str, result: str,
            plan_snapshot: Sequence[str], risk_v: float,
            replanned: bool = False) -> None:
        """记录一轮交互，供前端回放；不参与任何随机数抽取。"""
        if trace is None:
            return
        trace.append({
            "step": step,
            "node": node,
            "role": role,
            "action": action,
            "result": result,
            "ability": round(learner.ability, 4),
            "emotion": round(learner.emotion, 4),
            "difficulty": round(kg.d(node), 4),
            "prep": round(readiness(kg, node, learned), 4),
            "risk": round(risk_v, 4),
            "plan": list(plan_snapshot)[:8],
            "plan_len": len(plan_snapshot),
            "mastered": len(mastered),
            "switches": ep.switches,
            "replan_just_now": replanned,
        })

    for step in range(1, learner.budget + 1):
        if shock and step == shock.get("step"):
            if "emotion" in shock:
                learner.emotion = clamp(learner.emotion + shock["emotion"])
            if "ability" in shock:
                learner.ability = clamp(learner.ability + shock["ability"])
            learner._peak = max(learner._peak, learner.emotion)

        if learner.emotion >= DROPOUT:
            ep.dropout = True
            ep.steps = step
            break

        # ---- 滚动重规划：阶段性调整，而非每轮洗牌
        replan_flag = False
        if use_roll:
            fresh = [t for t in targets if t not in mastered]
            if last_action == "PASS":
                stuck = 0
            elif last_action.startswith("FAIL"):
                stuck += 1

            # 触发条件：开局、周期性复核、当前目标反复卡住、情绪跨越阈值
            crossed = (prev_emotion < SWITCH <= learner.emotion) or \
                      (prev_emotion >= SWITCH > learner.emotion)
            trigger = (step == 1) or ((step - 1) % replan_every == 0) or stuck >= 2 or crossed

            if trigger and fresh:
                if stuck >= 2 and plan and plan[0] in target_set:
                    # 卡住：允许把当前目标整体后移，重新排序
                    new = planner.plan(learner, cur, fresh, lam_stab=stab,
                                       visited=set(hist), mastered=set(learned))
                else:
                    # 常规：锁定当前目标，只重排其后的部分，避免打断先修积累
                    head = plan[0] if plan and plan[0] in target_set else None
                    rest = [t for t in fresh if t != head]
                    tail = planner.plan(learner, head or cur, rest, lam_stab=stab,
                                        visited=set(hist), mastered=set(learned))
                    new = ([head] if head else []) + (tail or [])
                    if head is None:
                        new = planner.plan(learner, cur, fresh, lam_stab=stab,
                                           visited=set(hist), mastered=set(learned))
                if new and new != plan:
                    ep.switches += 1
                    ep.divergence.append(path_divergence(plan, new))
                    plan = new
                    replan_flag = True
        if not plan:
            plan = [t for t in targets if t not in mastered]
        if not plan or done():
            ep.completed = True
            ep.steps = step - 1
            break

        cur_node = plan[0]
        role = "target" if cur_node in target_set else "bridge"

        prep_now = readiness(kg, cur_node, learned)
        r_now = risk(learner, cur_node, kg, gap=(blocked == cur_node),
                     prep=prep_now)
        if r_now > 0.60:
            ep.mismatch_steps += 1

        # ---- 动作路由
        obs = observe()
        remedial_node = kg.easier_pred(cur_node)
        if obs > SWITCH or last_action == "FAIL_AFF":
            action = "REST"
        elif last_action in ("FAIL_COG", "FAIL") and remedial_node and cur_node not in remediated:
            action = "REM"
        else:
            action = "GOAL"

        if action == "REST":
            ep.rest += 1
            efficacy = learner.video_efficacy if use_evolve else 0.80
            if rng.random() <= efficacy:
                learner.fast_update("REST")
                last_action = "REST_OK"
            else:
                learner.fast_update("FAIL")
                last_action = "FAIL_AFF"
            ep.steps = step
            prev_emotion = learner.emotion
            learner._peak = max(learner._peak, learner.emotion)
            emotion_hist.append(learner.emotion)
            rec(step, cur_node, role, "REST", last_action, plan, r_now,
                replanned=replan_flag)
            continue

        node = remedial_node if action == "REM" else cur_node
        gap = (blocked == cur_node and cur_node not in remediated and action == "GOAL")
        if rng.random() < p_affective(learner, action == "REM"):
            learner.fast_update("FAIL")
            last_action = "FAIL_AFF"
            window.append(0)
        else:
            ps = p_success(learner, kg.d(node), gap, action == "REM",
                           modulated=use_evolve,
                           prep=readiness(kg, node, learned))
            if rng.random() < ps:
                if action == "REM":
                    ep.remedial += 1
                    remediated.add(cur_node)
                    learner.fast_update("REM")
                    last_action = "REM_OK"
                    window.append(1)
                else:
                    learner.fast_update("PASS")
                    learned.add(cur_node)
                    if role == "target":
                        mastered.add(cur_node)
                    cur = cur_node
                    blocked = None
                    plan = plan[1:]
                    if node not in hist:
                        hist.append(node)
                    last_action = "PASS"
                    window.append(1)
                    if done():
                        ep.completed = True
                        ep.steps = step
                        ep.mastery = 100.0
                        ep.peak_emotion = round(max(learner._peak, learner.emotion), 4)
                        return ep
            else:
                learner.fast_update("FAIL")
                if action == "GOAL":
                    blocked = cur_node
                last_action = "FAIL_COG"
                window.append(0)

        if use_evolve and len(window) >= WINDOW:
            learner.slow_update(mean(window))
            window = []

        ep.steps = step
        prev_emotion = learner.emotion
        ep.peak_emotion = round(max(learner._peak, learner.emotion), 4)
        emotion_hist.append(learner.emotion)
        rec(step, cur_node, role, action, last_action, plan, r_now,
            replanned=replan_flag)

    ep.mastery = round((len(mastered) + 1) / len(initial) * 100, 2)
    ep.peak_emotion = round(max(getattr(learner, "_peak", learner.emotion), learner.emotion), 4)
    ep.completed = done()
    return ep


# ---------------------------------------------------------------- 记录峰值
def _track_peak(learner: Learner) -> None:
    learner._peak = max(getattr(learner, "_peak", 0.0), learner.emotion)


# ---------------------------------------------------------------- 实验 D1
PROTOTYPES = {
    "勤奋稳健": dict(conscientiousness=0.80, neuroticism=0.25, openness=0.60),
    "焦虑敏感": dict(conscientiousness=0.60, neuroticism=0.75, openness=0.45),
    "探索开放": dict(conscientiousness=0.45, neuroticism=0.40, openness=0.85),
    "时间紧迫": dict(conscientiousness=0.55, neuroticism=0.55, openness=0.50),
}

STRATEGIES = ["static", "evolve", "roll", "roll_nostab"]


def make_learners(rng: random.Random, proto: str, n: int, budget: int = 50,
                  ability_shift: float = 0.0) -> List[Learner]:
    base = PROTOTYPES[proto]
    out = []
    for _ in range(n):
        out.append(Learner(
            conscientiousness=clamp(base["conscientiousness"] + rng.gauss(0, 0.06)),
            neuroticism=clamp(base["neuroticism"] + rng.gauss(0, 0.06)),
            openness=clamp(base["openness"] + rng.gauss(0, 0.06)),
            ability=clamp(rng.uniform(0.30, 0.80) + ability_shift),
            emotion=clamp(rng.uniform(0.10, 0.50)),
            budget=budget,
            pressure=0.15 if proto != "时间紧迫" else 0.70,
        ))
    return out


def blend(rng: random.Random, proto: str, ability_shift: float = 0.0,
          budget: int = 50) -> Learner:
    """为同一初始画像生成四个策略各自的副本，保证配对比较。"""
    base = PROTOTYPES[proto]
    return Learner(
        conscientiousness=clamp(base["conscientiousness"] + rng.gauss(0, 0.06)),
        neuroticism=clamp(base["neuroticism"] + rng.gauss(0, 0.06)),
        openness=clamp(base["openness"] + rng.gauss(0, 0.06)),
        ability=clamp(rng.uniform(0.30, 0.80) + ability_shift),
        emotion=clamp(rng.uniform(0.10, 0.50)),
        budget=budget,
        pressure=0.15 if proto != "时间紧迫" else 0.70,
    )


def copy_learner(l: Learner) -> Learner:
    m = Learner(l.conscientiousness, l.neuroticism, l.openness,
                l.ability, l.emotion, l.budget, l.pressure)
    m._peak = l.emotion
    return m


def experiment_main(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D1：四策略配对比较。"""
    n_paths = 6 if quick else 18
    n_learners = 12 if quick else 30
    rng = random.Random(SEED)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]
    rows: Dict[str, List[Episode]] = {s: [] for s in STRATEGIES}
    per_proto: Dict[str, Dict[str, List[Episode]]] = {
        p: {s: [] for s in STRATEGIES} for p in PROTOTYPES
    }

    for path in problems:
        for proto in PROTOTYPES:
            for _ in range(n_learners):
                base = blend(rng, proto)
                for s in STRATEGIES:
                    lr = copy_learner(base)
                    ep = run_episode(kg, planner, lr, path, s,
                                     random.Random(rng.randint(1, 10 ** 9)))
                    ep.peak_emotion = round(getattr(lr, "_peak", lr.emotion), 4)
                    rows[s].append(ep)
                    per_proto[proto][s].append(ep)

    def agg(eps: List[Episode]) -> Dict:
        return {
            "n": len(eps),
            "completion": round(mean([100.0 if e.completed else 0.0 for e in eps]), 2),
            "mastery": round(mean([e.mastery for e in eps]), 2),
            "peak_emotion": round(mean([e.peak_emotion for e in eps]), 4),
            "steps": round(mean([e.steps for e in eps]), 2),
            "dropout": round(mean([100.0 if e.dropout else 0.0 for e in eps]), 2),
            "mismatch_rate": round(mean([
                100.0 * e.mismatch_steps / max(1, e.steps) for e in eps]), 2),
            "replans": round(mean([e.switches for e in eps]), 2),
            "divergence": round(mean([mean(e.divergence) if e.divergence else 0.0 for e in eps]), 4),
        }

    overall = {s: agg(rows[s]) for s in STRATEGIES}
    by_proto = {p: {s: agg(per_proto[p][s]) for s in STRATEGIES} for p in PROTOTYPES}

    # 配对差值：roll 相对 static / evolve
    paired = {}
    for base_s in ("static", "evolve", "roll_nostab"):
        diffs = []
        for a, b in zip(rows["roll"], rows[base_s]):
            diffs.append((100.0 if a.completed else 0.0) - (100.0 if b.completed else 0.0))
        # 路径聚类自助区间
        ci = bootstrap_ci(diffs, rng, 2000)
        wins = sum(1 for d in diffs if d > 0)
        paired[f"roll_vs_{base_s}"] = {
            "delta_completion": round(mean(diffs), 2),
            "ci95": ci,
            "win_rate": round(100.0 * wins / max(1, len(diffs)), 2),
        }

    return {
        "n_paths": n_paths, "n_learners_per_proto": n_learners,
        "problems_sample": {f"p{i+1}": p for i, p in enumerate(problems[:3])},
        "overall": overall, "by_prototype": by_proto, "paired": paired,
    }


def bootstrap_ci(xs: List[float], rng: random.Random, n: int = 2000) -> List[float]:
    if not xs:
        return [0.0, 0.0]
    means = []
    for _ in range(n):
        means.append(mean([xs[rng.randrange(len(xs))] for _ in range(len(xs))]))
    means.sort()
    return [round(means[int(0.025 * n)], 2), round(means[int(0.975 * n) - 1], 2)]


# ---------------------------------------------------------------- 实验 D2
def experiment_heterogeneity(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D2：尽责性 × 神经质 网格，比较 static 与 roll 的完成率差。"""
    n_paths = 4 if quick else 8
    n_learners = 8 if quick else 26
    rng = random.Random(SEED + 1)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]
    grid = []
    for c in (0.20, 0.50, 0.80):
        for nn in (0.20, 0.50, 0.80):
            st, ro = [], []
            for path in problems:
                for _ in range(n_learners):
                    lr = Learner(c, nn, 0.50, clamp(rng.uniform(0.30, 0.80)),
                                 clamp(rng.uniform(0.10, 0.50)), 50, 0.30 * nn + 0.15)
                    for s, box in (("static", st), ("roll", ro)):
                        m = copy_learner(lr)
                        ep = run_episode(kg, planner, m, path, s,
                                         random.Random(rng.randint(1, 10 ** 9)))
                        box.append(100.0 if ep.completed else 0.0)
            a, b = mean(st), mean(ro)
            grid.append({
                "conscientiousness": c, "neuroticism": nn,
                "static": round(a, 2), "roll": round(b, 2),
                "gain": round(b - a, 2),
            })
    return {"grid": grid}


# ---------------------------------------------------------------- 实验 D3
def experiment_replan_frequency(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D3：重规划周期对完成率与轨迹稳定性的影响。"""
    n_paths = 4 if quick else 8
    n_learners = 8 if quick else 16
    rng = random.Random(SEED + 2)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]
    out = []
    for every in (1, 2, 3, 5, 10):
        comp, div, sw, stb = [], [], [], []
        for path in problems:
            for _ in range(n_learners):
                lr = Learner(0.60, 0.50, 0.55, clamp(rng.uniform(0.30, 0.80)),
                             clamp(rng.uniform(0.10, 0.50)))
                m = copy_learner(lr)
                ep = run_episode(kg, planner, m, path, "roll",
                                 random.Random(rng.randint(1, 10 ** 9)),
                                 replan_every=every)
                comp.append(100.0 if ep.completed else 0.0)
                if ep.divergence:
                    div.append(mean(ep.divergence))
                sw.append(ep.switches)
        out.append({
            "replan_every": every,
            "completion": round(mean(comp), 2),
            "mean_divergence": round(mean(div) if div else 0.0, 4),
            "path_changes": round(mean(sw), 2),
        })
    return {"frequency": out}


# ---------------------------------------------------------------- 实验 D4
def experiment_lag_prior(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D4：观测滞后与自评能力偏差下的鲁棒性。"""
    n_paths = 4 if quick else 8
    n_learners = 8 if quick else 16
    rng = random.Random(SEED + 3)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]

    lag_rows, prior_rows = [], []
    for lag in (0, 1, 2, 3):
        comp = []
        for path in problems:
            for _ in range(n_learners):
                lr = Learner(0.60, 0.50, 0.55, clamp(rng.uniform(0.30, 0.80)),
                             clamp(rng.uniform(0.10, 0.50)))
                m = copy_learner(lr)
                ep = run_episode(kg, planner, m, path, "roll",
                                 random.Random(rng.randint(1, 10 ** 9)), lag=lag)
                comp.append(100.0 if ep.completed else 0.0)
        lag_rows.append({"lag": lag, "completion": round(mean(comp), 2)})

    for shift in (-0.10, 0.0, 0.10):
        comp_s, comp_r = [], []
        for path in problems:
            for _ in range(n_learners):
                lr = blend(rng, "勤奋稳健", ability_shift=shift)
                for s, box in (("static", comp_s), ("roll", comp_r)):
                    m = copy_learner(lr)
                    # 自评偏差：策略看到的是错位的初始能力
                    m.ability = clamp(m.ability + shift)
                    ep = run_episode(kg, planner, m, path, s,
                                     random.Random(rng.randint(1, 10 ** 9)))
                    box.append(100.0 if ep.completed else 0.0)
        prior_rows.append({
            "self_report_shift": shift,
            "static": round(mean(comp_s), 2),
            "roll": round(mean(comp_r), 2),
            "gain": round(mean(comp_r) - mean(comp_s), 2),
        })
    return {"lag": lag_rows, "prior": prior_rows}


# ---------------------------------------------------------------- 实验 D5
def experiment_budget(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D5：时间预算收紧时动态重规划的价值。"""
    n_paths = 4 if quick else 8
    n_learners = 8 if quick else 16
    rng = random.Random(SEED + 4)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]
    out = []
    for budget in (30, 40, 50, 70):
        st, ro = [], []
        for path in problems:
            for _ in range(n_learners):
                lr = Learner(0.60, 0.50, 0.55, clamp(rng.uniform(0.30, 0.80)),
                             clamp(rng.uniform(0.10, 0.50)), budget)
                for s, box in (("static", st), ("roll", ro)):
                    m = copy_learner(lr)
                    m.budget = budget
                    ep = run_episode(kg, planner, m, path, s,
                                     random.Random(rng.randint(1, 10 ** 9)))
                    box.append(100.0 if ep.completed else 0.0)
        a, b = mean(st), mean(ro)
        out.append({"budget": budget, "static": round(a, 2), "roll": round(b, 2),
                    "gain": round(b - a, 2)})
    return {"budget": out}


# ---------------------------------------------------------------- 实验 D6
SHOCKS = [
    ("无扰动", None),
    ("情绪冲击", {"step": 18, "emotion": 0.35}),
    ("能力跃迁", {"step": 18, "ability": 0.15}),
]


def experiment_shock(kg: KG, planner: Replanner, quick: bool = False) -> Dict:
    """D6：中途状态突变下，固定计划与滚动重规划的响应差异。"""
    n_paths = 4 if quick else 8
    n_learners = 8 if quick else 16
    rng = random.Random(SEED + 5)
    problems = [kg.sample_problem(rng, 6) for _ in range(n_paths)]
    out = []
    for name, shock in SHOCKS:
        st, ro, st_peak, ro_peak = [], [], [], []
        for path in problems:
            for _ in range(n_learners):
                lr = Learner(0.60, 0.50, 0.55, clamp(rng.uniform(0.30, 0.80)),
                             clamp(rng.uniform(0.10, 0.50)))
                for s, box, pk in (("static", st, st_peak), ("roll", ro, ro_peak)):
                    m = copy_learner(lr)
                    m._peak = m.emotion
                    ep = run_episode(kg, planner, m, path, s,
                                     random.Random(rng.randint(1, 10 ** 9)),
                                     shock=shock)
                    box.append(100.0 if ep.completed else 0.0)
                    pk.append(ep.peak_emotion)
        out.append({
            "shock": name,
            "static": round(mean(st), 2),
            "roll": round(mean(ro), 2),
            "gain": round(mean(ro) - mean(st), 2),
            "static_peak": round(mean(st_peak), 4),
            "roll_peak": round(mean(ro_peak), 4),
        })
    return {"shock": out}


# ---------------------------------------------------------------- 输出
def dump(name: str, obj: Dict) -> None:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {p.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="小样本自检")
    args = ap.parse_args()

    t0 = time.time()
    print("构建图谱 ...")
    kg = KG()
    print(f"  节点 {kg.g.number_of_nodes()}  边 {kg.g.number_of_edges()}")
    planner = Replanner(kg)

    print("D1 四策略主对照 ...")
    d1 = experiment_main(kg, planner, args.quick)
    dump("d1_main", d1)
    for s, v in d1["overall"].items():
        print(f"    {s:11s} 完成 {v['completion']:6.2f}  掌握 {v['mastery']:6.2f} "
              f" 峰值情绪 {v['peak_emotion']:.3f}  失配 {v['mismatch_rate']:5.2f}%")

    print("D2 性格异质性 ...")
    dump("d2_heterogeneity", experiment_heterogeneity(kg, planner, args.quick))

    print("D3 重规划频率 ...")
    dump("d3_frequency", experiment_replan_frequency(kg, planner, args.quick))

    print("D4 滞后与自评偏差 ...")
    dump("d4_lag_prior", experiment_lag_prior(kg, planner, args.quick))

    print("D5 时间预算 ...")
    dump("d5_budget", experiment_budget(kg, planner, args.quick))

    print("D6 中途扰动 ...")
    dump("d6_shock", experiment_shock(kg, planner, args.quick))

    # CSV：主表
    with (OUT / "d1_main.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        keys = ["completion", "mastery", "peak_emotion", "steps", "dropout",
                "mismatch_rate", "replans", "divergence"]
        w.writerow(["strategy"] + keys)
        for s, v in d1["overall"].items():
            w.writerow([s] + [v[k] for k in keys])

    meta = {
        "seed": SEED,
        "quick": args.quick,
        "runtime_sec": round(time.time() - t0, 1),
        "graph": {"nodes": kg.g.number_of_nodes(), "edges": kg.g.number_of_edges()},
        "params": {
            "gap_penalty": GAP_PENALTY, "alpha_goal": ALPHA_GOAL,
            "alpha_rem": ALPHA_REM, "dropout": DROPOUT, "switch": SWITCH,
            "slow_window": WINDOW,
        },
    }
    dump("meta", meta)
    print(f"完成，用时 {meta['runtime_sec']} 秒")


if __name__ == "__main__":
    main()
