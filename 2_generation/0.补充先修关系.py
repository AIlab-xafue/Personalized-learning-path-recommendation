import os
import json
import time
from neo4j import GraphDatabase, basic_auth
from pathlib import Path
import sys

# ==========================================
# 1. 配置区 (请修改)
# ==========================================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")

# 指向您的 MOOCCube 数据集根目录
DATA_BASE_PATH_STR = os.environ.get("MOOCCUBE_DIR", "data/MOOCCube")
# 先修关系文件的相对路径
PREREQ_FILE_REL_PATH = os.path.join(os.environ.get("MOOCCUBE_DIR", "data/MOOCCube"), "additional_information", "prerequisite_prediction.json")

BATCH_SIZE = 5000  # 批量提交大小


# ==========================================
# 2. 核心代码
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


def import_prerequisites(driver, file_path):
    if not os.path.exists(file_path):
        print(f"❌ 文件未找到: {file_path}")
        return

    print(f"--- 开始导入先修关系: {os.path.basename(file_path)} ---")
    print("⚠️  注意：仅当概念名称(name)在图谱中完全匹配时，才会建立关系。")

    # 1. (建议) 临时创建 name 索引以加速匹配 (如果已有会忽略)
    # 这一步不会修改数据，只会让查询变快
    with driver.session() as session:
        try:
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Concept) ON (n.name)")
            print("ℹ️  已确保 Concept(name) 索引存在，加速匹配。")
        except Exception as e:
            print(f"⚠️ 索引创建跳过 (不影响导入): {e}")

    # 2. 批量导入逻辑
    # 使用 MATCH ... MATCH ... MERGE ...
    # 如果 MATCH 找不到节点，整个语句会变为无操作 (No-op)，保证不创建脏数据
    query = """
    UNWIND $batch AS row
    MATCH (source:Concept {name: row.c1})
    MATCH (target:Concept {name: row.c2})
    MERGE (source)-[r:PREREQUISITE]->(target)
    """

    batch = []
    count = 0
    start_time = time.time()

    with driver.session() as session:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if not line.strip(): continue

                    try:
                        row = json.loads(line)

                        # 获取概念名称 (键名为 c1, c2)
                        c1 = row.get('c1')
                        c2 = row.get('c2')

                        if c1 and c2:
                            batch.append({"c1": c1, "c2": c2})

                        # 批量提交
                        if len(batch) >= BATCH_SIZE:
                            result = session.run(query, batch=batch)
                            # 获取实际创建的关系数量 (Summary)
                            stats = result.consume().counters
                            created = stats.relationships_created
                            count += created

                            batch = []
                            print(f"   已处理 {line_no} 行，实际新建关系: {count} 条...", end='\r')

                    except json.JSONDecodeError:
                        continue

            # 提交剩余批次
            if batch:
                result = session.run(query, batch=batch)
                stats = result.consume().counters
                count += stats.relationships_created

            elapsed = time.time() - start_time
            print(f"\n✅ 导入完成！")
            print(f"   - 耗时: {elapsed:.2f} 秒")
            print(f"   - 成功建立关系: {count} 条")

            if count == 0:
                print("⚠️ 警告：建立了 0 条关系。可能是图谱中 Concept 的 'name' 属性与文件中的名称不匹配。")

        except Exception as e:
            print(f"\n❌ 导入过程中出错: {e}")


if __name__ == "__main__":
    base_path = Path(DATA_BASE_PATH_STR)
    full_path = base_path / PREREQ_FILE_REL_PATH

    driver = get_driver()
    try:
        import_prerequisites(driver, full_path)
    finally:
        driver.close()