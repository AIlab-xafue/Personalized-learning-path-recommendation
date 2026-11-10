# -----------------------------------------------------------------------------
# 【脚本 3: 运行推理 (2.深度检索特征.py)】
# 目的：(对应PPT 月3) 使用“步骤 2”中微调过的新模型，执行 RAG 推理
#
# 1. 运行前请确保已安装: pip install transformers sentencepiece neo4j
# 2. 请务必修改下方 "配置项" 部分
# -----------------------------------------------------------------------------

import os
import sys
# (使用 MT5 相关的正确类)
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from neo4j import GraphDatabase, basic_auth
import json

# ---------------------------------------------------------------
# 1. 配置项 (*** 请务必修改以下配置 ***)
# ---------------------------------------------------------------

# (修改我)
# ！！！(关键) 此处路径必须指向“步骤 2 (finetune_mt5.py)”的输出文件夹！！！
T5_MODEL_PATH = r"/T5_small/zhuanjiamodel"

# (修改我) Neo4j 数据库连接信息
NEO4J_URI = "bolt://localhost:7687"  # 您的 Neo4j URI
NEO4J_USER = "neo4j"  # 您的 Neo4j 用户名
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")  # ！！！您的 Neo4j 密码！！！


# ---------------------------------------------------------------
# 2. 辅助函数：连接 Neo4j (不变)
# ---------------------------------------------------------------
def get_neo4j_driver(uri, user, password):
    """初始化并验证 Neo4j 连接"""
    try:
        driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))
        driver.verify_connectivity()
        print(f"✅ Neo4j 连接成功 (URI: {uri})")
        return driver
    except Exception as e:
        print(f"\n❌ [严重错误] Neo4j 连接失败: {e}")
        print(f"!!! 请检查您的 NEO4J_URI, NEO4J_USER, 和 NEO4J_PASSWORD 是否正确。")
        sys.exit(1)


# ---------------------------------------------------------------
# 3. 核心功能：RAG 检索 (全景上下文) (不变)
# ---------------------------------------------------------------
def retrieve_full_context_from_neo4j(driver, user_id, target_concept_name):
    """
    (此函数不变)
    从 Neo4j 检索 RAG 所需的"全景上下文"
    """

    print(f"\n--- 步骤 1: 正在为用户 '{user_id}' 检索全景上下文 ---")

    facts = {
        "user_id": user_id,
        "target": target_concept_name,
        "profile": {},
        "known_concepts": [],
        "missing_prereqs": [],
        "available_resources": {}
    }

    with driver.session() as session:
        # --- 查询 1: 获取学生画像 和 已知技能 ---
        query_1 = """
        MATCH (u:User {id: $user_id})
        WITH u
        OPTIONAL MATCH (u)-[:USER_COURSE]->(course:Course)
        WITH u, collect(DISTINCT course) AS courses
        OPTIONAL MATCH (u)-[:USER_VIDEO]->(video:Video)
        WITH u, courses, collect(DISTINCT video) AS videos
        OPTIONAL MATCH (u)-[:USER_COURSE|USER_VIDEO]->(resource)
        OPTIONAL MATCH (resource)-[:COURSE_CONCEPT|VIDEO_CONCEPT]->(concept:Concept)
        WITH u, courses, videos, collect(DISTINCT concept.name) AS known_concepts
        RETURN 
            u.gender AS gender, 
            u.province AS province,
            [c IN courses | c.name] AS course_history,
            [v IN videos | v.name] AS video_history,
            known_concepts
        """
        profile_data = session.run(query_1, user_id=user_id).single()

        if not profile_data:
            print(f"❌ [错误] Neo4j 中未找到 User ID: '{user_id}'")
            return None

        facts["profile"] = {
            "gender": profile_data["gender"],
            "province": profile_data["province"],
            "course_history": profile_data["course_history"],
            "video_history": profile_data["video_history"]
        }
        facts["known_concepts"] = [c for c in profile_data["known_concepts"] if c is not None]
        print("  > 步骤 1a: 获取学生画像... 完成")
        print(f"  > 步骤 1b: 推断已知技能... 完成 (共 {len(facts['known_concepts'])} 个)")

        # --- 查询 2: 获取缺失的先修路径 ---
        query_2 = """
        MATCH (target:Concept {name: $target_name})
        MATCH (prereq:Concept)-[:PREREQUISITE*1..5]->(target)
        WHERE 
            NOT prereq.name IN $known_concepts
        AND 
            NOT EXISTS {
              MATCH (k:Concept)
              WHERE k.name IN $known_concepts
              AND (prereq)-[:PREREQUISITE*]->(k)
            }
        WITH prereq, target
        MATCH p = (prereq)-[:PREREQUISITE*]->(target)
        RETURN prereq.name AS missing_concept, min(length(p)) AS dist_to_target
        ORDER BY dist_to_target DESC 
        """
        result = session.run(query_2,
                             target_name=target_concept_name,
                             known_concepts=facts["known_concepts"])

        missing_concepts_ordered = [r["missing_concept"] for r in result]
        unique_missing_concepts = list(dict.fromkeys(missing_concepts_ordered))
        facts["missing_prereqs"] = unique_missing_concepts

        if not facts["missing_prereqs"] and target_concept_name not in facts["known_concepts"]:
            facts["missing_prereqs"] = [target_concept_name]

        print(f"  > 步骤 1c: 检索缺失的先修课... 完成 (共 {len(facts['missing_prereqs'])} 个)")

        # --- 查询 3: 获取可用资源 ---
        concepts_to_find_resources = facts["missing_prereqs"]
        if not concepts_to_find_resources and target_concept_name not in facts["known_concepts"]:
            concepts_to_find_resources = [target_concept_name]
        elif not concepts_to_find_resources and target_concept_name in facts["known_concepts"]:
            concepts_to_find_resources = []

        if concepts_to_find_resources:
            # (限制资源检索数量)
            query_3 = """
            UNWIND $missing_concepts[..5] AS concept_name
            MATCH (c:Concept {name: concept_name})
            OPTIONAL MATCH (v:Video)-[:VIDEO_CONCEPT]->(c)
            WITH c, collect(DISTINCT v.name)[..3] AS videos
            OPTIONAL MATCH (co:Course)-[:COURSE_CONCEPT]->(c)
            WITH c, videos, co
            LIMIT 2 
            OPTIONAL MATCH (t:Teacher)-[:TEACHER_COURSE]->(co)
            WITH c, videos, co, collect(DISTINCT t.name) AS teachers
            WITH c, videos, collect(DISTINCT {course: co.name, teachers: teachers}) AS courses
            OPTIONAL MATCH (p:Paper)-[:CONCEPT_PAPER]->(c)
            WITH c, videos, courses, collect(DISTINCT p.name)[..2] AS papers
            RETURN 
                c.name AS concept, 
                videos, 
                [item IN courses WHERE item.course IS NOT NULL] AS courses,
                papers
            """
            result = session.run(query_3, missing_concepts=concepts_to_find_resources)
            for r in result:
                facts["available_resources"][r["concept"]] = {
                    "videos": r["videos"],
                    "courses": r["courses"],
                    "papers": r["papers"]
                }
        print("  > 步骤 1d: 检索可用资源 (已限制数量)... 完成")

    return facts


# ---------------------------------------------------------------
# 4. 辅助函数：格式化 *中文* Prompt (不变)
# ---------------------------------------------------------------
def format_prompt_for_t5_ZH(facts: dict):
    """
    (此函数不变)
    将从 Neo4j 检索到的结构化事实，转换为 T5-small 能理解的纯文本 Prompt。
    """

    print("\n--- 步骤 2: 正在构建个性化 RAG Prompt ---")

    task_prefix = "generate_learning_path: "
    profile = facts["profile"]
    student_info = (
        f"学生ID: {facts['user_id']}\n"
        f"已知技能: (已省略 {len(facts['known_concepts'])} 个技能)\n"
        f"学习历史: 已学 {len(profile['course_history'])} 门课程, "
        f"观看过 {len(profile['video_history'])} 个视频。\n"
        f"个性化偏好: 假设该生偏好'视频'资源多于'课程'或'论文'。"
    )

    task_description = ""
    if not facts["missing_prereqs"]:
        knowledge_facts = (
            f"学习目标: {facts['target']}\n"
            f"缺失的先修概念: 无。该生已掌握所有先修知识。"
        )
        task_description = (
            f"该学生已具备学习【{facts['target']}】的所有条件。"
            f"请根据【可用资源】和【学生画像】(优先推荐'视频')，"
            f"为该学生推荐学习【{facts['target']}】的入门资源。"
        )
    else:
        knowledge_facts = (
            f"学习目标: {facts['target']}\n"
            f"缺失的先修概念 (必须按此顺序): {', '.join(facts['missing_prereqs'])}"
        )
        task_description = (
            f"请根据以上【知识图谱事实】和【可用资源】，"
            f"并结合【学生画像】(优先推荐'视频')，"
            f"为该学生生成一个清晰、可执行的学习路径。"
        )

    resource_text_list = []
    concepts_to_show_resources = facts["missing_prereqs"]
    if not concepts_to_show_resources:
        concepts_to_show_resources = [facts["target"]]

    if not facts["available_resources"]:
        resource_text_list.append("无特定资源信息。")
    else:
        for concept_name in concepts_to_show_resources:
            resources = facts["available_resources"].get(concept_name)
            if not resources:
                resource_text_list.append(f"对于概念 '{concept_name}': (无可用资源)")
                continue
            resource_text_list.append(f"对于概念 '{concept_name}':")
            if resources["videos"]:
                resource_text_list.append(f"  - 可用视频 (示例): {', '.join(resources['videos'])}")
            if resources["courses"]:
                course_texts = []
                for c in resources['courses']:
                    teacher_str = f"(教师: {c['teachers'][0]})" if c['teachers'] and c['teachers'][0] else ""
                    course_texts.append(f"{c['course']} {teacher_str}")
                resource_text_list.append(f"  - 可用课程 (示例): {'; '.join(course_texts)}")
            if resources["papers"]:
                resource_text_list.append(f"  - 可用论文 (示例): {', '.join(resources['papers'])}")

    available_resources = "\n".join(resource_text_list)

    final_prompt = (
        f"{task_prefix}\n"
        f"--- 任务 ---\n"
        f"{task_description}\n\n"
        f"--- 学生画像 (个性化依据) ---\n{student_info}\n\n"
        f"--- 知识图谱事实 (必须遵守) ---\n{knowledge_facts}\n\n"
        f"--- 可用资源 (用于规划) ---\n{available_resources}"
    )

    return final_prompt


# ---------------------------------------------------------------
# 5. 辅助函数：T5 生成
# ---------------------------------------------------------------
def generate_path_with_t5(prompt_text, model_path):
    """
    (此函数不变)
    加载您 *微调过的* MT5-small 模型并根据 Prompt 生成路径。
    """
    print(f"\n--- 步骤 3: 正在加载 *微调过的* MT5-small 模型 ---")
    if not os.path.isdir(model_path):
        print(f"❌ [错误] T5 模型路径未找到: '{model_path}'")
        print("!!! 请检查 T5_MODEL_PATH 变量是否指向 'my_finetuned_mt5_small' 文件夹。")
        sys.exit(1)

    try:
        # (使用 MT5 相关的正确类)
        tokenizer = MT5TokenizerFast.from_pretrained(model_path)
        model = MT5ForConditionalGeneration.from_pretrained(model_path)

    except Exception as e:
        print(f"❌ [错误] 加载 MT5 模型失败: {e}")
        sys.exit(1)

    print(f"MT5-small (已微调) 模型加载成功于: {model_path}")
    print("MT5-small 正在根据 RAG Prompt 生成路径...")

    inputs = tokenizer(prompt_text, return_tensors="pt", max_length=1024, truncation=True)

    output_sequences = model.generate(
        input_ids=inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        max_length=256,
        num_beams=5,
        early_stopping=True,
        repetition_penalty=1.2
    )

    generated_path = tokenizer.decode(output_sequences[0], skip_special_tokens=True)
    return generated_path


# ---------------------------------------------------------------
# 6. 主执行脚本
# ---------------------------------------------------------------
if __name__ == "__main__":

    # (模拟) 定义一个学生和他的目标
    TEST_USER_ID = "U_10384829"  # 替换为您图谱中真实存在的 User ID
    TEST_TARGET = "无线局域网"  # 替换为您图谱中真实存在的 Concept Name

    neo4j_driver = None
    try:
        # 1. 连接数据库
        neo4j_driver = get_neo4j_driver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

        # 2. RAG: 检索全景上下文
        facts = retrieve_full_context_from_neo4j(neo4j_driver, TEST_USER_ID, TEST_TARGET)

        if facts:
            # 3. Format: 构建 Prompt
            final_prompt = format_prompt_for_t5_ZH(facts)
            print(f"--- 最终生成的 Prompt (共 {len(final_prompt)} 字符): ---")
            print(final_prompt)
            print("------------------------------------------\n")

            # 4. Generate: T5 生成路径
            # (确保 T5_MODEL_PATH 指向您微调后的模型)
            generated_path = generate_path_with_t5(final_prompt, T5_MODEL_PATH)

            # 5. 显示结果
            print("\n==========================================")
            print("      MT5-small (已微调) 生成的个性化学习路径")
            print("==========================================")
            cleaned_path = generated_path.replace("<pad>", "").replace("<extra_id_0>", "").strip()
            print(cleaned_path)

    except Exception as e:
        print(f"\n❌ [主程序异常]: {e}")
    finally:
        # 6. 确保关闭数据库连接
        if neo4j_driver:
            neo4j_driver.close()
            print("\n✅ Neo4j 连接已关闭。")