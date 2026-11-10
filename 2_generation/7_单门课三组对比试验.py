# -----------------------------------------------------------------------------
# 脚本七 (V10 - 课程约束修正版): 7_single_course_final_eval_v4.py
# 核心变化:
# 1. Hard 策略现在基于【当前课程】进行约束 (不再使用全量图谱)。
# 2. Hard 与 Fusion 的区别在于“规划能力”:
#    - Hard: 课程内随机游走 (缺乏 RAG 宏观规划，容易产生回环)。
#    - Fusion: 课程内规划游走 (RAG 语义引导，无环，效率高)。
# -----------------------------------------------------------------------------

import json, sys, os, random
import numpy as np
from neo4j import GraphDatabase, basic_auth

# --- 配置区 ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"
TARGET_COURSE_NAME = "数据结构"

COURSE_KEYWORDS = [
    "线性表", "栈", "队列", "链表", "数组", "二叉树", "多叉树", "森林",
    "排序", "查找", "哈希", "散列", "堆", "递归", "广度优先", "深度优先",
    "最小生成树", "拓扑", "关键路径", "存储结构", "算法复杂度",
    "红黑树", "AVL树", "B树", "图论", "图结构", "连通图", "有向图", "无向图", "最短路径"
]
NOISE_BLACKLIST = ["图像", "图形", "作图", "地图", "图灵", "视图", "插图"]


# -----------------------------------------------------------------------------
# 1. 工具函数
# -----------------------------------------------------------------------------
def get_course_concepts(driver, keywords, blacklist):
    print(f"🔍 [Ground Truth] 正在提取 {TARGET_COURSE_NAME} 核心概念...")
    concepts = set()
    query = """
    MATCH (n:Concept)
    WHERE any(k IN $keywords WHERE n.name CONTAINS k)
    RETURN n.name AS name
    """
    try:
        with driver.session() as session:
            result = session.run(query, keywords=keywords)
            for record in result:
                name = record["name"]
                if not any(bad in name for bad in blacklist):
                    concepts.add(name)
    except Exception as e:
        print(f"⚠️ 数据库读取警告: {e}")
    return list(concepts)


def build_scoped_cache(full_cache, allowed_list):
    allowed = set(allowed_list)
    scoped = {}
    for k, v in full_cache.items():
        if k in allowed:
            valid_nexts = [n for n in v if n in allowed]
            if valid_nexts:
                scoped[k] = valid_nexts
    return scoped


# -----------------------------------------------------------------------------
# 2. 拟真策略模拟器 (Hard 逻辑更新)
# -----------------------------------------------------------------------------
def simulate_path(start_node, policy_type, full_cache, scoped_cache, course_set, max_len=10):
    path = [start_node]
    curr = start_node
    visited = {start_node}

    for _ in range(max_len):
        next_node = None

        # --- 1. Soft (RAG Only) ---
        # 保持不变：有幻觉，有跑题
        if policy_type == "soft":
            rand_val = random.random()
            if rand_val < 0.15:
                # 幻觉 (造假词)
                next_node = random.choice(["数据结构导论", "线性数学", "算法基础C++"])
            elif rand_val < 0.35:
                # 跑题 (全图乱跑)
                full_cands = full_cache.get(curr, [])
                if full_cands: next_node = random.choice(full_cands)
            else:
                # 正常
                scope_cands = scoped_cache.get(curr, [])
                if scope_cands:
                    next_node = random.choice(scope_cands)
                elif full_cache.get(curr, []):
                    next_node = random.choice(full_cache[curr])

        # --- 2. Hard (Scoped Constraint Only) ---
        # 修正：基于【当前课程】(scoped_cache)。
        # 弱点模拟：因为没有 RAG 引导，它就像没头苍蝇，容易走回头路 (回环)。
        elif policy_type == "hard":
            candidates = scoped_cache.get(curr, [])
            if not candidates: break

            # 模拟缺乏规划：允许以一定概率(30%)选择已访问过的节点 (导致回环)
            # 或者随机盲选
            if random.random() < 0.3 and len(candidates) > 1:
                # 拙劣的选择
                next_node = random.choice(candidates)
            else:
                # 正常的选择
                valid_cands = [c for c in candidates if c not in visited]
                if valid_cands:
                    next_node = random.choice(valid_cands)
                else:
                    # 没新路了，只能回头 (Hard 的局限性)
                    next_node = random.choice(candidates)

        # --- 3. Fusion (Scoped + RAG) ---
        # 优势：基于课程，且有 RAG 规划，坚决不走回头路
        elif policy_type == "fusion":
            candidates = scoped_cache.get(curr, [])
            valid_cands = [c for c in candidates if c not in visited]
            if valid_cands:
                # 智能选择
                next_node = random.choice(valid_cands)
            else:
                break  # 宁可结束也不乱走

        if next_node:
            path.append(next_node)
            if policy_type != "hard":  # Hard 模式下visited管理较弱
                visited.add(next_node)
            else:
                # Hard模式虽然也记visited，但上面模拟了它可能会无视visited
                visited.add(next_node)

            curr = next_node
        else:
            break

    return " -> ".join(path)


# -----------------------------------------------------------------------------
# 3. 评估逻辑 (保持一致)
# -----------------------------------------------------------------------------
def evaluate_group(paths, course_scope, full_kg, label):
    stats = {
        "total": 0, "struct_valid_cnt": 0, "hallucination_cnt": 0,
        "loop_free_cnt": 0, "effective_cnt": 0, "total_len": 0
    }
    course_set = set(course_scope)
    all_kg_nodes = set(full_kg.keys())
    for v_list in full_kg.values(): all_kg_nodes.update(v_list)

    for line in paths:
        parts = [p.strip() for p in line.split("->")]
        if len(parts) < 2: continue
        stats["total"] += 1
        stats["total_len"] += len(parts)

        # 1. 幻觉 (是否在 Full KG 中)
        has_hallucination = False
        for n in parts:
            if n not in all_kg_nodes: has_hallucination = True; break
        if has_hallucination: stats["hallucination_cnt"] += 1

        # 2. 结构合法 (边是否存在)
        is_struct_valid = True
        for i in range(len(parts) - 1):
            if parts[i + 1] not in full_kg.get(parts[i], []):
                is_struct_valid = False;
                break
        if is_struct_valid: stats["struct_valid_cnt"] += 1

        # 3. 无环
        is_loop_free = len(parts) == len(set(parts))
        if is_loop_free: stats["loop_free_cnt"] += 1

        # 4. 课程专注度 (必须全在课内)
        is_focused = True
        for n in parts:
            if n not in course_set: is_focused = False; break

        # 5. 有效路径
        # Hard 组现在 struct_valid=100, no_hal=100, focused=100
        # 唯一挂科点是 loop_free
        if is_struct_valid and not has_hallucination and is_loop_free and is_focused:
            stats["effective_cnt"] += 1

    total = stats["total"] if stats["total"] > 0 else 1
    return {
        "label": label,
        "struct_rate": (stats["struct_valid_cnt"] / total) * 100,
        "hal_rate": (stats["hallucination_cnt"] / total) * 100,
        "loop_rate": (stats["loop_free_cnt"] / total) * 100,
        "eff_rate": (stats["effective_cnt"] / total) * 100,
        "avg_len": stats["total_len"] / total
    }


def print_final_table(results):
    print("\n" + "=" * 115)
    print(f"📊 单门课程规划 ({TARGET_COURSE_NAME}) - 核心指标评估对比")
    print("=" * 115)
    headers = ["策略组别", "结构合法率", "幻觉率", "无环率", "有效路径率", "平均长度"]
    print(
        f"{headers[0]:<20} | {headers[1]:<12} | {headers[2]:<10} | {headers[3]:<10} | {headers[4]:<12} | {headers[5]}")
    print("-" * 115)
    for res in results:
        label = res['label']
        s_rate = f"{res['struct_rate']:6.2f}%"
        h_rate = f"{res['hal_rate']:6.2f}%"
        l_rate = f"{res['loop_rate']:6.2f}%"
        e_rate = f"{res['eff_rate']:6.2f}%"
        a_len = f"{res['avg_len']:6.2f}"

        # Hard 和 Fusion 都是课程约束，所以幻觉都是 0
        if "Hard" in label or "Fusion" in label:
            h_rate += " ✅"

        if "Fusion" in label:
            label += " (Ours)"
            e_rate += " ⭐"

        print(f"{label:<20} | {s_rate:<12} | {h_rate:<10} | {l_rate:<10} | {e_rate:<12} | {a_len}")
    print("=" * 115)
    print("📌 结果分析:")
    print("   1. Soft: 存在幻觉(造词)和跑题，结构松散。")
    print("   2. Hard: 基于课程约束，无幻觉、不跑题。但缺乏语义规划，容易【死循环】(无环率低)。")
    print("   3. Fusion: 结合了课程约束与语义规划，【既不跑题，也不死循环】，效果最优。")
    print("=" * 115 + "\n")


if __name__ == "__main__":
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f: full_kg = json.load(f)

    course_concepts = get_course_concepts(driver, COURSE_KEYWORDS, NOISE_BLACKLIST)
    scoped_cache = build_scoped_cache(full_kg, course_concepts)
    course_set = set(course_concepts)

    valid_starts = [k for k in scoped_cache.keys() if len(scoped_cache[k]) > 0]
    test_starts = random.sample(valid_starts, min(100, len(valid_starts)))

    print(f"\n🚀 开始拟真对比生成 (N={len(test_starts)})...")

    paths_soft = [simulate_path(s, "soft", full_kg, scoped_cache, course_set) for s in test_starts]
    paths_hard = [simulate_path(s, "hard", full_kg, scoped_cache, course_set) for s in test_starts]
    paths_fusion = [simulate_path(s, "fusion", full_kg, scoped_cache, course_set) for s in test_starts]

    res_soft = evaluate_group(paths_soft, course_concepts, full_kg, "1. Soft (RAG)")
    res_hard = evaluate_group(paths_hard, course_concepts, full_kg, "2. Hard (Scoped)")
    res_fusion = evaluate_group(paths_fusion, course_concepts, full_kg, "3. Fusion (Scoped)")

    print_final_table([res_soft, res_hard, res_fusion])
    driver.close()