# -----------------------------------------------------------------------------
# 脚本十二：12_ablation_repetition_penalty.py
# 作用 (Role): 回应审稿意见9——对动态重复惩罚系数 λ (repetition_penalty) 进行消融实验，
#              对比 λ ∈ {1.0, 2.0, 2.5, 3.0} 时【无环率 LR】与【平均路径长度 AL】的变化，
#              用于论证正文 3.1.2 节 λ=2.5 取值的合理性。
#              建议将结果表插入 3.4 节表3下方，作为新增的"防环惩罚系数消融实验结果表"。
#
# 实验设计:
#   固定 Beam Size=5（论文正式取值），仅改变 repetition_penalty，
#   在同一批起点上分别生成路径，评估 SL/LR/EPR/AL。
#
# 运行前请确认:
#   - MODEL_PATH 指向你训练好的 T5-small 权重目录
#   - Neo4j 服务已启动，且 kg_transition_cache.json 已由脚本一生成
# -----------------------------------------------------------------------------
import os
import json, csv, random
import torch
from tqdm import tqdm
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth

# ================= 配置区 =================
MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"

PENALTY_VALUES = [1.0, 2.0, 2.5, 3.0]   # 待对比的防环惩罚系数 λ
FIXED_BEAM_SIZE = 5                     # 固定为论文正式取值，隔离 λ 这一单一自变量
SAMPLE_SIZE = 30
MAX_STEPS = 20
MIN_EFFECTIVE_LENGTH = 4
RANDOM_SEED = 42
OUTPUT_CSV = "repetition_penalty_ablation_results.csv"
FIXED_PERSONA = "学习能力中等, 偏好循序渐进的引导"


# ---- Trie 硬约束（与脚本十一完全一致）----
class TrieNode:
    def __init__(self):
        self.children, self.is_end = {}, False


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
                node.is_end = True


def get_constraint_fn(tokenizer, valid_concepts):
    if not valid_concepts:
        return None
    trie = ConceptTrie(tokenizer, valid_concepts)
    ignore_ids = {tokenizer.pad_token_id, tokenizer.eos_token_id, 0}

    def prefix_allowed_tokens_fn(batch_id, sent_input_ids):
        gen_tokens = [t for t in sent_input_ids.tolist() if t != 0]
        node = trie.root
        for token in gen_tokens:
            if token in ignore_ids:
                continue
            if token in node.children:
                node = node.children[token]
            else:
                return [tokenizer.eos_token_id]
        allowed = list(node.children.keys())
        if node.is_end:
            allowed.append(tokenizer.eos_token_id)
        return allowed if allowed else [tokenizer.eos_token_id]

    return prefix_allowed_tokens_fn


def get_valid_and_context(driver, current_node):
    query = """
    MATCH (curr:Concept {name: $name})-[r]->(next:Concept)
    WHERE type(r) CONTAINS 'PREREQUISITE' OR type(r) CONTAINS 'prerequisite'
    OPTIONAL MATCH (next)-[out_r]->()
    RETURN next.name AS name, count(out_r) AS out_degree
    ORDER BY out_degree DESC
    LIMIT 20
    """
    try:
        with driver.session() as session:
            nexts = [record["name"] for record in session.run(query, name=current_node)]
            return nexts, ", ".join(nexts[:5]) if nexts else "无"
    except Exception as e:
        print(f"Graph Query Error: {e}")
        return [], "无"


def construct_prompt(path_history, rag_context, step_num, total_steps):
    history_str = " -> ".join(path_history)
    current_concept = path_history[-1]
    return (
        f"任务: 个性化连贯学习路径规划\n"
        f"学生画像: {FIXED_PERSONA}\n"
        f"已学轨迹: {history_str} (进度: {step_num}/{total_steps}步)\n"
        f"当前起点: {current_concept}\n"
        f"合法候选集: [{rag_context}]\n"
        f"指令: 请结合学生的个性化画像与已学的语义上下文，从合法候选集中选择最适合、最连贯且未访问过的下一个知识点。\n"
        f"下一个概念是:"
    )


def generate_fusion_path(model, tokenizer, driver, start_node, repetition_penalty, max_steps=MAX_STEPS):
    current_node = start_node
    path_list = [start_node]
    visited = {start_node}

    for step in range(max_steps):
        valid_nexts, rag_context = get_valid_and_context(driver, current_node)
        if not valid_nexts:
            break
        unvisited_nexts = [n for n in valid_nexts if n not in visited]
        if not unvisited_nexts:
            break

        constraint_fn = get_constraint_fn(tokenizer, unvisited_nexts)
        prompt = construct_prompt(path_list, rag_context, step + 1, max_steps)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        try:
            outputs = model.generate(
                **inputs,
                max_length=20,
                num_beams=FIXED_BEAM_SIZE,
                num_return_sequences=1,
                repetition_penalty=repetition_penalty,
                early_stopping=True,
                prefix_allowed_tokens_fn=constraint_fn
            )
            next_concept = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            if next_concept in unvisited_nexts:
                path_list.append(next_concept)
                visited.add(next_concept)
                current_node = next_concept
            else:
                break
        except Exception as e:
            print(f"Generation interrupted: {e}")
            break

    return " -> ".join(path_list)


def evaluate_paths(path_list_strs, kg_cache, entity_set, min_len=MIN_EFFECTIVE_LENGTH):
    total_paths = len(path_list_strs)
    if total_paths == 0:
        return None
    total_sl, total_hr, total_al = 0.0, 0.0, 0.0
    loop_free_count, effective_path_count = 0, 0

    for line in path_list_strs:
        nodes = [n.strip() for n in line.split("->") if n.strip()]
        path_length = len(nodes)
        if path_length < 2:
            continue
        hallucination_nodes = [n for n in nodes if n not in entity_set]
        hr_score = len(hallucination_nodes) / path_length
        total_hr += hr_score

        legal_edges, total_edges = 0, path_length - 1
        for i in range(total_edges):
            src, tgt = nodes[i], nodes[i + 1]
            if src in kg_cache and tgt in kg_cache[src]:
                legal_edges += 1
        sl_score = legal_edges / total_edges if total_edges > 0 else 0
        total_sl += sl_score

        is_loop_free = (len(set(nodes)) == path_length)
        if is_loop_free:
            loop_free_count += 1
        total_al += path_length

        if sl_score == 1.0 and hr_score == 0.0 and is_loop_free and path_length >= min_len:
            effective_path_count += 1

    return {
        "SL": (total_sl / total_paths) * 100,
        "HR": (total_hr / total_paths) * 100,
        "LR": (loop_free_count / total_paths) * 100,
        "EPR": (effective_path_count / total_paths) * 100,
        "AL": total_al / total_paths,
    }


if __name__ == "__main__":
    print("⏳ 加载模型与图谱缓存...")
    tokenizer = MT5TokenizerFast.from_pretrained(MODEL_PATH)
    model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f:
        kg_cache = json.load(f)
    entity_set = set(kg_cache.keys())
    for targets in kg_cache.values():
        entity_set.update(targets)

    valid_starts = [k for k, v in kg_cache.items() if len(v) > 2]
    random.seed(RANDOM_SEED)
    test_starts = random.sample(valid_starts, min(SAMPLE_SIZE, len(valid_starts)))
    print(f"✅ 已固定 {len(test_starts)} 个起点，将在全部 λ 设置下复用，确保对比公平。")

    results_table = []
    for lam in PENALTY_VALUES:
        print(f"\n🚀 正在评估 防环惩罚系数 λ = {lam} ...")
        torch.manual_seed(RANDOM_SEED)
        generated_paths = []
        for start in tqdm(test_starts, desc=f"lambda={lam}"):
            path = generate_fusion_path(model, tokenizer, driver, start, lam)
            if path.count("->") >= 1:
                generated_paths.append(path)

        metrics = evaluate_paths(generated_paths, kg_cache, entity_set)
        results_table.append({
            "Lambda": lam,
            "SL(%)": round(metrics["SL"], 2) if metrics else 0,
            "LR(%)": round(metrics["LR"], 2) if metrics else 0,
            "EPR(%)": round(metrics["EPR"], 2) if metrics else 0,
            "AL": round(metrics["AL"], 2) if metrics else 0,
        })

    print("\n" + "=" * 90)
    print("📊 不同防环惩罚系数 λ 下 无环率(LR) / 平均路径长度(AL) 对比表（3.4节 表3 下新增表）")
    print("=" * 90)
    print(f"{'λ':<8} | {'SL(%)':<8} | {'LR(%)':<8} | {'EPR(%)':<8} | {'AL'}")
    print("-" * 90)
    for row in results_table:
        print(f"{row['Lambda']:<8} | {row['SL(%)']:<8} | {row['LR(%)']:<8} | {row['EPR(%)']:<8} | {row['AL']}")
    print("=" * 90)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results_table[0].keys()))
        writer.writeheader()
        writer.writerows(results_table)
    print(f"💾 结果已保存至 {OUTPUT_CSV}。")

    driver.close()