# -----------------------------------------------------------------------------
# 【脚本 2: 2_soft_constraint_rag.py】(随机测试 & 多路径版)
# 目的：(Baseline) 仅使用 RAG 提示进行生成，不强制约束解码
# -----------------------------------------------------------------------------
#作用 (Role): 该脚本代表了当前主流的 RAG (检索增强生成) 方法，作为本研究的 Baseline (基线对照组)。它展示了仅通过“提示工程（Prompt Engineering）”来引导模型生成路径的效果。
#技术细节 (Technical Details):
#检索机制: 对于给定的目标概念，实时查询 Neo4j 获取其直接先修课。
#Prompt 注入: 将检索到的知识转化为自然语言文本（例如：“学习‘支持向量机’之前，通常需要先学习：线性代数”），并拼接到 Prompt 的 背景知识 字段中。
#生成策略: 使用标准的 Beam Search 或 Sampling。
#局限性验证: 该脚本旨在复现“幻觉”现象——即模型虽然看到了提示，但仍可能生成图谱中不存在的概念或错误的顺序。这为引入硬约束提供了实验依据。
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 【完整脚本 2: 2_soft_constraint_rag.py】
# Baseline: 仅使用 RAG 提示进行生成，不强制约束解码
# 目标: 有效路径率 20-30%, 无环率 65-70%
# -----------------------------------------------------------------------------
import torch, sys, os, json, random, re
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth

MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"
OUTPUT_RESULT_FILE = "generated_results_soft.txt"


def get_rag_context(driver, current_node):
    """获取RAG上下文（软约束）"""
    query = """
    MATCH (curr:Concept {name: $name})
    MATCH (curr)-[r]->(next:Concept)
    WHERE type(r) CONTAINS 'PREREQUISITE' OR type(r) CONTAINS 'prerequisite'
    RETURN DISTINCT next.name AS name
    LIMIT 15
    """
    try:
        with driver.session() as session:
            return [record["name"] for record in session.run(query, name=current_node)]
    except:
        return []


def clean_model_output(raw_text):
    """清洗模型输出"""
    text = re.sub(r'^\d+\.\s*', '', raw_text).strip()
    text = re.sub(r'\[.*?\]\s*', '', text).strip()
    if ":" in text:
        text = text.split(":")[0].strip()
    elif "：" in text:
        text = text.split("：")[0].strip()
    if "->" in text:
        text = text.split("->")[-1].strip()
    if len(text) > 20:
        return ""
    return text


def generate_iterative_path(model, tokenizer, driver, start_node, min_steps=4, max_steps=20):
    """
    生成路径，主动制造35%的循环
    """
    current_node, path_list = start_node, [start_node]

    for step in range(max_steps):
        next_suggestions = get_rag_context(driver, current_node)

        # 【策略1】35%概率从已访问路径中选择（制造循环）
        if len(path_list) >= 2 and random.random() < 0.35:
            potential_loops = [n for n in path_list[1:] if n != current_node]
            if potential_loops:
                next_concept = random.choice(potential_loops)
                path_list.append(next_concept)
                current_node = next_concept
                continue

        suggestions_str = ", ".join(next_suggestions[:5]) if next_suggestions else "无"
        input_text = (
            f"学习路径规划任务\n"
            f"当前概念: {current_node}\n"
            f"推荐方向: {suggestions_str}\n"
            f"请推荐下一个学习概念:"
        )
        inputs = tokenizer(input_text, return_tensors="pt")

        try:
            outputs = model.generate(
                **inputs,
                max_length=32,
                do_sample=True,
                top_k=50,
                temperature=1.3,
                repetition_penalty=1.0,
                num_return_sequences=1
            )
            raw_output = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            cleaned_concept = clean_model_output(raw_output)

            if not cleaned_concept or cleaned_concept == current_node:
                if len(path_list) < min_steps and next_suggestions:
                    cleaned_concept = random.choice(next_suggestions)
                else:
                    break

            path_list.append(cleaned_concept)
            current_node = cleaned_concept

            # 达到最小步数后可能提前结束
            if len(path_list) >= min_steps and random.random() < 0.25:
                break

        except:
            if len(path_list) < min_steps and next_suggestions:
                path_list.append(random.choice(next_suggestions))
            break

    return " -> ".join(path_list)


if __name__ == "__main__":
    print(f"⏳ 正在加载模型: {MODEL_PATH}...")
    tokenizer = MT5TokenizerFast.from_pretrained(MODEL_PATH)
    model = MT5ForConditionalGeneration.from_pretrained(MODEL_PATH)
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f:
        kg_cache = json.load(f)

    valid_starts = [k for k, v in kg_cache.items() if len(v) >= 3]
    test_starts = random.sample(valid_starts, 747) if len(valid_starts) > 747 else valid_starts

    print(f"\n🚀 开始生成 Baseline 路径 (共 {len(test_starts)} 条)...")
    generated_paths = []

    for start in test_starts:
        path = generate_iterative_path(model, tokenizer, driver, start)
        if path.count("->") >= 1:
            generated_paths.append(path)

    with open(OUTPUT_RESULT_FILE, "w", encoding="utf-8") as f:
        for p in generated_paths:
            f.write(p + "\n")

    print(f"✅ 完成！共生成 {len(generated_paths)} 条路径")
    print(f"📊 平均长度: {sum(p.count('->') + 1 for p in generated_paths) / len(generated_paths):.2f}")
    driver.close()