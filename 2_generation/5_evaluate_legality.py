# -----------------------------------------------------------------------------
# 【评估脚本 5: 5_evaluate_legality.py】 (多维对比终极版)
# 核心功能：批量评估 Baseline, Ablation, Fusion 三组实验，并生成论文 Table 1
# -----------------------------------------------------------------------------
import json
import os

# ================= 配置区 =================
# 图谱缓存文件
KG_CACHE_FILE = "kg_transition_cache.json"

# 论文设定的 EPR 有效路径最小长度阈值
MIN_EFFECTIVE_LENGTH = 4

# 【核心修改】配置你要对比的三个实验结果文件
# 提示：你需要先运行三次生成脚本，分别保存为这三个名字
EVAL_FILES = {
    "Baseline (Soft)": "generated_results_soft.txt",
    "Ablation (Hard Only)": "generated_results_hard.txt",
    "Ours (Fusion)": "generated_results_fusion_final.txt"
}


def load_graph_data(cache_file):
    print(f"📂 正在加载图谱缓存: {cache_file}")
    with open(cache_file, "r", encoding="utf-8") as f:
        kg_cache = json.load(f)

    entity_set = set(kg_cache.keys())
    for targets in kg_cache.values():
        entity_set.update(targets)

    return kg_cache, entity_set


def evaluate_single_file(file_path, kg_cache, entity_set):
    """评估单个文件并返回各项指标"""
    if not os.path.exists(file_path):
        return None  # 文件不存在返回 None

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    total_paths = len(lines)
    if total_paths == 0:
        return None

    total_sl, total_hr, total_al = 0.0, 0.0, 0.0
    loop_free_count, effective_path_count = 0, 0

    for line in lines:
        nodes = [n.strip() for n in line.split("->") if n.strip()]
        path_length = len(nodes)
        if path_length < 2: continue

        # 1. 幻觉率 (HR)
        hallucination_nodes = [n for n in nodes if n not in entity_set]
        hr_score = len(hallucination_nodes) / path_length
        total_hr += hr_score

        # 2. 结构合法率 (SL)
        legal_edges = 0
        total_edges = path_length - 1
        for i in range(total_edges):
            src, tgt = nodes[i], nodes[i + 1]
            if src in kg_cache and tgt in kg_cache[src]:
                legal_edges += 1

        sl_score = legal_edges / total_edges if total_edges > 0 else 0
        total_sl += sl_score

        # 3. 无环率 (LR)
        is_loop_free = (len(set(nodes)) == path_length)
        if is_loop_free: loop_free_count += 1

        # 4. 平均长度 (AL)
        total_al += path_length

        # 5. 有效路径率 (EPR)
        if sl_score == 1.0 and hr_score == 0.0 and is_loop_free and path_length >= MIN_EFFECTIVE_LENGTH:
            effective_path_count += 1

    # 返回计算结果 (百分比和浮点数)
    return {
        "SL": (total_sl / total_paths) * 100,
        "HR": (total_hr / total_paths) * 100,
        "LR": (loop_free_count / total_paths) * 100,
        "EPR": (effective_path_count / total_paths) * 100,
        "AL": total_al / total_paths
    }


if __name__ == "__main__":
    kg_cache, entity_set = load_graph_data(KG_CACHE_FILE)

    print("\n" + "=" * 85)
    print(
        f"{'实验组别 (Method)':<22} | {'结构合法率(SL)':<14} | {'幻觉率(HR)':<10} | {'无环率(LR)':<10} | {'有效路径率(EPR)':<14} | {'平均长度(AL)'}")
    print("-" * 85)

    # 批量评估并打印表格
    for method_name, file_path in EVAL_FILES.items():
        results = evaluate_single_file(file_path, kg_cache, entity_set)

        if results:
            print(
                f"{method_name:<24} | {results['SL']:>10.2f}%    | {results['HR']:>7.2f}%   | {results['LR']:>7.2f}%   | {results['EPR']:>11.2f}%    | {results['AL']:>7.2f}")
        else:
            print(f"{method_name:<24} | {'[文件未找到或为空，请先运行生成脚本]':<60}")

    print("=" * 85)
    print("💡 提示: 上述输出已完全对齐论文的 Table 1 格式，可直接复制使用。")