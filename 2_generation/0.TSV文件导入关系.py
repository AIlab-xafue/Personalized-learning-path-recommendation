import os
import time
from neo4j import GraphDatabase, basic_auth
import sys

# ==========================================
# 1. 配置区
# ==========================================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")

# 请确认这是您的文件真实路径
TARGET_FILE_PATH = os.path.join(os.environ.get("MOOCCUBE_DIR", "data/MOOCCube"), "relations", "prerequisite-dependency.json")

BATCH_SIZE = 5000


# ==========================================
# 2. 核心逻辑
# ==========================================

def get_driver():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("✅ Neo4j 连接成功")
        return driver
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)


def clean_concept_name(raw_str):
    """
    数据清洗函数：从 'K_概念名_学科' 中提取 '概念名'
    例如: 'K_计算机科学_计算机科学技术' -> '计算机科学'
    """
    if not raw_str: return None

    # 1. 去除 'K_' 前缀
    if raw_str.startswith("K_"):
        temp = raw_str[2:]
    else:
        temp = raw_str

    # 2. 去除后缀 (学科名)
    # 逻辑：找到最后一个下划线，取其左边的部分
    # 这样做是为了防止概念名本身包含下划线（如 TCP_IP）被误切
    parts = temp.rsplit('_', 1)
    if len(parts) > 1:
        return parts[0]
    else:
        return temp


def import_tsv_relations(driver, file_path):
    if not os.path.exists(file_path):
        print(f"❌ 文件未找到: {file_path}")
        return

    print(f"--- 开始处理 TSV 格式文件: {os.path.basename(file_path)} ---")

    # 1. 确保索引存在 (加速匹配)
    with driver.session() as session:
        try:
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Concept) ON (n.name)")
        except:
            pass

    # 2. 读取并清洗数据
    batch = []
    count = 0
    total_lines = 0
    start_time = time.time()

    # Cypher 语句
    query = """
    UNWIND $batch AS row
    MATCH (source:Concept {name: row.c1})
    MATCH (target:Concept {name: row.c2})
    MERGE (source)-[r:PREREQUISITE]->(target)
    """

    print("正在读取并导入数据...")

    with driver.session() as session:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                total_lines += 1

                # TSV 分割
                parts = line.split('\t')
                if len(parts) < 2:
                    continue

                # 提取原始字符串
                raw_c1 = parts[0].strip()
                raw_c2 = parts[1].strip()

                # 数据清洗
                c1 = clean_concept_name(raw_c1)
                c2 = clean_concept_name(raw_c2)

                if c1 and c2:
                    batch.append({"c1": c1, "c2": c2})

                # 打印前几条清洗结果，方便您验证
                if total_lines <= 3:
                    print(f"   [样例清洗] 原文: {raw_c1} -> 清洗后: {c1}")

                # 批量提交
                if len(batch) >= BATCH_SIZE:
                    result = session.run(query, batch=batch)
                    stats = result.consume().counters
                    count += stats.relationships_created
                    batch = []  # 清空
                    print(f"   已处理 {total_lines} 行 | 成功建立关系: {count}...", end='\r')

            # 提交剩余数据
            if batch:
                result = session.run(query, batch=batch)
                stats = result.consume().counters
                count += stats.relationships_created

    elapsed = time.time() - start_time
    print(f"\n\n✅ 导入完成！")
    print(f"   - 总行数: {total_lines}")
    print(f"   - 成功建立关系: {count} 条")
    print(f"   - 耗时: {elapsed:.2f} 秒")

    if count == 0:
        print("\n⚠️ 警告：依然是 0 条。请检查控制台打印的 '[样例清洗]' 是否与您数据库里的 name 一致。")


if __name__ == "__main__":
    driver = get_driver()
    try:
        import_tsv_relations(driver, TARGET_FILE_PATH)
    finally:
        driver.close()