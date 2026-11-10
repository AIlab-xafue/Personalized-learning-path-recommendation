"""
Reproducible supplementary experiments for the dual-state learning-path agent.

Run with the Python environment that already contains numpy, networkx, scipy and
matplotlib, for example:

    python 7_dual_state_extended_experiments.py

Outputs are written to ./dual_state_outputs:
    - main_experiment_per_seed.csv
    - ablation_per_seed.csv
    - cohort_per_seed.csv
    - sensitivity_per_seed.csv
    - statistical_tests.csv
    - experiment_summary.json
    - figure1_dual_state_framework.png
    - figure2_main_outcomes.png
    - figure3_video_sensitivity.png
"""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

try:
    from scipy import stats
except Exception:  # pragma: no cover - scipy is optional for portability.
    stats = None


SCRIPT_DIR = Path(__file__).resolve().parent
PREREQ_PATH = SCRIPT_DIR.parent / "big" / "MOOCCube" / "relations" / "prerequisite-dependency.json"
OUTPUT_DIR = SCRIPT_DIR / "dual_state_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_SEED = 20260924
DEFAULT_START_NODE = None
PATH_LENGTH = 10
MAIN_STUDENTS_PER_SEED = 100
COHORT_STUDENTS_PER_SEED = 50
N_SEEDS = 10
MAX_STEPS = 50
MAIN_VIDEO_SUCCESS_PROB = 0.80


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class KnowledgeGraph:
    """Knowledge-graph wrapper with topological difficulty and downgrade search."""

    def __init__(self, relation_path: Path = PREREQ_PATH):
        self.relation_path = relation_path
        self.graph = nx.DiGraph()

        if not relation_path.exists():
            raise FileNotFoundError(f"Cannot find prerequisite relation file: {relation_path}")

        with relation_path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) != 2:
                    continue
                source, target = (self._concept_name(value) for value in parts)
                if source and target and source != target:
                    self.graph.add_edge(source, target)

        if not self.graph:
            raise ValueError(f"No prerequisite edges were loaded from {relation_path}")

        ancestor_counts = {
            node: len(nx.ancestors(self.graph, node))
            for node in self.graph.nodes
        }
        max_ancestors = max(ancestor_counts.values()) if ancestor_counts else 1
        self.node_difficulty = {
            node: round(
                0.25 + (math.log1p(count) / math.log1p(max_ancestors)) * 0.60,
                4,
            )
            for node, count in ancestor_counts.items()
        }

    @staticmethod
    def _concept_name(concept_id: str) -> str:
        value = concept_id.strip()
        if value.startswith("K_"):
            value = value[2:]
        return value.rsplit("_", 1)[0] if "_" in value else value

    def difficulty(self, node: str) -> float:
        return self.node_difficulty.get(node, 0.50)

    def generate_path(
        self,
        start_node: Optional[str] = DEFAULT_START_NODE,
        length: int = PATH_LENGTH,
        seed: int = BASE_SEED,
    ) -> List[str]:
        """Generate one reproducible directed prerequisite chain."""
        rng = random.Random(seed)
        if start_node is not None and start_node not in self.graph:
            raise ValueError(f"Start node {start_node!r} is not in the graph.")

        starts = [start_node] if start_node is not None else list(self.graph.nodes)
        starts = [node for node in starts if self.graph.out_degree(node) > 0]
        rng.shuffle(starts)
        starts.sort(key=lambda node: self.difficulty(node))

        def search(node: str, path: List[str]) -> Optional[List[str]]:
            if len(path) >= length:
                return path
            successors = [n for n in self.graph.successors(node) if n not in path]
            rng.shuffle(successors)
            successors.sort(key=lambda n: (self.difficulty(n), self.graph.out_degree(n)))
            for successor in successors:
                result = search(successor, path + [successor])
                if result is not None:
                    return result
            return None

        for candidate in starts:
            result = search(candidate, [candidate])
            if result is not None:
                return result
        raise ValueError(f"No directed prerequisite chain of length {length} was found.")

    def find_easier_related_node(
        self,
        current_node: str,
        current_history: Iterable[str],
        planned_path: List[str],
    ) -> str:
        """Find a lower-difficulty prerequisite or previously visited concept."""
        current_difficulty = self.difficulty(current_node)

        predecessors = []
        if current_node in self.graph:
            predecessors = [
                n for n in self.graph.predecessors(current_node)
                if self.difficulty(n) < current_difficulty - 0.05
            ]
        if predecessors:
            return min(predecessors, key=self.difficulty)

        history_candidates = [
            n for n in current_history
            if self.difficulty(n) < current_difficulty - 0.05
        ]
        if history_candidates:
            return min(history_candidates, key=self.difficulty)

        path_candidates = [
            n for n in planned_path
            if self.difficulty(n) < current_difficulty - 0.05
        ]
        if path_candidates:
            return min(path_candidates, key=self.difficulty)

        return current_node


@dataclass
class UserProfile:
    user_id: str
    total_path_len: int
    ability: float
    anxiety: float
    mastered_nodes: set = field(default_factory=set)
    last_feedback: str = "PASS"
    peak_anxiety: float = field(init=False)

    def __post_init__(self) -> None:
        self.peak_anxiety = self.anxiety

    @property
    def mastery(self) -> float:
        return len(self.mastered_nodes) / self.total_path_len if self.total_path_len else 0.0

    def update(self, feedback: str, node: str, counts_toward_path: bool = False) -> None:
        self.last_feedback = feedback
        if feedback in {"PASS", "GOAL_REACHED"}:
            if counts_toward_path:
                self.mastered_nodes.add(node)
            self.ability = clamp(self.ability + 0.02, 0.0, 1.0)
            self.anxiety = clamp(self.anxiety - 0.05, 0.0, 1.0)
        elif feedback == "PASS_REMEDIAL":
            self.ability = clamp(self.ability + 0.05, 0.0, 1.0)
            self.anxiety = clamp(self.anxiety - 0.03, 0.0, 1.0)
        elif feedback == "PASS_REST":
            self.anxiety = clamp(self.anxiety - 0.25, 0.0, 1.0)
        elif feedback.startswith("FAIL"):
            self.anxiety = clamp(self.anxiety + 0.15, 0.0, 1.0)
        self.peak_anxiety = max(self.peak_anxiety, self.anxiety)


class StudentSimulator:
    def __init__(
        self,
        path: List[str],
        profile: UserProfile,
        kg: KnowledgeGraph,
        rng: random.Random,
        anxiety_failure_weight: float = 0.80,
        video_success_prob: float = 1.00,
        dropout_threshold: float = 0.95,
    ):
        self.path = path
        self.profile = profile
        self.kg = kg
        self.rng = rng
        self.anxiety_failure_weight = anxiety_failure_weight
        self.video_success_prob = video_success_prob
        self.dropout_threshold = dropout_threshold
        self.target_index = 1 if len(path) > 1 else 0
        self.history = [path[0]]
        self.hard_blocked_targets = set()
        self.remediated_targets = set()
        self.profile.mastered_nodes.add(path[0])

    @property
    def target_node(self) -> str:
        return self.path[self.target_index]

    def step(self, action: str) -> str:
        if self.profile.anxiety >= self.dropout_threshold:
            return "DROPOUT"

        node_name, resource_type = self._parse_action(action)
        difficulty = self.kg.difficulty(node_name)

        if "视频" in resource_type or "video" in resource_type.lower():
            if self.rng.random() <= self.video_success_prob:
                self.profile.update("PASS_REST", node_name)
                return "PASS_REST"
            self.profile.update("FAIL_ANXIOUS", node_name)
            return "FAIL_ANXIOUS"

        remedial = "基础" in resource_type or "remedial" in resource_type.lower()
        affective_weight = self.anxiety_failure_weight * (0.45 if remedial else 1.0)
        if self.rng.random() < self.profile.anxiety * affective_weight:
            self.profile.update("FAIL_ANXIOUS", node_name)
            return "FAIL_ANXIOUS"

        unresolved_gap = (
            not remedial
            and self.target_node in self.hard_blocked_targets
            and self.target_node not in self.remediated_targets
        )
        gap_penalty = 0.25 if unresolved_gap else 0.0
        success_prob = clamp(
            self.profile.ability - difficulty * 0.60 + 0.40 - gap_penalty,
            0.05,
            0.95,
        )
        if self.rng.random() < success_prob:
            if node_name not in self.history:
                self.history.append(node_name)
            if remedial:
                self.remediated_targets.add(self.target_node)
                self.profile.update("PASS_REMEDIAL", node_name)
                return "PASS_REMEDIAL"

            is_target = node_name == self.target_node
            feedback = "GOAL_REACHED" if is_target and self.target_index == len(self.path) - 1 else "PASS"
            self.profile.update(feedback, node_name, counts_toward_path=is_target)
            if feedback == "GOAL_REACHED":
                return "GOAL_REACHED"
            if is_target:
                self.hard_blocked_targets.discard(node_name)
                self.remediated_targets.discard(node_name)
                self.target_index += 1
            return feedback

        if not remedial and node_name == self.target_node:
            self.hard_blocked_targets.add(node_name)
        self.profile.update("FAIL_HARD", node_name)
        return "FAIL_HARD"

    @staticmethod
    def _parse_action(action: str) -> Tuple[str, str]:
        if "(" in action and ")" in action:
            node, rest = action.split("(", 1)
            return node.strip(), rest.split(")", 1)[0].strip()
        return action.strip(), ""


class PolicyAgent:
    def __init__(self, path: List[str], kg: KnowledgeGraph):
        self.path = path
        self.kg = kg

    def generate(self, target_node: str, profile: UserProfile, history: List[str], strategy: str) -> str:
        if strategy == "static":
            return f"{target_node}(概念)"

        if strategy == "cognitive_only":
            if profile.last_feedback.startswith("FAIL"):
                easier = self.kg.find_easier_related_node(target_node, history, self.path)
                return f"{easier}(基础概念)"
            return f"{target_node}(概念)"

        if strategy == "affective_only":
            if profile.last_feedback.startswith("FAIL") or profile.anxiety > 0.70:
                return f"{target_node}(视频)"
            return f"{target_node}(概念)"

        if strategy == "fusion":
            if profile.last_feedback == "FAIL_ANXIOUS" or profile.anxiety > 0.70:
                return f"{target_node}(视频)"
            if profile.last_feedback == "FAIL_HARD":
                easier = self.kg.find_easier_related_node(target_node, history, self.path)
                if easier == target_node:
                    return f"{target_node}(视频)"
                return f"{easier}(基础概念)"
            return f"{target_node}(概念)"

        raise ValueError(f"Unknown strategy: {strategy}")


def run_single(
    student_config: Dict[str, float],
    path: List[str],
    kg: KnowledgeGraph,
    strategy: str,
    seed: int,
    video_success_prob: float = 1.00,
    max_steps: int = MAX_STEPS,
) -> Dict[str, float]:
    rng = random.Random(seed)
    profile = UserProfile(
        user_id=str(student_config["id"]),
        total_path_len=len(path),
        ability=float(student_config["ability"]),
        anxiety=float(student_config["anxiety"]),
    )
    simulator = StudentSimulator(
        path=path,
        profile=profile,
        kg=kg,
        rng=rng,
        video_success_prob=video_success_prob,
    )
    agent = PolicyAgent(path, kg)

    goal_reached = False
    dropout = False
    steps = 0
    for steps in range(1, max_steps + 1):
        action = agent.generate(simulator.target_node, profile, simulator.history, strategy)
        feedback = simulator.step(action)
        if feedback == "GOAL_REACHED":
            goal_reached = True
            break
        if feedback == "DROPOUT":
            dropout = True
            break

    return {
        "goal_reached": float(goal_reached),
        "mastery": profile.mastery,
        "peak_anxiety": profile.peak_anxiety,
        "steps": float(steps),
        "dropout": float(dropout),
    }


def generate_uniform_students(seed: int, n: int) -> List[Dict[str, float]]:
    rng = random.Random(seed)
    return [
        {
            "id": f"u{seed}_{i:03d}",
            "ability": round(rng.uniform(0.30, 0.80), 4),
            "anxiety": round(rng.uniform(0.10, 0.50), 4),
        }
        for i in range(n)
    ]


def generate_cohort_students(seed: int, n: int, ability_mean: float, anxiety_mean: float) -> List[Dict[str, float]]:
    rng = random.Random(seed)
    return [
        {
            "id": f"c{seed}_{i:03d}",
            "ability": round(clamp(rng.gauss(ability_mean, 0.06), 0.10, 0.95), 4),
            "anxiety": round(clamp(rng.gauss(anxiety_mean, 0.05), 0.05, 0.90), 4),
        }
        for i in range(n)
    ]


def aggregate_student_results(
    rows: List[Dict[str, float]],
    seed: int,
    strategy: str,
    experiment: str,
    cohort: str = "",
    video_success_prob: Optional[float] = None,
) -> Dict[str, float]:
    return {
        "experiment": experiment,
        "seed": seed,
        "cohort": cohort,
        "strategy": strategy,
        "video_success_prob": "" if video_success_prob is None else video_success_prob,
        "goal_completion": np.mean([r["goal_reached"] for r in rows]) * 100,
        "final_mastery": np.mean([r["mastery"] for r in rows]) * 100,
        "peak_anxiety": np.mean([r["peak_anxiety"] for r in rows]),
        "avg_steps": np.mean([r["steps"] for r in rows]),
        "dropout_rate": np.mean([r["dropout"] for r in rows]) * 100,
    }


def run_seeded_experiment(
    kg: KnowledgeGraph,
    path: List[str],
    strategies: List[str],
    student_generator,
    experiment: str,
    n_per_seed: int,
    cohort: str = "",
    video_success_prob: float = MAIN_VIDEO_SUCCESS_PROB,
) -> List[Dict[str, float]]:
    per_seed = []
    for seed_idx in range(N_SEEDS):
        seed = BASE_SEED + seed_idx
        students = student_generator(seed, n_per_seed)
        for strategy_idx, strategy in enumerate(strategies):
            rows = []
            for i, student in enumerate(students):
                # Common random numbers make early, shared parts of each policy
                # trajectory directly comparable for the same synthetic learner.
                sim_seed = seed * 100_000 + i * 101
                rows.append(
                    run_single(
                        student,
                        path,
                        kg,
                        strategy,
                        seed=sim_seed,
                        video_success_prob=video_success_prob,
                    )
                )
            per_seed.append(
                aggregate_student_results(
                    rows,
                    seed=seed,
                    strategy=strategy,
                    experiment=experiment,
                    cohort=cohort,
                    video_success_prob=video_success_prob,
                )
            )
    return per_seed


def summarize(per_seed_rows: List[Dict[str, float]], group_fields: List[str]) -> List[Dict[str, object]]:
    metrics = ["goal_completion", "final_mastery", "peak_anxiety", "avg_steps", "dropout_rate"]
    groups: Dict[Tuple[object, ...], List[Dict[str, float]]] = {}
    for row in per_seed_rows:
        key = tuple(row[field] for field in group_fields)
        groups.setdefault(key, []).append(row)

    summary = []
    for key, rows in groups.items():
        out = {field: value for field, value in zip(group_fields, key)}
        for metric in metrics:
            values = np.array([float(r[metric]) for r in rows], dtype=float)
            out[f"{metric}_mean"] = float(values.mean())
            out[f"{metric}_sd"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        summary.append(out)
    return summary


def paired_tests(per_seed_rows: List[Dict[str, float]], experiment: str, baseline: str, proposed: str) -> List[Dict[str, object]]:
    metrics = ["goal_completion", "final_mastery", "peak_anxiety", "avg_steps", "dropout_rate"]
    subset = [r for r in per_seed_rows if r["experiment"] == experiment and r["cohort"] == ""]
    by_seed_strategy = {(r["seed"], r["strategy"]): r for r in subset}
    seeds = sorted({r["seed"] for r in subset})
    out = []
    for metric in metrics:
        base_values = []
        prop_values = []
        for seed in seeds:
            b = by_seed_strategy.get((seed, baseline))
            p = by_seed_strategy.get((seed, proposed))
            if b and p:
                base_values.append(float(b[metric]))
                prop_values.append(float(p[metric]))
        if not base_values:
            continue
        base_arr = np.array(base_values)
        prop_arr = np.array(prop_values)
        diff = prop_arr - base_arr
        t_value = ""
        p_value = ""
        if stats is not None and len(diff) > 1 and diff.std(ddof=1) > 0:
            t_value, p_value = stats.ttest_rel(prop_arr, base_arr)
            t_value = float(t_value)
            p_value = float(p_value)
        dz = float(diff.mean() / diff.std(ddof=1)) if len(diff) > 1 and diff.std(ddof=1) > 0 else ""
        out.append(
            {
                "experiment": experiment,
                "comparison": f"{proposed} vs {baseline}",
                "metric": metric,
                "baseline_mean": float(base_arr.mean()),
                "proposed_mean": float(prop_arr.mean()),
                "mean_difference": float(diff.mean()),
                "paired_t": t_value,
                "p_value": p_value,
                "cohens_dz": dz,
            }
        )
    return out


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_mean_sd(mean: float, sd: float, decimals: int = 1) -> str:
    return f"{mean:.{decimals}f} ± {sd:.{decimals}f}"


def plot_framework(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 7.0), dpi=260)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    def box(x, y, w, h, title, lines, face, edge="#31465A"):
        rect = plt.Rectangle((x, y), w, h, facecolor=face, edgecolor=edge, linewidth=1.25)
        ax.add_patch(rect)
        ax.text(x + 0.02 * w, y + h - 0.12 * h, title, ha="left", va="top", fontsize=9.2, weight="bold", color="#172B3A")
        ax.text(x + 0.02 * w, y + h - 0.34 * h, lines, ha="left", va="top", fontsize=7.8, color="#263746", linespacing=1.25)

    def arrow(start, end, label="", color="#40596B", style="->"):
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle=style, lw=1.25, color=color))
        if label:
            ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.018, label,
                    ha="center", va="bottom", fontsize=7.1, color=color,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.8))

    ax.text(0.50, 0.965, "Dual-state cognitive-affective path reconstruction architecture",
            ha="center", va="center", fontsize=13, weight="bold", color="#172B3A")
    ax.text(0.50, 0.925, "Hard graph constraints delimit feasible path actions; soft state evidence selects the intervention.",
            ha="center", va="center", fontsize=8.5, color="#40596B")

    box(0.04, 0.68, 0.20, 0.18, "1  Evidence and context",
        "Interaction: correctness, latency,\nhelp request, previous feedback\nContext: target, history, resource type", "#EAF1F5")
    box(0.04, 0.42, 0.20, 0.18, "2  Graph-constrained plan",
        "Target path P and current target v_t\nPrerequisite neighbourhood N_G(v_t)\nDifficulty proxy d(v_t)", "#E8F3EE")
    box(0.30, 0.58, 0.22, 0.28, "3  Dual-state estimator",
        "Cognitive state c_t in [0,1]\nAffective state e_t in [0,1]\nMastery m_t and interaction memory h_t\n\nAttribution:\np_cap, p_aff, p_amb", "#F2F5F7")
    box(0.58, 0.58, 0.22, 0.28, "4  Uncertainty-aware policy gate",
        "PASS -> advance on P\nCapability gap -> prerequisite scaffold\nAffective overload -> modality/pacing switch\nAmbiguous evidence -> low-risk probe", "#FFF4E5")
    box(0.84, 0.58, 0.13, 0.28, "5  Action",
        "advance\ndowngrade\nswitch\nprobe\nterminate", "#F7EDEE")
    box(0.58, 0.23, 0.22, 0.23, "6  Learner or simulator response",
        "PASS\nPASS_REMEDIAL / PASS_REST\nFAIL_HARD / FAIL_ANXIOUS\nDROPOUT", "#F2F5F7")
    box(0.30, 0.23, 0.22, 0.23, "7  State and path update",
        "c_(t+1) = clip(c_t + delta_c)\ne_(t+1) = clip(e_t + delta_e)\nRemediation returns to original target\nLog transition and update mastery", "#EAF1F5")
    box(0.04, 0.10, 0.20, 0.22, "Safety and audit layer",
        "Graph legality check\nAnxiety and dropout thresholds\nMaximum-step guard\nUncertainty logging\nHuman review interface", "#F7EDEE", edge="#7A3E48")

    arrow((0.24, 0.77), (0.30, 0.77), "observations")
    arrow((0.24, 0.51), (0.30, 0.64), "feasible set")
    arrow((0.52, 0.72), (0.58, 0.72), "state + attribution")
    arrow((0.80, 0.72), (0.84, 0.72), "selected action")
    arrow((0.905, 0.58), (0.78, 0.45), "interaction")
    arrow((0.58, 0.34), (0.52, 0.34), "typed feedback")
    arrow((0.41, 0.46), (0.41, 0.58), "updated state")
    arrow((0.30, 0.29), (0.24, 0.23), "audit log")
    arrow((0.14, 0.32), (0.14, 0.42), "gates", color="#7A3E48")

    ax.text(0.30, 0.075, "Hard constraints", fontsize=7.6, weight="bold", color="#2F6B56")
    ax.text(0.395, 0.075, "prerequisite legality, target preservation", fontsize=7.5, color="#40596B")
    ax.text(0.66, 0.075, "Soft constraints", fontsize=7.6, weight="bold", color="#A26816")
    ax.text(0.745, 0.075, "anxiety, pacing, modality and confidence", fontsize=7.5, color="#40596B")

    fig.tight_layout(pad=0.5)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_main_outcomes(summary_rows: List[Dict[str, object]], path: Path) -> None:
    rows = [r for r in summary_rows if r.get("strategy") in ["static", "cognitive_only", "fusion"]]
    rows = sorted(rows, key=lambda r: ["static", "cognitive_only", "fusion"].index(r["strategy"]))
    labels = ["Static", "Cognitive-only", "Dual-state"]
    metrics = [
        ("goal_completion", "Goal completion (%)", 1),
        ("final_mastery", "Final mastery (%)", 1),
        ("peak_anxiety", "Peak anxiety", 2),
        ("avg_steps", "Average steps", 1),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), dpi=220)
    axes = axes.flatten()
    colors = ["#8f9aa8", "#6f8fb7", "#2f7d6b"]
    for ax, (metric, title, decimals) in zip(axes, metrics):
        means = [r[f"{metric}_mean"] for r in rows]
        sds = [r[f"{metric}_sd"] for r in rows]
        ax.bar(labels, means, yerr=sds, color=colors, capsize=4)
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis="x", labelrotation=15)
        ax.grid(axis="y", alpha=0.25)
        for i, value in enumerate(means):
            ax.text(i, value, f"{value:.{decimals}f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle("Policy comparison across ten random seeds", fontsize=12, weight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_video_sensitivity(summary_rows: List[Dict[str, object]], path: Path) -> None:
    rows = [r for r in summary_rows if r["strategy"] in ["affective_only", "fusion"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=220)
    labels = {"affective_only": "Affective-only", "fusion": "Dual-state"}
    colors = {"affective_only": "#a85d4f", "fusion": "#2f7d6b"}
    for metric, title, ax in [
        ("goal_completion", "Goal completion (%)", axes[0]),
        ("peak_anxiety", "Peak anxiety", axes[1]),
    ]:
        for strategy in ["affective_only", "fusion"]:
            srows = sorted([r for r in rows if r["strategy"] == strategy], key=lambda r: float(r["video_success_prob"]))
            xs = [float(r["video_success_prob"]) for r in srows]
            ys = [r[f"{metric}_mean"] for r in srows]
            es = [r[f"{metric}_sd"] for r in srows]
            ax.errorbar(xs, ys, yerr=es, marker="o", capsize=4, label=labels[strategy], color=colors[strategy])
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Video-rest success probability")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Outcome")
    axes[1].legend(frameon=False)
    fig.suptitle("Sensitivity to the video-rest assumption", fontsize=12, weight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    kg = KnowledgeGraph(PREREQ_PATH)
    path = kg.generate_path(DEFAULT_START_NODE, PATH_LENGTH, BASE_SEED)
    print("Evaluation path:", " -> ".join(path))

    uniform_generator = lambda seed, n: generate_uniform_students(seed, n)

    main_rows = run_seeded_experiment(
        kg,
        path,
        ["static", "cognitive_only", "fusion"],
        uniform_generator,
        experiment="main",
        n_per_seed=MAIN_STUDENTS_PER_SEED,
        video_success_prob=MAIN_VIDEO_SUCCESS_PROB,
    )

    ablation_rows = run_seeded_experiment(
        kg,
        path,
        ["static", "cognitive_only", "affective_only", "fusion"],
        uniform_generator,
        experiment="ablation",
        n_per_seed=MAIN_STUDENTS_PER_SEED,
        video_success_prob=MAIN_VIDEO_SUCCESS_PROB,
    )

    cohort_specs = {
        "low_ability": (0.35, 0.30),
        "anxiety_prone": (0.60, 0.55),
        "balanced": (0.55, 0.30),
    }
    cohort_rows = []
    for cohort, (ability_mean, anxiety_mean) in cohort_specs.items():
        generator = lambda seed, n, am=ability_mean, xm=anxiety_mean: generate_cohort_students(seed, n, am, xm)
        cohort_rows.extend(
            run_seeded_experiment(
                kg,
                path,
                ["static", "cognitive_only", "fusion"],
                generator,
                experiment="cohort",
                n_per_seed=COHORT_STUDENTS_PER_SEED,
                cohort=cohort,
                video_success_prob=MAIN_VIDEO_SUCCESS_PROB,
            )
        )

    sensitivity_rows = []
    for video_success_prob in [1.00, 0.80, 0.60, 0.40]:
        sensitivity_rows.extend(
            run_seeded_experiment(
                kg,
                path,
                ["affective_only", "fusion"],
                uniform_generator,
                experiment="sensitivity",
                n_per_seed=MAIN_STUDENTS_PER_SEED,
                video_success_prob=video_success_prob,
            )
        )

    tests = []
    tests.extend(paired_tests(main_rows, "main", "static", "fusion"))
    tests.extend(paired_tests(main_rows, "main", "cognitive_only", "fusion"))
    tests.extend(paired_tests(ablation_rows, "ablation", "affective_only", "fusion"))

    write_csv(OUTPUT_DIR / "main_experiment_per_seed.csv", main_rows)
    write_csv(OUTPUT_DIR / "ablation_per_seed.csv", ablation_rows)
    write_csv(OUTPUT_DIR / "cohort_per_seed.csv", cohort_rows)
    write_csv(OUTPUT_DIR / "sensitivity_per_seed.csv", sensitivity_rows)
    write_csv(OUTPUT_DIR / "statistical_tests.csv", tests)

    main_summary = summarize(main_rows, ["strategy"])
    ablation_summary = summarize(ablation_rows, ["strategy"])
    cohort_summary = summarize(cohort_rows, ["cohort", "strategy"])
    sensitivity_summary = summarize(sensitivity_rows, ["video_success_prob", "strategy"])

    summary = {
        "path": path,
        "settings": {
            "base_seed": BASE_SEED,
            "n_seeds": N_SEEDS,
            "main_students_per_seed": MAIN_STUDENTS_PER_SEED,
            "cohort_students_per_seed": COHORT_STUDENTS_PER_SEED,
            "max_steps": MAX_STEPS,
            "main_video_success_prob": MAIN_VIDEO_SUCCESS_PROB,
            "prerequisite_graph_nodes": kg.graph.number_of_nodes(),
            "prerequisite_graph_edges": kg.graph.number_of_edges(),
        },
        "main": main_summary,
        "ablation": ablation_summary,
        "cohort": cohort_summary,
        "sensitivity": sensitivity_summary,
        "tests": tests,
    }
    with (OUTPUT_DIR / "experiment_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    plot_framework(OUTPUT_DIR / "figure1_dual_state_framework.png")
    plot_main_outcomes(main_summary, OUTPUT_DIR / "figure2_main_outcomes.png")
    plot_video_sensitivity(sensitivity_summary, OUTPUT_DIR / "figure3_video_sensitivity.png")

    print("\nMain experiment summary")
    for row in sorted(main_summary, key=lambda r: ["static", "cognitive_only", "fusion"].index(r["strategy"])):
        print(
            row["strategy"],
            format_mean_sd(row["goal_completion_mean"], row["goal_completion_sd"]),
            format_mean_sd(row["final_mastery_mean"], row["final_mastery_sd"]),
            f"{row['peak_anxiety_mean']:.2f} ± {row['peak_anxiety_sd']:.2f}",
            format_mean_sd(row["avg_steps_mean"], row["avg_steps_sd"]),
        )
    print(f"\nOutputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
