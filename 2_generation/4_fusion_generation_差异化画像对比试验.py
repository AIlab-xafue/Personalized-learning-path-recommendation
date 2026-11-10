import json, sys, os, torch, random
from tqdm import tqdm
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth

MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE, OUTPUT_FILE = "kg_transition_cache.json", "generated_results_fusion.txt"
SAMPLE_SIZE = 747


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
                    if tid not in node.children: node.children[tid] = TrieNode()
                    node = node.children[tid]
                node.is_end = True


def get_constraint_fn(tokenizer, valid_concepts):
    if not valid_concepts: return None
    trie = ConceptTrie(tokenizer, valid_concepts)
    ignore_ids = {tokenizer.pad_token_id, tokenizer.eos_token_id, 0}

    def prefix_allowed_tokens_fn(batch_id, sent_input_ids):
        gen_tokens = [t for t in sent_input_ids.tolist() if t != 0]
        node = trie.root
        for token in gen_tokens:
            if token in ignore_ids: continue
            if token in node.children:
                node = node.children[token]
            else:
                return [tokenizer.eos_token_id]
        allowed = list(node.children.keys())
        if node.is_end: allowed.append(tokenizer.eos_token_id)
        return allowed if allowed else [tokenizer.eos_token_id]

    return prefix_allowed_tokens_fn


def get_valid_and_context(driver, current_node):
    """同时获取硬约束和软约束信息"""
    query = """
    MATCH (curr:Concept {name: $name})-[r]->(next:Concept)
    WHERE type(r) CONTAINS 'PREREQUISITE' OR type(r) CONTAINS 'prerequisite'
    RETURN DISTINCT next.name AS name LIMIT 20
    """
    try:
        with driver.session() as session:
            nexts = [record["name"] for record in session.run(query, name=current_node)]
            return nexts, ", ".join(nexts[:5]) if nexts else "无"
    except:
        return [], "无"


def construct_enhanced_prompt(current_concept, rag_context, step_num, total_steps):
    """增强的Prompt，提供更多上下文"""
    return (
        f"任务: 学习路径规划\n"
        f"当前状态: {current_concept} (第{step_num}/{total_steps}步)\n"
        f"学生画像: 偏好视频资源, 循序渐进学习\n"
        f"推荐方向: {rag_context}\n"
        f"注意: 请选择一个新的、未访问过的概念\n"
        f"指令: 下一个概念是:"
    )


def generate_fusion_path(model, tokenizer, driver, start_node, known_concepts=None, user_pref="", max_steps=20):
    """修改后的生成逻辑，支持个性化参数
    :param known_concepts: 用户的已知概念集合 (set)，用于跳过基础
    :param user_pref: 用户偏好描述，拼接到 Prompt 中"""
    # 1. 初始化 Visited 集合：加入起点 + 已知知识 (关键修改!)
    if known_concepts is None: known_concepts = set()
    visited = {start_node} | known_concepts

    current_node = start_node
    path_list = [start_node]

    for step in range(max_steps):
        # 获取硬约束和软约束
        valid_nexts, rag_context = get_valid_and_context(driver, current_node)
        if not valid_nexts: break

        # 过滤掉已访问的节点（强化防循环）
        unvisited_nexts = [n for n in valid_nexts if n not in visited]
        if not unvisited_nexts: break  # 所有后继都访问过了

        # 硬约束准备
        constraint_fn = get_constraint_fn(tokenizer, unvisited_nexts)

        # ... (构建 Prompt 的代码微调) ...
        # 在 Prompt 中注入用户偏好
        prompt = (
            f"任务: 学习路径规划\n"
            f"当前: {current_node} (第{step + 1}步)\n"
            f"画像: {user_pref}\n"  # <--- 注入偏好
            f"参考: {rag_context}\n"
            f"指令: 下一个概念是:"
        )

        inputs = tokenizer(prompt, return_tensors="pt")

        try:
            # 优化的采样参数：平衡多样性和质量
            outputs = model.generate(
                **inputs,
                max_length=20,
                do_sample=True,
                top_k=30,  # 降低top_k，提高质量
                top_p=0.85,  # 添加nucleus sampling
                temperature=0.7,  # 适中温度
                repetition_penalty=2.5,  # 提高重复惩罚
                num_return_sequences=1,
                prefix_allowed_tokens_fn=constraint_fn
            )
            next_concept = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

            # 多重验证
            if next_concept in unvisited_nexts and next_concept not in visited:
                path_list.append(next_concept)
                visited.add(next_concept)
                current_node = next_concept
            else:
                break
        except:
            break

    return " -> ".join(path_list)


if __name__ == "__main__":
    print(f"⏳ [Case Study] 加载模型...")
    tokenizer = MT5TokenizerFast.from_pretrained(MODEL_PATH)
    model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH)
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    # 定义实验起点
    START_NODE = "数据结构"

    # 定义两个对比学生
    students = [
        {
            "name": "学生 A (初学者)",
            "known": set(),  # 一张白纸
            "pref": "零基础, 喜欢视频, 循序渐进",
            "desc": "预期：从基础概念开始 (线性表...)"
        },
        {
            "name": "学生 B (进阶者)",
            "known": {"线性表", "栈", "队列", "链表", "数组", "广义表"},  # 已知基础
            "pref": "有编程基础, 喜欢代码, 攻克难点",
            "desc": "预期：跳过基础，直接讲树/图/算法"
        }
    ]

    print(f"\n🚀 开始个性化对比实验 (起点: {START_NODE})...\n")
    print("=" * 60)

    for stu in students:
        print(f"👤 正在为 [{stu['name']}] 生成路径...")
        print(f"   ℹ️  画像: {stu['pref']}")
        print(f"   🧠 已知: {stu['known'] if stu['known'] else '无'}")

        # 为了保证可复现，可以设置种子 (可选)
        torch.manual_seed(42)

        path = generate_fusion_path(
            model, tokenizer, driver,
            START_NODE,
            known_concepts=stu['known'],
            user_pref=stu['pref']
        )

        print(f"   🛣️  生成路径: {path}")
        print("-" * 60)

    driver.close()

