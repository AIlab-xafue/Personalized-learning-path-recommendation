import os
import json
import logging
import time
from neo4j import GraphDatabase, basic_auth
from pathlib import Path
import sys

# ==========================================
# 1. 配置区 (请务必修改)
# ==========================================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")  # 您的密码

# (修改我) MOOCCube 数据集的根目录
DATA_BASE_PATH_STR = os.environ.get("MOOCCUBE_DIR", "data/MOOCCube")
DATA_DIR = Path(DATA_BASE_PATH_STR)

# 批量处理大小
BATCH_SIZE = 5000

# ==========================================
# 2. 映射配置
# ==========================================

# 节点文件配置 (文件名 -> Label)
ENTITY_FILES = {
    "user.json": "User",
    "course.json": "Course",
    "concept.json": "Concept",
    "video.json": "Video",
    "teacher.json": "Teacher",
    "school.json": "School",
    "paper.json": "Paper"
}

# 关系文件配置
# 格式: (子文件夹, 文件名, 起点Label, 关系类型, 终点Label, 起点Key, 终点Key)
RELATION_CONFIGS = [
    # --- 1. 核心先修关系 (来自 relations 文件夹) ---
    # 这是人工标注的 Ground Truth，置信度高
    # 通常键名为 concept_a_id, concept_b_id (脚本会自动尝试这些变体)
    ("relations", "prerequisite-dependency.json", "Concept", "PREREQUISITE", "Concept", "concept_a_id", "concept_b_id"),

    # --- 2. 附加先修关系 (来自 additional_information 文件夹) ---
    # 这是算法预测的，覆盖率高
    # 您确认过键名为 c1, c2
    ("additional_information", "prerequisite_prediction.json", "Concept", "PREREQUISITE_PRED", "Concept", "c1", "c2"),

    # --- 3. 其他常规关系 ---
    ("relations", "user-course.json", "User", "ENROLLED_IN", "Course", "user_id", "course_id"),
    ("relations", "user-video.json", "User", "WATCHED", "Video", "user_id", "video_id"),
    ("relations", "course-concept.json", "Course", "COVERS", "Concept", "course_id", "concept_id"),
    ("relations", "course-video.json", "Course", "CONTAINS", "Video", "course_id", "video_id"),
    ("relations", "video-concept.json", "Video", "EXPLAINS", "Concept", "video_id", "concept_id"),
    ("relations", "teacher-course.json", "Teacher", "TEACHES", "Course", "teacher_id", "course_id"),
    ("relations", "school-course.json", "School", "OFFERS", "Course", "school_id", "course_id"),
    ("relations", "school-teacher.json", "School", "EMPLOYS", "Teacher", "school_id", "teacher_id"),
    ("relations", "concept-paper.json", "Concept", "APPEARS_IN", "Paper", "concept_id", "paper_id"),
]

# ==========================================
# 3. 核心代码
# ==========================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_driver():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logging.info("✅ Neo4j 连接成功")
        return driver
    except Exception as e:
        logging.critical(f"❌ 连接失败: {e}")
        sys.exit(1)

def clear_database(driver):
    """清空数据库 (先清空旧数据再导入)"""
    logging.info("正在清空数据库...")
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        # 清空约束
        try:
            constraints = session.run("SHOW CONSTRAINTS").data()
            for c in constraints:
                session.run(f"DROP CONSTRAINT `{c['name']}`")
            # 清空索引
            indexes = session.run("SHOW INDEXES").data()
            for i in indexes:
                if i['type'] == 'RANGE' and i.get('owningConstraint') is None:
                    session.run(f"DROP INDEX `{i['name']}`")
        except Exception as e:
            logging.warning(f"清空约束时警告 (可忽略): {e}")
    logging.info("数据库已清空 ✅")

def create_constraints(driver):
    """为所有节点创建唯一ID约束"""
    logging.info("--- 步骤 1: 创建索引与约束 ---")
    with driver.session() as session:
        for label in ENTITY_FILES.values():
            # Concept 使用 name 作为唯一键 (为了配合 prerequisite_prediction.json)
            # 如果 concept.json 中有 id，通常建议用 id，但 prediction 文件用的是 name
            # 这里我们对 Concept 同时建立 id 和 name 索引以防万一
            if label == "Concept":
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")
                session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.name)")
                logging.info(f"   > {label}: id 约束 & name 索引已创建")
            else:
                query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                session.run(query)
                logging.info(f"   > {label}: id 唯一约束已创建")
    logging.info("✅ 约束创建完成")

def flatten_json(y):
    """递归压平 JSON 对象，防止 Neo4j 报错"""
    flat_row = {}
    for k, v in y.items():
        if k == 'id':
            flat_row[k] = v
            continue
        if isinstance(v, (dict, list)):
            flat_row[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat_row[k] = v
    return flat_row

def load_nodes(driver):
    """加载节点"""
    logging.info("\n--- 步骤 2: 加载节点 (Entities) ---")
    entities_dir = DATA_DIR / "entities"
    # 容错路径
    if not entities_dir.exists():
        entities_dir = DATA_DIR / "实体+关系"

    if not entities_dir.exists():
        logging.error(f"❌ 节点文件夹未找到: {entities_dir}")
        return

    for filename, label in ENTITY_FILES.items():
        path = entities_dir / filename
        if not path.exists():
            logging.warning(f"   ⚠️ 跳过缺失文件: {filename}")
            continue

        logging.info(f"   > 正在加载 {filename} ...")

        batch = []
        count = 0
        start_time = time.time()

        query = f"UNWIND $batch AS row MERGE (n:{label} {{id: row.id}}) SET n += row.props"

        with driver.session() as session:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            row = json.loads(line)
                            node_id = row.get('id')
                            # 如果 Concept 没有 id，尝试用 name 作为 id (针对 MOOCCube 某些版本)
                            if not node_id and label == "Concept": node_id = row.get('name')

                            if not node_id: continue

                            props = flatten_json(row)
                            if 'id' in props: del props['id']

                            batch.append({"id": node_id, "props": props})

                            if len(batch) >= BATCH_SIZE:
                                session.run(query, batch=batch)
                                count += len(batch)
                                batch = []
                                print(f"     已处理: {count}", end='\r')

                        except json.JSONDecodeError:
                            continue

                # 提交剩余
                if batch:
                    session.run(query, batch=batch)
                    count += len(batch)

                elapsed = time.time() - start_time
                logging.info(f"     ✅ {label}: 加载完成 {count} 个 (耗时 {elapsed:.2f}s)")

            except Exception as e:
                logging.error(f"     ❌ 加载失败: {e}")

def load_relations(driver):
    """加载关系 (混合解析 JSONL 和 TSV)"""
    logging.info("\n--- 步骤 3: 加载关系 (Relations) ---")

    for subdir, filename, start_lbl, rel_type, end_lbl, start_key, end_key in RELATION_CONFIGS:
        path = DATA_DIR / subdir / filename

        # 容错中文路径
        if not path.exists() and subdir == "relations":
             path = DATA_DIR / "实体+关系" / filename

        if not path.exists():
            logging.warning(f"   ⚠️ 跳过缺失文件: {subdir}/{filename}")
            continue

        logging.info(f"   > 正在加载 {filename} ({rel_type})...")

        batch = []
        count = 0
        start_time = time.time()

        # (关键) 动态构建 Cypher 查询
        # 对于 prerequisite_prediction.json，它是基于 name 的 (c1, c2 是名字)
        if filename == "prerequisite_prediction.json":
            query = f"""
            UNWIND $batch AS row
            MATCH (a:{start_lbl} {{name: row.s}})
            MATCH (b:{end_lbl} {{name: row.e}})
            MERGE (a)-[r:{rel_type}]->(b)
            """
        else:
            # 其他关系通常基于 id
            query = f"""
            UNWIND $batch AS row
            MATCH (a:{start_lbl} {{id: row.s}})
            MATCH (b:{end_lbl} {{id: row.e}})
            MERGE (a)-[r:{rel_type}]->(b)
            """

        with driver.session() as session:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue

                        s_id = None
                        e_id = None

                        # --- 策略 A: 尝试当作 JSON 解析 ---
                        try:
                            row = json.loads(line)
                            s_id = row.get(start_key)
                            e_id = row.get(end_key)

                            # 容错键名 (自动尝试常见的键名变体)
                            if not s_id and 'Concept' in start_lbl:
                                s_id = row.get('concept_id') or row.get('concept_a') or row.get('concept_a_id') or row.get('source_id') or row.get('c1')
                            if not e_id and 'Concept' in end_lbl:
                                e_id = row.get('concept_id') or row.get('concept_b') or row.get('concept_b_id') or row.get('target_id') or row.get('c2')

                        except json.JSONDecodeError:
                            # --- 策略 B: JSON 失败，尝试当作 TSV (制表符分隔) 解析 ---
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                s_id = parts[0].strip()
                                e_id = parts[1].strip()

                        if s_id and e_id:
                            batch.append({"s": s_id, "e": e_id})

                        if len(batch) >= BATCH_SIZE:
                            session.run(query, batch=batch)
                            count += len(batch)
                            batch = []
                            print(f"     已处理: {count}", end='\r')

                if batch:
                    session.run(query, batch=batch)
                    count += len(batch)

                elapsed = time.time() - start_time
                logging.info(f"     ✅ {rel_type}: 加载完成 {count} 条 (耗时 {elapsed:.2f}s)")

            except Exception as e:
                logging.error(f"     ❌ 加载失败: {e}")

if __name__ == "__main__":
    if not DATA_DIR.exists():
        logging.critical(f"❌ 错误: 路径不存在 -> {DATA_DIR}")
        sys.exit(1)

    driver = get_driver()
    try:
        clear_database(driver) # 步骤 0：清空旧数据
        create_constraints(driver) # 步骤 1：创建约束

        load_nodes(driver) # 步骤 2：加载节点
        load_relations(driver) # 步骤 3：加载关系

        logging.info("\n✨ 全部导入完成！")
    finally:
        driver.close()