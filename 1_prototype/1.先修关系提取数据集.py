import os
import sys
import json
import random
from neo4j import GraphDatabase, basic_auth

# ---------------------------------------------------------------
# 1. 配置项
# ---------------------------------------------------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")

# (重要) 增加训练样本数量，用于正式微调
NUM_TRAINING_SAMPLES = 3000
OUTPUT_FILE = "training_data_final.jsonl"


# ---------------------------------------------------------------
# 2. 核心功能：利用“双重先修关系”检索
# ---------------------------------------------------------------
def get_neo4j_driver():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
        return driver
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)


def retrieve_rich_context(driver, user_id, target_concept):
    """
    从 Neo4j 检索全景上下文。
    关键升级：同时利用 PREREQUISITE 和 PREREQUISITE_PRED 关系。
    """
    facts = {
        "user_id": user_id,
        "target": target_concept,
        "profile": {},
        "known_concepts": [],
        "missing_prereqs": [],
        "available_resources": {}
    }

    with driver.session() as session:
        # 1. 获取画像 (不变)
        q_profile = """
        MATCH (u:User {id: $uid})
        OPTIONAL MATCH (u)-[:USER_COURSE]->(c:Course)
        OPTIONAL MATCH (u)-[:USER_VIDEO]->(v:Video)
        OPTIONAL MATCH (c)-[:COURSE_CONCEPT]->(kc:Concept)
        RETURN 
            count(DISTINCT c) as course_cnt,
            count(DISTINCT v) as video_cnt,
            collect(DISTINCT kc.name) as known
        """
        res = session.run(q_profile, uid=user_id).single()
        if not res: return None

        facts["profile"] = {"course_cnt": res["course_cnt"], "video_cnt": res["video_cnt"]}
        facts["known_concepts"] = res["known"]

        # 2. (关键升级) 获取先修路径
        # 同时查找 人工标注(PREREQUISITE) 和 算法预测(PREREQUISITE_PRED) 的关系
        q_prereq = """
        MATCH (target:Concept {name: $target})
        // 查找 1 到 3 跳的先修路径，允许两种关系类型
        MATCH p = (prereq)-[:PREREQUISITE|PREREQUISITE_PRED*1..3]->(target)
        WHERE NOT prereq.name IN $known
        // 按路径长度排序，确保先学基础的
        RETURN DISTINCT prereq.name as name, length(p) as dist
        ORDER BY dist DESC
        LIMIT 5
        """
        res = session.run(q_prereq, target=target_concept, known=facts["known_concepts"])
        facts["missing_prereqs"] = [r["name"] for r in res]

        # 如果没有缺失先修课，目标本身就是下一步
        if not facts["missing_prereqs"] and target_concept not in facts["known_concepts"]:
            facts["missing_prereqs"] = [target_concept]

        # 3. 获取资源 (不变)
        concepts_to_find = facts["missing_prereqs"]
        if concepts_to_find:
            q_res = """
            UNWIND $concepts as c_name
            MATCH (c:Concept {name: c_name})
            OPTIONAL MATCH (v:Video)-[:VIDEO_CONCEPT]->(c)
            OPTIONAL MATCH (co:Course)-[:COURSE_CONCEPT]->(c)
            RETURN c.name as c, collect(DISTINCT v.name)[..3] as vs, collect(DISTINCT co.name)[..2] as cos
            """
            res = session.run(q_res, concepts=concepts_to_find)
            for r in res:
                facts["available_resources"][r["c"]] = {"videos": r["vs"], "courses": r["cos"]}

    return facts


def format_prompt(facts):
    """构建 RAG Prompt"""
    # 模拟一个随机偏好，训练模型适应不同需求
    pref_type = random.choice(["视频", "课程"])

    profile_txt = (
        f"学生ID: {facts['user_id']}\n"
        f"已知技能数: {len(facts['known_concepts'])}\n"
        f"偏好: 优先推荐'{pref_type}'"
    )

    knowledge_txt = f"学习目标: {facts['target']}\n需掌握概念序列: {', '.join(facts['missing_prereqs'])}"

    res_txt = ""
    for c in facts["missing_prereqs"]:
        res = facts["available_resources"].get(c)
        if res:
            v_str = ",".join(res['videos'])
            c_str = ",".join(res['courses'])
            res_txt += f"概念'{c}': [视频] {v_str}; [课程] {c_str}\n"

    return (
        f"--- 任务 ---\n请为该学生规划学习路径。\n\n"
        f"--- 学生画像 ---\n{profile_txt}\n\n"
        f"--- 知识图谱事实 ---\n{knowledge_txt}\n\n"
        f"--- 可用资源 ---\n{res_txt}"
    ), pref_type


def create_gold_path(facts, pref_type):
    """
    生成“黄金标准”路径。
    利用刚导入的先修关系构建逻辑。
    """
    steps = []
    for i, c in enumerate(facts["missing_prereqs"]):
        res = facts["available_resources"].get(c)
        if not res:
            steps.append(f"{i + 1}. [自学] {c}")
            continue

        # 根据模拟的偏好选择资源
        if pref_type == "视频" and res["videos"]:
            steps.append(f"{i + 1}. [视频] {c}: 观看 '{res['videos'][0]}'")
        elif res["courses"]:
            steps.append(f"{i + 1}. [课程] {c}: 学习 '{res['courses'][0]}'")
        elif res["videos"]:  # 如果偏好课程但没有，回退到视频
            steps.append(f"{i + 1}. [视频] {c}: 观看 '{res['videos'][0]}'")
        else:
            steps.append(f"{i + 1}. [概念] {c}")

    return " -> ".join(steps)


# ---------------------------------------------------------------
# 3. 主程序
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 开始构建基于完整先修关系的训练集...")
    driver = get_neo4j_driver()

    # 1. 获取有意义的训练样本 (User -> 未学课程的概念)
    q_samples = """
    MATCH (u:User)
    MATCH (c:Course) WHERE NOT (u)-[:USER_COURSE]->(c)
    MATCH (c)-[:COURSE_CONCEPT]->(t:Concept)
    RETURN DISTINCT u.id as uid, t.name as target
    LIMIT $limit
    """

    with driver.session() as session:
        print("正在查询样本对...")
        samples = list(session.run(q_samples, limit=NUM_TRAINING_SAMPLES))

    print(f"获取到 {len(samples)} 个样本，开始生成 Prompt...")

    count = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for s in samples:
            facts = retrieve_rich_context(driver, s["uid"], s["target"])
            if not facts or not facts["missing_prereqs"]: continue

            prompt, pref = format_prompt(facts)
            output = create_gold_path(facts, pref)

            f.write(json.dumps({"input": prompt, "output": output}, ensure_ascii=False) + "\n")
            count += 1
            if count % 100 == 0: print(f"已生成 {count} 条...", end="\r")

    print(f"\n✅ 完成！已生成 {count} 条高质量训练数据至 {OUTPUT_FILE}")
    print("👉 下一步：请运行 'finetune_mt5.py' 使用此文件重新训练模型。")
    driver.close()