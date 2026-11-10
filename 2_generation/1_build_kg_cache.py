# -----------------------------------------------------------------------------
#脚本一：1_build_kg_cache.py (构建约束缓存)
#作用 (Role): 该脚本是整个“硬约束”机制的基础设施。它的核心任务是离线预处理。它从 Neo4j 知识图谱中提取全量的先修关系知识，并将其转化为一个高效的本地查找表（JSON 缓存）。这样做是为了避免在模型推理（Inference）阶段频繁查询数据库，从而保证生成的实时性。
#技术细节 (Technical Details):
#数据源: 连接到 MOOCCube 知识图谱（Neo4j）。
#查询逻辑: 执行 Cypher 查询 MATCH (a:Concept)-[:PREREQUISITE|PREREQUISITE_PRED]->(b:Concept)。这不仅包含人工标注的高置信度关系 (PREREQUISITE)，也包含算法预测的高覆盖率关系 (PREREQUISITE_PRED)，确保约束规则的完备性。
#数据结构: 构建一个邻接表（Adjacency List）形式的字典：{ "当前概念": ["合法后继1", "合法后继2", ...] }。
#输出: 生成 kg_transition_cache.json 文件。这个文件本质上定义了模型生成的“合法边界”。
# -----------------------------------------------------------------------------
import os
import json
import sys
import time
from neo4j import GraphDatabase, basic_auth

# --- 配置区 ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")  # 您的密码
OUTPUT_FILE = "../Title2/kg_transition_cache1.json"


def build_transition_map():
    print(f"🔌 正在连接 Neo4j ({NEO4J_URI})...")
    driver = None
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)

    print("⏳ 正在提取全量先修关系 (这可能需要几秒钟)...")
    start_time = time.time()

    # 查询：获取所有的一跳先修关系
    # 同时包含人工标注 (PREREQUISITE) 和 算法预测 (PREREQUISITE_PRED)
    query = """
    MATCH (a:Concept)-[:PREREQUISITE|PREREQUISITE_PRED]->(b:Concept)
    RETURN a.name AS source, b.name AS target
    """

    transition_map = {}
    relation_count = 0

    with driver.session() as session:
        result = session.run(query)
        for record in result:
            src = record["source"]
            tgt = record["target"]

            if src not in transition_map:
                transition_map[src] = []

            # 避免重复添加
            if tgt not in transition_map[src]:
                transition_map[src].append(tgt)
                relation_count += 1

    driver.close()
    elapsed = time.time() - start_time

    print(f"✅ 提取完成！耗时 {elapsed:.2f} 秒")
    print(f"   - 覆盖概念数 (起点): {len(transition_map)}")
    print(f"   - 总跳转关系数: {relation_count}")

    # 保存为 JSON
    print(f"💾 正在保存缓存至 {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(transition_map, f, ensure_ascii=False, indent=2)
    print("✅ 完成。")


if __name__ == "__main__":
    build_transition_map()