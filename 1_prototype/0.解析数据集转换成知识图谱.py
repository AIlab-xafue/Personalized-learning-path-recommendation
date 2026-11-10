import os
import csv
import logging
import time
import json
from py2neo import Graph
from pathlib import Path
import sys

# ===== 配置区 =====
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
BATCH_SIZE = 5000  # (优化) 增加批量大小以减少事务次数

# (优化) 自动获取 database 文件夹的路径
# 假设 database 文件夹与此 .py 脚本位于同一级别
try:
    # (新) 自动查找 'database' 文件夹
    DATA_DIR = Path(__file__).parent / "database"
    if not DATA_DIR.exists():
        # (备用) 如果在 IDE 中直接运行，可能需要这个
        DATA_DIR = Path(r"database")
        if not DATA_DIR.exists():
            raise FileNotFoundError
except (FileNotFoundError, NameError):
    # (如果都找不到，则使用您脚本中的原始硬编码路径)
    DATA_DIR = Path(r"database")
    if not DATA_DIR.exists():
        logging.error(f"❌ [错误] 未找到 'database' 文件夹。")
        logging.error(f"   请确保 'DATA_DIR' 变量指向了您包含 CSV 文件的文件夹。")
        sys.exit(1)

# ===== 初始化日志 =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== (优化) 节点 Schema 定义 (文件名, 标签, 主键) =====
# (关键假设：基于我们之前的讨论，Concept 的主键是 'name'，其他是 'id')
# (如果 Concept 的主键也是 'id'，请将 'name' 改回 'id')
ENTITY_FILES = {
    "concept.csv": ("Concept", "id"),  # 假设 'concept.csv' 也有 'id' 列
    "course.csv": ("Course", "id"),
    "paper.csv": ("Paper", "id"),
    "school.csv": ("School", "id"),
    "teacher.csv": ("Teacher", "id"),
    "user.csv": ("User", "id"),
    "video.csv": ("Video", "id"),
}

# ===== (优化) 关系 Schema 定义 =====
# 格式: (文件名, 起点标签, 起点键, 关系类型, 终点标签, 终点键, CSV起始列, CSV终点列)
# (关键) 我们现在为 MATCH 指定了标签 (例如 'User', 'Video')，这将极大提速
REL_FILES = {
    # (注意: 假设所有 start/end_id 都引用 'id' 键)
    # (如果先修关系是 concept.name <-> concept.name, 您需要修改下面这行)
    "rel_prerequisite_dependency.csv": ("Concept", "id", "PREREQUISITE", "Concept", "id", "start_id", "end_id"),

    "rel_concept_paper.csv": ("Concept", "id", "CONCEPT_PAPER", "Paper", "id", "start_id", "end_id"),
    "rel_course_concept.csv": ("Course", "id", "COURSE_CONCEPT", "Concept", "id", "start_id", "end_id"),
    "rel_course_video.csv": ("Course", "id", "COURSE_VIDEO", "Video", "id", "start_id", "end_id"),
    "rel_field_concept.csv": ("Concept", "id", "FIELD_CONCEPT", "Concept", "id", "start_id", "end_id"),
    # 假设 Concept -> Concept
    "rel_school_course.csv": ("School", "id", "SCHOOL_COURSE", "Course", "id", "start_id", "end_id"),
    "rel_school_teacher.csv": ("School", "id", "SCHOOL_TEACHER", "Teacher", "id", "start_id", "end_id"),
    "rel_teacher_course.csv": ("Teacher", "id", "TEACHER_COURSE", "Course", "id", "start_id", "end_id"),
    "rel_user_course.csv": ("User", "id", "USER_COURSE", "Course", "id", "start_id", "end_id"),
    "rel_user_video.csv": ("User", "id", "USER_VIDEO", "Video", "id", "start_id", "end_id"),
    "rel_video_concept.csv": ("Video", "id", "VIDEO_CONCEPT", "Concept", "id", "start_id", "end_id"),
}


def get_neo4j_driver(uri, user, password):
    """(新) 辅助函数：连接 Neo4j"""
    try:
        driver = Graph(uri, auth=(user, password))
        driver.run("RETURN 1")  # 测试连接
        logging.info(f"✅ Neo4j 连接成功 (URI: {uri})")
        return driver
    except Exception as e:
        logging.critical(f"❌ [严重错误] Neo4j 连接失败: {e}")
        sys.exit(1)


def clear_database(graph):
    """清空 Neo4j 中所有节点和关系"""
    logging.info("正在清空 Neo4j 数据库...")
    graph.run("MATCH (n) DETACH DELETE n")
    # (新) 清空所有约束和索引
    try:
        constraints = graph.run("SHOW CONSTRAINTS").data()
        for c in constraints:
            graph.run(f"DROP CONSTRAINT `{c['name']}`")
        indexes = graph.run("SHOW INDEXES").data()
        for i in indexes:
            # 过滤掉自动创建的约束索引 (它们会在 DROP CONSTRAINT 时自动删除)
            if i['type'] == 'RANGE' and not i['uniqueness'] == 'UNIQUE':
                graph.run(f"DROP INDEX `{i['name']}`")
        logging.info("已清空旧约束和索引。")
    except Exception as e:
        logging.warning(f"清空约束/索引时出错: {e}")
    logging.info("数据库已清空 ✅")


def create_constraints(graph):
    """(优化) 关键优化：为所有节点的主键创建唯一约束 (和索引)"""
    logging.info("--- 步骤 1: 正在创建数据库约束和索引... ---")
    tx = graph.begin()
    try:
        for filename, (label, key) in ENTITY_FILES.items():
            # (优化) 使用 CONSTRAINT (唯一性 + 索引)
            query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            tx.run(query)
            logging.info(f"  > 已创建/确认 {label} 节点的唯一 {key} 约束。")
        tx.commit()
        logging.info("✅ 约束和索引创建完毕。")
    except Exception as e:
        logging.error(f"❌ 创建约束时出错: {e}")
        tx.rollback()
        sys.exit(1)


def commit_node_batch(tx, label, key_name, batch):
    """(优化) 辅助函数：使用 UNWIND 批量提交节点"""
    # (优化) Cypher 查询现在动态使用标签和主键
    query = f"""
    UNWIND $batch AS row
    MERGE (n:{label} {{{key_name}: row.{key_name}}})
    SET n += row.props
    """
    tx.run(query, batch=batch)


def load_entities(graph):
    """(已优化) 批量加载所有节点"""
    logging.info(f"\n--- 步骤 2: 正在从 {DATA_DIR} 加载节点... ---")

    for filename, (label, key_name) in ENTITY_FILES.items():
        path = DATA_DIR / filename
        if not path.exists():
            logging.warning(f"  [警告] 未找到文件: {path}，跳过 {label} 节点。")
            continue

        logging.info(f"  > 正在加载 {filename} ...")

        batch = []
        count = 0
        start_time = time.time()
        tx = graph.begin()  # (优化) 为每个文件开启一个事务

        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    primary_key_value = row.get(key_name)
                    if not primary_key_value:
                        logging.warning(f"   [警告] {filename} 中发现缺少主键 '{key_name}' 的行: {row}。跳过。")
                        continue

                    # (优化) 属性 = row - 主键
                    properties = {k: v for k, v in row.items() if k != key_name and v}

                    # (优化) 批处理数据包含主键和属性
                    batch_item = {
                        key_name: primary_key_value,
                        "props": properties
                    }
                    batch.append(batch_item)

                    if len(batch) >= BATCH_SIZE:
                        commit_node_batch(tx, label, key_name, batch)
                        count += len(batch)
                        batch.clear()

            if batch:
                commit_node_batch(tx, label, key_name, batch)
                count += len(batch)

            tx.commit()
            elapsed = time.time() - start_time
            logging.info(f"    > 成功加载 {count} 个 {label} 节点 - {elapsed:.2f}秒")

        except Exception as e:
            logging.error(f"    ❌ [错误] 加载 {filename} 失败: {e}")
            tx.rollback()

    logging.info(f"✅ 所有节点加载完毕。")


def commit_relation_batch(tx, start_label, start_key, rel_type, end_label, end_key, batch):
    """(优化) 辅助函数：使用 UNWIND + 标签化 MATCH 批量提交关系"""
    # (优化) 这里的 MATCH (start:Label {key: ...}) 速度极快
    query = f"""
    UNWIND $batch AS row
    MATCH (start:{start_label} {{{start_key}: row.start_id}})
    MATCH (end:{end_label} {{{end_key}: row.end_id}})
    MERGE (start)-[r:{rel_type}]->(end)
    SET r += row.props
    """
    tx.run(query, batch=batch)


def load_relationships(graph):
    """(已优化) 批量加载所有关系"""
    logging.info("\n--- 步骤 3: 正在加载关系... ---")

    for filename, schema in REL_FILES.items():
        (start_label, start_key, rel_type, end_label, end_key, csv_start_col, csv_end_col) = schema

        path = DATA_DIR / filename
        if not path.exists():
            logging.warning(f"  [警告] 未找到文件: {path}，跳过 {rel_type} 关系。")
            continue

        logging.info(f"  > 正在加载 {filename} (关系: {rel_type})...")

        batch = []
        count = 0
        start_time = time.time()
        tx = graph.begin()

        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    start_id_val = row.get(csv_start_col)
                    end_id_val = row.get(csv_end_col)

                    if not start_id_val or not end_id_val:
                        logging.warning(
                            f"   [警告] {filename} 中缺少 '{csv_start_col}' 或 '{csv_end_col}' 的行: {row}。跳过。")
                        continue

                    rel_props = {k: v for k, v in row.items()
                                 if k not in [csv_start_col, csv_end_col] and v}

                    # (优化) 批处理数据包含 start/end ID 和属性
                    batch.append({
                        "start_id": start_id_val,
                        "end_id": end_id_val,
                        "props": rel_props
                    })

                    if len(batch) >= BATCH_SIZE:
                        commit_relation_batch(tx, start_label, start_key, rel_type, end_label, end_key, batch)
                        count += len(batch)
                        batch.clear()

            if batch:
                commit_relation_batch(tx, start_label, start_key, rel_type, end_label, end_key, batch)
                count += len(batch)

            tx.commit()
            elapsed = time.time() - start_time
            logging.info(f"    > 成功加载 {count} 条 {rel_type} 关系 - {elapsed:.2f}秒")

        except Exception as e:
            logging.error(f"    ❌ [错误] 加载 {filename} 失败: {e}")
            tx.rollback()

    logging.info(f"✅ 关系加载完毕。")


def show_statistics(graph):
    """显示导入统计"""
    logging.info("\n--- 步骤 4: 正在统计数据... ---")
    try:
        node_count = graph.run("MATCH (n) RETURN count(n) as count").data()[0]["count"]
        logging.info(f"✅ 总节点数: {node_count}")

        rel_count = graph.run("MATCH ()-[r]->() RETURN count(r) as count").data()[0]["count"]
        logging.info(f"✅ 总关系数: {rel_count}")

        # 各类型节点统计
        for _, (label, key) in ENTITY_FILES.items():
            count = graph.run(f"MATCH (n:{label}) RETURN count(n) as count").data()[0]["count"]
            if count > 0:
                logging.info(f"  {label}: {count}")
    except Exception as e:
        logging.error(f"❌ 统计数据时出错: {e}")


# ---------------------------------------------------------------
# 7. 主执行函数
# ---------------------------------------------------------------
if __name__ == "__main__":
    if not DATA_DIR.exists():
        logging.critical(f"❌ [严重错误] 数据集根目录未找到: {DATA_DIR}")
        sys.exit(1)

    overall_start = time.time()
    graph = None
    try:
        graph = get_neo4j_driver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

        # 步骤 0：清空数据库
        clear_database(graph)

        # (优化) 步骤 1：创建约束 (非常重要)
        create_constraints(graph)

        # 步骤 2：加载所有节点
        load_entities(graph)

        # 步骤 3：加载所有关系
        load_relationships(graph)

        # 步骤 4：显示统计
        show_statistics(graph)

        total_time = time.time() - overall_start
        logging.info("\n==========================================")
        logging.info(f"🎉 恭喜！知识图谱已成功导入 Neo4j。")
        logging.info(f"   总耗时: {total_time:.2f} 秒")
        logging.info("==========================================")

    except Exception as e:
        logging.critical(f"\n❌ [主程序异常]: {e}")
    finally:
        # py2neo 的 Graph 对象没有 .close() 方法，连接是自动管理的
        logging.info("\n✅ 脚本执行完毕。")