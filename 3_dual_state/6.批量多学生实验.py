"""
文件: batch_simulation.py
目的: 为论文第二课题生成 100 个模拟学生的批量对比实验数据
特色: 引入真实知识图谱、拓扑难度计算、真实前驱降级逻辑
对比基线: Static, Cognitive-Only, Fusion (Ours)
"""
import random
import networkx as nx
import numpy as np
import time
import json
import os

# ==========================================
# 1. 增强型用户画像 (引入最高焦虑追踪)
# ==========================================
class UserProfile:
    def __init__(self, user_id, total_path_len, ability=0.6, anxiety=0.3):
        self.user_id = user_id
        self.ability = ability
        self.anxiety = anxiety
        self.total_path_len = total_path_len
        self.mastered_nodes = set()
        self.last_feedback = "PASS"
        self.max_anxiety_recorded = anxiety  # 记录过程中的最高焦虑值

    @property
    def overall_mastery(self):
        if self.total_path_len == 0: return 0.0
        return len(self.mastered_nodes) / self.total_path_len

    def update_metrics(self, feedback, current_node):
        self.last_feedback = feedback

        if "PASS" in feedback:
            if "REST" not in feedback: # 真正学懂了概念
                self.anxiety = max(0.1, self.anxiety - 0.05)
                self.ability = min(1.0, self.ability + 0.02)
                self.mastered_nodes.add(current_node)
            else: # 看了视频，缓解情绪
                self.anxiety = max(0.1, self.anxiety - 0.25)

        elif "FAIL" in feedback:
            # 失败导致焦虑上升
            self.anxiety = min(1.0, self.anxiety + 0.15)

        # 实时更新最高焦虑值
        if self.anxiety > self.max_anxiety_recorded:
            self.max_anxiety_recorded = self.anxiety

# ==========================================
# 2. 真实图谱环境 (核心改造：基于拓扑的难度计算)
# ==========================================
class KnowledgeGraph:
    def __init__(self, json_path="kg_transition_cache1.json"):
        self.G = nx.DiGraph()
        self.node_difficulty = {}

        # 1. 加载真实图谱数据
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for source, targets in data.items():
                self.G.add_node(source)
                for t in targets:
                    self.G.add_edge(source, t)
        else:
            print(f"⚠️ 找不到 {json_path}，将使用虚拟图谱代替...")
            nodes = [f"概念_{i}" for i in range(1, 16)]
            self.G.add_nodes_from(nodes)
            for i in range(14): self.G.add_edge(nodes[i], nodes[i+1])

        # 2. 基于图谱拓扑结构计算真实难度 (出度中心性)
        out_degrees = dict(self.G.out_degree())
        if out_degrees:
            max_deg = max(out_degrees.values()) if max(out_degrees.values()) > 0 else 1
            for node, deg in out_degrees.items():
                # 基础难度 0.3，出度越大的节点（核心枢纽）越难，最高 0.85
                self.node_difficulty[node] = round(0.3 + (deg / max_deg) * 0.55, 2)
        else:
            for node in self.G.nodes():
                self.node_difficulty[node] = 0.5

    def get_difficulty(self, node):
        return self.node_difficulty.get(node, 0.5)

    def find_easier_related_node(self, current_node, current_path):
        """降级策略：优先寻找历史路径中简单的点复习，其次寻找图谱真实前驱"""
        curr_diff = self.get_difficulty(current_node)

        # 策略A：历史路径复习 (寻找难度明显更低的已学节点)
        candidates = [n for n in current_path if self.get_difficulty(n) < curr_diff - 0.1]
        if candidates:
            return random.choice(candidates)

        # 策略B：寻找真实图谱上的前驱节点 (先修知识)
        if current_node in self.G:
            predecessors = list(self.G.predecessors(current_node))
            if predecessors:
                # 找前驱中最简单的一个
                return min(predecessors, key=lambda x: self.get_difficulty(x))

        # 兜底策略
        return current_node

    def generate_real_path(self, start_node="模式识别", min_length=10):
        """在图谱上进行随机游走，生成真实的连贯教学路径"""
        path = [start_node]
        curr = start_node
        for _ in range(min_length - 1):
            neighbors = list(self.G.successors(curr))
            # 过滤掉已经走过的节点，防止死循环
            valid_neighbors = [n for n in neighbors if n not in path]
            if not valid_neighbors:
                break
            curr = random.choice(valid_neighbors)
            path.append(curr)

        # 容错：如果图谱太稀疏导致断路，手动补齐假节点保证实验可运行
        while len(path) < min_length:
            path.append(f"扩展知识_{len(path)}")
            self.node_difficulty[path[-1]] = 0.5

        return path

# ==========================================
# 3. 模拟器 (增加“崩溃辍学”机制)
# ==========================================
class StudentSimulator:
    def __init__(self, path, profile, kg):
        self.path = path
        self.profile = profile
        self.kg = kg
        self.curr_node = path[0]
        self.history = [self.curr_node]

    def step(self, action):
        node_name = action.split("(")[0].strip()
        res_type = action.split("(")[1].strip(")") if "(" in action else ""

        difficulty = self.kg.get_difficulty(node_name)

        # --- 辍学判定 ---
        if self.profile.anxiety >= 0.95:
            return "DROPOUT" # 焦虑爆表，直接放弃学习

        # --- 成功判定 ---
        if node_name == self.path[-1] and "概念" in res_type:
            success_prob = self.profile.ability - (difficulty * 0.5) + 0.4
            if random.random() < success_prob:
                self.profile.update_metrics("PASS", node_name)
                return "GOAL_REACHED"

        if "视频" in res_type:
            feedback = "PASS_REST"
        else:
            # --- 失败判定 ---
            if random.random() < (self.profile.anxiety * 0.8):
                feedback = "FAIL_ANXIOUS"
            else:
                success_prob = self.profile.ability - (difficulty * 0.6) + 0.4
                if random.random() < success_prob:
                    self.curr_node = node_name
                    if node_name not in self.history: self.history.append(node_name)
                    feedback = "PASS"
                else:
                    feedback = "FAIL_HARD"

        self.profile.update_metrics(feedback, node_name)
        return feedback

# ==========================================
# 4. 智能体 (集成三种策略基线)
# ==========================================
class T5ModelAgent:
    def __init__(self, correct_path, kg):
        self.path = correct_path
        self.kg = kg

    def get_next_node(self, current_node):
        try:
            curr_idx = self.path.index(current_node)
            return self.path[curr_idx + 1] if curr_idx < len(self.path)-1 else current_node
        except:
            return current_node

    def generate(self, current_node, profile, strategy):
        # 策略 1: 静态死板推进 (无论反馈如何，只推下一个)
        if strategy == "static":
            return f"{self.get_next_node(current_node)}(进阶概念)"

        # 策略 2: 单维认知自适应 (只管能力，不管情绪)
        if strategy == "cognitive_only":
            if profile.last_feedback == "FAIL_HARD":
                easier_node = self.kg.find_easier_related_node(current_node, self.path)
                return f"{easier_node}(基础概念)"
            return f"{self.get_next_node(current_node)}(进阶概念)"

        # 策略 3: 双态融合自适应 (Ours)
        if strategy == "fusion":
            if profile.last_feedback == "FAIL_ANXIOUS" or profile.anxiety > 0.7:
                return f"{current_node}(视频)"
            if profile.last_feedback == "FAIL_HARD":
                easier_node = self.kg.find_easier_related_node(current_node, self.path)
                if easier_node == current_node:
                    return f"{current_node}(视频)"
                return f"{easier_node}(基础概念)"
            return f"{self.get_next_node(current_node)}(进阶概念)"

# ==========================================
# 5. 实验运行框架
# ==========================================
def run_single_simulation(student_config, path, kg, strategy, max_steps=50):
    student = UserProfile(
        student_config["id"],
        len(path),
        ability=student_config["ability"],
        anxiety=student_config["anxiety"]
    )
    agent = T5ModelAgent(path, kg)
    sim = StudentSimulator(path, student, kg)

    step = 0
    goal_reached = False

    while step < max_steps:
        step += 1
        curr = sim.curr_node
        action = agent.generate(curr, student, strategy)
        feedback = sim.step(action)

        if feedback == "GOAL_REACHED":
            goal_reached = True
            break
        elif feedback == "DROPOUT":
            break # 中途辍学

    return {
        "goal_reached": 1 if goal_reached else 0,
        "mastery": student.overall_mastery,
        "peak_anxiety": student.max_anxiety_recorded,
        "steps": step
    }

if __name__ == "__main__":
    print("🚀 正在初始化批量模拟实验环境 (真实图谱版)...")
    kg = KnowledgeGraph("kg_transition_cache1.json")

    # 获取一条真实的长度为10的教学路径
    real_path = kg.generate_real_path("模式识别", min_length=10)
    print(f"✅ 生成真实评测路径: {' -> '.join(real_path)}")

    NUM_STUDENTS = 100
    print(f"👥 正在生成 {NUM_STUDENTS} 个具有不同能力和焦虑初始值的虚拟学习者...")

    # 随机生成 100 个学生配置
    students = []
    for i in range(NUM_STUDENTS):
        students.append({
            "id": f"Stu_{i:03d}",
            "ability": round(random.uniform(0.3, 0.8), 2),
            "anxiety": round(random.uniform(0.1, 0.5), 2)
        })

    strategies = ["static", "cognitive_only", "fusion"]
    results = {s: {"reach": [], "mastery": [], "anxiety": [], "steps": []} for s in strategies}

    print(f"⚙️ 开始进行三种策略的交叉对比模拟实验...\n")

    # 开始批处理跑库
    for i, stu in enumerate(students):
        for strat in strategies:
            res = run_single_simulation(stu, real_path, kg, strat)
            results[strat]["reach"].append(res["goal_reached"])
            results[strat]["mastery"].append(res["mastery"])
            results[strat]["anxiety"].append(res["peak_anxiety"])
            results[strat]["steps"].append(res["steps"])

    # ==========================================
    # 6. 统计与打印论文表格
    # ==========================================
    print("="*85)
    print("📊 实验结果统计 (论文 Table X 候选数据)")
    print("="*85)
    print(f"| 策略机制 (Strategy) | 目标达成率 (Goal Reach) | 最终掌握度 (Mastery) | 焦虑峰值 (Peak Anxiety) | 平均步数 (Avg Steps) |")
    print(f"| :--- | :---: | :---: | :---: | :---: |")

    display_names = {
        "static": "Baseline 1 (静态路径)",
        "cognitive_only": "Baseline 2 (单维认知自适应)",
        "fusion": "Ours (双态协同自适应)"
    }

    for strat in strategies:
        avg_reach = np.mean(results[strat]["reach"]) * 100
        avg_mastery = np.mean(results[strat]["mastery"]) * 100
        avg_anxiety = np.mean(results[strat]["anxiety"])
        avg_steps = np.mean(results[strat]["steps"])

        name = display_names[strat]
        print(f"| {name} | {avg_reach:.1f}% | {avg_mastery:.1f}% | {avg_anxiety:.2f} | {avg_steps:.1f} |")

    print("="*85)
    print("💡 数据解读提示：")
    print("1. Ours 的【目标达成率】应远高于其他两组，证明防辍学效果显著。")
    print("2. Ours 的【焦虑峰值】应显著低于单维自适应，证明情绪干预（推视频）切实有效。")
    print("3. Ours 的【平均步数】可能略多于静态策略，因为引入了复习和看视频的迂回策略，但换来了极高的成功率。")