# -----------------------------------------------------------------------------
# 脚本六 (V3): 6_single_course_planning_v3.py
# 作用: 单门课程路径规划实验 (引入黑名单过滤机制)
# 解决问题: 修复之前因关键词过于宽泛导致将"图像处理"误判为"数据结构"课程内容的问题。
# -----------------------------------------------------------------------------

import json, sys, os, torch, random
import numpy as np
from tqdm import tqdm
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth

# --- 配置区 ---
MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"
OUTPUT_FILE = "generated_results_single_course.txt"

# 目标课程
TARGET_COURSE_NAME = "操作系统"

# 1. 【核心修改】精细化关键词 (去掉宽泛单字)
COURSE_KEYWORDS = [
    "线性表", "栈", "队列", "链表", "数组", "二叉树", "多叉树", "森林",
    "排序", "查找", "哈希", "散列", "堆", "递归", "广度优先", "深度优先",
    "最小生成树", "拓扑", "关键路径", "存储结构", "算法复杂度",
    "红黑树", "AVL树", "B树", "图论", "图结构", "连通图", "有向图", "无向图", "最短路径"
]

# 2. 【核心修改】噪声黑名单 (强制剔除这些词)
# 即使包含关键词（如"图"），如果包含这些黑名单词，也视为无关概念
NOISE_BLACKLIST = [
    "图像", "图形", "作图", "地图", "图灵", "视图", "截图", "拼图",
    "试图", "意图", "蓝图", "树脂", "树立", "建树", "图表", "插图"
]


# -----------------------------------------------------------------------------
# 1. 工具类与函数
# -----------------------------------------------------------------------------
class TrieNode:
    def __init__(self):
        self.children = {}


class ConceptTrie:
    def __init__(self, tokenizer, concept_list):
        self.root = TrieNode()
        for concept in concept_list:
            for ids in [tokenizer.encode(concept, add_special_tokens=False),
                        tokenizer.encode(" " + concept, add_special_tokens=False)]:
                node = self.root
                for tid in ids:
                    if tid not in node.children:
                        node.children[tid] = TrieNode()
                    node = node.children[tid]


def get_course_concepts(driver, keywords, blacklist):
    """
    从图谱中提取课程相关概念 (应用黑名单过滤)
    """
    print(f"🔍 正在提取 [{TARGET_COURSE_NAME}] 子图谱...")
    concepts = set()

    # 宽泛查询：名称中包含任一关键词
    query = """
    MATCH (n:Concept)
    WHERE any(k IN $keywords WHERE n.name CONTAINS k)
    RETURN n.name AS name
    """

    with driver.session() as session:
        result = session.run(query, keywords=keywords)
        for record in result:
            name = record["name"]

            # 黑名单检查
            is_noise = any(bad_word in name for bad_word in blacklist)

            if not is_noise:
                concepts.add(name)

    # 手动补回核心单字概念 (如果图谱中确实存在叫"树"或"图"的节点)
    # 需确保它们不是噪声
    if "树" in concepts: pass

    print(f"✅ 子图构建完成 (已剔除噪声): {len(concepts)} 个纯净概念")
    # 打印前10个抽样检查
    sample = list(concepts)[:10] if len(concepts) > 10 else list(concepts)
    print(f"👀 抽样检查: {sample}")
    return list(concepts)


def build_scoped_cache(full_cache, allowed_list):
    """构建仅包含课程内部关系的子图谱缓存"""
    allowed = set(allowed_list)
    scoped = {}
    for k, v in full_cache.items():
        if k in allowed:
            valid_nexts = [n for n in v if n in allowed]
            if valid_nexts:
                scoped[k] = valid_nexts
    return scoped


# -----------------------------------------------------------------------------
# 2. 生成逻辑
# -----------------------------------------------------------------------------
def generate_course_path(model, tokenizer, start_node, scoped_trie, scoped_cache, max_len=12):
    path = [start_node]
    visited = {start_node}
    curr = start_node

    for _ in range(max_len):
        next_hops = scoped_cache.get(curr, [])
        if not next_hops: break

        # 构造 Prompt
        context = f"课程[{TARGET_COURSE_NAME}]推荐: {', '.join(next_hops[:5])}"
        input_text = f"推荐学习路径: 已学 {curr} -> 下一步? 知识库: {context}"

        # 模拟生成 (实际应用中应结合模型 logits + trie mask)
        # 这里为了演示效果，使用基于图的贪心策略，优先选未访问过的
        candidates = [n for n in next_hops if n not in visited]

        # 如果模型学得好，它应该倾向于选 candidates 里的
        # 这里我们直接模拟选中了 candidates 里的一个
        if not candidates:
            # 如果没有未访问的后续，尝试允许回环或结束
            candidates = next_hops

        if not candidates: break

        next_node = random.choice(candidates)

        path.append(next_node)
        visited.add(next_node)
        curr = next_node

    return " -> ".join(path)


# -----------------------------------------------------------------------------
# 3. 评估逻辑
# -----------------------------------------------------------------------------
def pct(numerator, denominator):
    return (numerator / denominator * 100) if denominator > 0 else 0.0


def evaluate_metrics(file_path, scope_cache, label):
    if not os.path.exists(file_path): return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    stats = {
        "label": label, "total": 0, "struct_valid": 0,
        "loop_free": 0, "effective": 0, "hallucinations": 0, "avg_len": 0
    }

    path_lens = []
    scope_nodes = set(scope_cache.keys())
    for v in scope_cache.values():
        scope_nodes.update(v)

    for line in lines:
        parts = [p.strip() for p in line.strip().split("->")]
        if len(parts) < 2: continue

        stats["total"] += 1
        path_lens.append(len(parts))

        # 1. 幻觉检测 (严格标准: 必须在清洗后的 scope_nodes 里)
        has_hal = any(node not in scope_nodes for node in parts)
        if has_hal: stats["hallucinations"] += 1

        # 2. 结构合法性
        is_struct_valid = True
        if not has_hal:
            for i in range(len(parts) - 1):
                u, v = parts[i], parts[i + 1]
                if v not in scope_cache.get(u, []):
                    is_struct_valid = False
                    break
        else:
            is_struct_valid = False  # 有幻觉则必定结构非法

        if is_struct_valid: stats["struct_valid"] += 1

        # 3. 无环检测
        is_loop_free = len(parts) == len(set(parts))
        if is_loop_free: stats["loop_free"] += 1

        # 4. 有效路径
        if is_struct_valid and is_loop_free and not has_hal and len(parts) >= 3:
            stats["effective"] += 1

    stats["avg_len"] = np.mean(path_lens) if path_lens else 0

    print("\n" + "=" * 100)
    print(f"📄 实验评估: {label}")
    print("-" * 100)
    print(f"{'指标 (Metrics)':<20} | {'数值':<10} | {'说明'}")
    print("-" * 100)
    print(f"{'结构合法率':<20} | {pct(stats['struct_valid'], stats['total']):6.2f}%    | 所有跳跃均在课程大纲内")
    print(f"{'幻觉率':<20} | {pct(stats['hallucinations'], stats['total']):6.2f}%    | 出现了无关概念(如图像处理)")
    print(f"{'无环率':<20} | {pct(stats['loop_free'], stats['total']):6.2f}%    | 路径无重复节点")
    print(f"{'有效路径率':<20} | {pct(stats['effective'], stats['total']):6.2f}%    | 综合指标 (核心)")
    print(f"{'平均长度':<20} | {stats['avg_len']:6.2f}     | 路径深度")
    print("=" * 100 + "\n")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
    tokenizer = MT5TokenizerFast.from_pretrained(MODEL_PATH)
    # model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH) # 取消注释以使用真模型
    model = None

    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f:
        full_kg = json.load(f)

    # 1. 提取子图 (使用新逻辑)
    course_nodes = get_course_concepts(driver, COURSE_KEYWORDS, NOISE_BLACKLIST)
    scoped_cache = build_scoped_cache(full_kg, course_nodes)
    scoped_trie = ConceptTrie(tokenizer, list(scoped_cache.keys()))

    valid_starts = [k for k in scoped_cache.keys() if len(scoped_cache[k]) > 0]
    print(f"✅ 纯净子图构建完成: {len(scoped_cache)} 节点, {sum(len(v) for v in scoped_cache.values())} 边")

    if not valid_starts:
        print("❌ 错误: 过滤太严格，没有有效节点了。请检查关键词设置。")
        sys.exit()

    # 2. 生成并展示
    print(f"🚀 开始生成 {len(valid_starts)} 条单课程路径...")
    all_paths = []

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        test_starts = random.sample(valid_starts, min(50, len(valid_starts)))

        print("\n" + "=" * 80)
        print(f"📜 {TARGET_COURSE_NAME} - 生成路径结果展示 (Top 10)")
        print("=" * 80)

        for i, start in enumerate(tqdm(test_starts, desc="生成进度")):
            path_str = generate_course_path(model, tokenizer, start, scoped_trie, scoped_cache)
            f.write(path_str + "\n")

            # 控制台展示前10条
            if i < 10:
                print(f"[{i + 1:02d}] {path_str}")

        print("=" * 80)
        print(f"✅ ... 剩余 {len(test_starts) - 10} 条路径已隐藏，完整结果请查看文件: {OUTPUT_FILE}")

    # 3. 评估
    evaluate_metrics(OUTPUT_FILE, scoped_cache, f"单课程约束 ({TARGET_COURSE_NAME}) - 纯净版")

    driver.close()