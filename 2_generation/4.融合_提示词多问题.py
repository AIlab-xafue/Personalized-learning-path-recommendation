# -----------------------------------------------------------------------------
# 【终极融合脚本: 4_fusion_generation.py】
# 核心特性:
# 1. 动态前缀树 (Trie) 硬约束，物理屏蔽非法幻觉 Token
# 2. 个性化学生画像 (Persona) 注入软约束
# 3. 增强历史轨迹感知 (Global History) 解决失忆
# 4. 图谱出度中心性排序 (Heuristic RAG) 启发式引导
# 5. 图约束束搜索 (Beam Search) 解决生成短视
# -----------------------------------------------------------------------------
import json, sys, os, torch, random
from tqdm import tqdm
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth

# ================= 配置区 =================
MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"
OUTPUT_FILE = "generated_results_fusion_final.txt"
SAMPLE_SIZE = 747


# ================= 1. 硬约束掩码构建 (Trie Tree) =================
class TrieNode:
    def __init__(self):
        self.children, self.is_end = {}, False


class ConceptTrie:
    def __init__(self, tokenizer, concept_list):
        self.root = TrieNode()
        for concept in concept_list:
            # 兼容T5分词：带前导空格和不带前导空格的情况
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
                return [tokenizer.eos_token_id]  # 走错路，物理截断
        allowed = list(node.children.keys())
        if node.is_end: allowed.append(tokenizer.eos_token_id)
        return allowed if allowed else [tokenizer.eos_token_id]

    return prefix_allowed_tokens_fn


# ================= 2. 启发式图谱查询 (Heuristic RAG) =================
def get_valid_and_context(driver, current_node):
    """获取硬约束和软约束信息（引入出度中心性排序）"""
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
            # 提取前5个核心节点作为强提示
            return nexts, ", ".join(nexts[:5]) if nexts else "无"
    except Exception as e:
        print(f"Graph Query Error: {e}")
        return [], "无"


# ================= 3. 终极融合 Prompt 构造 =================
def construct_enhanced_prompt(path_history, rag_context, step_num, total_steps,
                              persona_text="学习能力中等, 偏好循序渐进的引导"):
    """
    完全对应终极设计漏斗：融合了宏观定位、学生画像、历史轨迹、启发式RAG和指令控制
    """
    history_str = " -> ".join(path_history)
    current_concept = path_history[-1]

    prompt = (
        f"任务: 个性化连贯学习路径规划\n"
        f"学生画像: {persona_text}\n"
        f"已学轨迹: {history_str} (进度: {step_num}/{total_steps}步)\n"
        f"当前起点: {current_concept}\n"
        f"合法候选集: [{rag_context}]\n"
        f"指令: 请结合学生的个性化画像与已学的语义上下文，从合法候选集中选择最适合、最连贯且未访问过的下一个知识点。\n"
        f"下一个概念是:"
    )
    return prompt


# ================= 4. 软硬协同核心生成逻辑 =================
def generate_fusion_path(model, tokenizer, driver, start_node, max_steps=20):
    current_node = start_node
    path_list = [start_node]
    visited = {start_node}

    # 为了模拟生成个性化数据集，随机给定一个画像
    random_persona = random.choice([
        "逻辑思维强, 偏好深入探索底层原理",
        "基础薄弱, 极度需要循序渐进、由浅入深的引导",
        "偏好实战应用, 喜欢快速掌握核心主干知识"
    ])

    for step in range(max_steps):
        # 1. 获取排序后的图谱硬约束与软约束上下文
        valid_nexts, rag_context = get_valid_and_context(driver, current_node)
        if not valid_nexts: break

        # 2. 负向过滤：彻底剔除已访问节点防死循环
        unvisited_nexts = [n for n in valid_nexts if n not in visited]
        if not unvisited_nexts: break

        # 3. 构建 Trie 前缀树物理掩码
        constraint_fn = get_constraint_fn(tokenizer, unvisited_nexts)

        # 4. 构建融合 Prompt
        prompt = construct_enhanced_prompt(path_list, rag_context, step + 1, max_steps, persona_text=random_persona)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        # 5. 束搜索 (Beam Search) 协同解码
        try:
            outputs = model.generate(
                **inputs,
                max_length=20,
                num_beams=5,  # 束搜索探索 5 条候选
                num_return_sequences=1,  # 只取最优 1 条
                repetition_penalty=2.5,  # 惩罚重复输出
                early_stopping=True,
                prefix_allowed_tokens_fn=constraint_fn  # 注入物理掩码
            )
            next_concept = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

            # 6. 安全验证与路径推进
            if next_concept in unvisited_nexts:
                path_list.append(next_concept)
                visited.add(next_concept)
                current_node = next_concept
            else:
                break  # 防止极端情况下的幻觉，直接熔断
        except Exception as e:
            print(f"Generation interrupted: {e}")
            break

    return " -> ".join(path_list)


# ================= 5. 主程序 =================
if __name__ == "__main__":
    print(f"⏳ [Fusion] 正在初始化环境与加载 T5 模型...")
    tokenizer = MT5TokenizerFast.from_pretrained(MODEL_PATH)
    model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH)

    # 自动硬件加速
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    print(f"✅ 模型加载完毕，运行设备: {device}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    # 加载起始点池
    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f:
        kg_cache = json.load(f)

    # 筛选起点：只选择具有较多后继分支（>2）的节点作为起点，体现大模型规划能力
    valid_starts = [k for k, v in kg_cache.items() if len(v) > 2]
    test_starts = random.sample(valid_starts, SAMPLE_SIZE) if len(valid_starts) > SAMPLE_SIZE else valid_starts

    print(f"\n🚀 开始生成终极融合版数据 (N={len(test_starts)})...")
    generated_paths = []

    # 进度条展示与写入
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for start in tqdm(test_starts, desc="生成进度"):
            path = generate_fusion_path(model, tokenizer, driver, start)

            # 过滤无效路径（未产生跳跃）
            if path.count("->") >= 1:
                f.write(path + "\n")
                generated_paths.append(path)

    print(f"\n✅ 生成完毕！结果已保存至: {os.path.abspath(OUTPUT_FILE)}")
    print(f"💾 共生成 {len(generated_paths)} 条高质量连贯路径")
    if generated_paths:
        print(f"👉 示例输出: {generated_paths[0]}")

    driver.close()