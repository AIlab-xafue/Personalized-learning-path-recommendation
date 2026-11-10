"""
版本：V10 (多维策略自适应版)
更新点：
1. 区分“能力不足失败”与“情绪焦虑失败”的应对策略
   - 太难 -> 降级学简单点
   - 太烦 -> 换视频/多模态资源
2. 增加“总体掌握度”的实时计算与显示
3. 改用 while 循环，确保跑完全程
"""
import json
import networkx as nx
import random
import time
import os
import re
import numpy as np

# T5 开关
USE_T5_MODEL = True
MODEL_PATH = os.environ.get("MOOCUBE_POLICY_MODEL", "models/zhuanjiamodel")

try:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    T5_AVAILABLE = True
except ImportError:
    T5_AVAILABLE = False
    USE_T5_MODEL = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# 1. 增强型用户画像 (含总体掌握度)
# ==========================================
class UserProfile:
    def __init__(self, user_id, total_path_len, ability=0.6, anxiety=0.3):
        self.user_id = user_id
        self.ability = ability
        self.anxiety = anxiety
        self.total_path_len = total_path_len # 路径总长度
        self.mastered_nodes = set() # 使用集合去重
        self.last_feedback = "PASS"

    @property
    def overall_mastery(self):
        """计算总体掌握度"""
        if self.total_path_len == 0: return 0.0
        return len(self.mastered_nodes) / self.total_path_len

    def update_metrics(self, feedback, current_node):
        self.last_feedback = feedback

        if "PASS" in feedback:
            if "REST" not in feedback: # 真正学懂了概念
                self.anxiety = max(0.1, self.anxiety - 0.05)
                self.ability = min(1.0, self.ability + 0.02)
                self.mastered_nodes.add(current_node)
            else: # 看了视频 (PASS_REST)
                self.anxiety = max(0.1, self.anxiety - 0.25)
                # 看视频也算某种程度的接触，但在本逻辑中暂不计入完全掌握，除非是PASS概念

        elif "FAIL" in feedback:
            # 失败：焦虑大幅上升
            self.anxiety = min(0.95, self.anxiety + 0.15)

    def estimate_time(self, current_difficulty=0.5):
        efficiency = self.ability * (1.2 - self.anxiety)
        base_time = 60
        real_time = (base_time * (1 + current_difficulty)) / max(0.1, efficiency)
        return int(real_time)

    def get_prompt_text(self):
        status = "良好"
        if self.anxiety > 0.7: status = "😰极度焦虑"
        elif self.last_feedback.startswith("FAIL"): status = "❌受挫"

        return (f"能力:{self.ability:.2f} | 焦虑:{self.anxiety:.2f} | "
                f"总体掌握度:{self.overall_mastery:.1%} | 状态:{status}")

# ==========================================
# 2. 图谱环境 (含难度系数 & 降级查找)
# ==========================================
class KnowledgeGraph:
    def __init__(self, json_path="kg_transition_cache1.json"):
        print(f"📂 加载图谱: {json_path} ...")
        self.G = nx.DiGraph()
        self.node_difficulty = {}

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for src in data.keys():
                self.G.add_node(src)
                random.seed(hash(src))
                # 难度 0.2 ~ 0.9
                self.node_difficulty[src] = round(0.2 + random.random() * 0.7, 2)
            self.adj = data
            print(f"✅ 图谱就绪")
        except FileNotFoundError:
            print("⚠️ 使用虚拟图谱")
            self.G.add_nodes_from(["模式识别", "近似解"])
        except Exception as e:
            print(f"⚠️ 图谱加载失败({e})，使用虚拟图谱")
            self.G.add_nodes_from(["模式识别", "近似解"])

    def get_difficulty(self, node):
        return self.node_difficulty.get(node, 0.5)

    def generate_personalized_path(self, start, end, length=12):
        if start == end: return [start]
        candidates = list(self.G.nodes())
        if start in candidates: candidates.remove(start)
        if end in candidates: candidates.remove(end)
        sample_len = min(len(candidates), length - 2)
        middle = random.sample(candidates, sample_len)
        return [start] + middle + [end]

    def find_easier_related_node(self, current_node, current_path):
        """寻找一个比当前节点简单的相关节点 (降级策略)"""
        curr_diff = self.get_difficulty(current_node)

        # 1. 尝试在路径历史中找一个非常简单的点 (复习)
        candidates = [n for n in current_path if self.get_difficulty(n) < curr_diff - 0.2]
        if candidates:
            return random.choice(candidates)

        # 2. 如果没找到，返回当前节点的“基础版” (逻辑模拟)
        # 在真实图谱中应该是找前驱节点，这里简化为返回自身，但Agent会标记为基础学习
        return current_node

# ==========================================
# 3. 模拟器 (细分失败类型)
# ==========================================
class StudentSimulator:
    def __init__(self, path, profile, kg):
        self.path = path
        self.profile = profile
        self.kg = kg
        self.curr_node = path[0]
        self.history = [self.curr_node]
        # 起点视为已掌握，避免短路径时掌握度长期为 0
        self.profile.mastered_nodes.add(self.curr_node)

    def step(self, action):
        node_name = action.split("(")[0].strip()
        res_type = action.split("(")[1].strip(")") if "(" in action else ""

        feedback = "ERROR"
        difficulty = self.kg.get_difficulty(node_name)

        # --- 成功情况 ---
        if node_name == self.path[-1] and "概念" in res_type:
            # 只有以概念形式掌握终点才算结束；结束前先更新状态与掌握度
            self.curr_node = node_name
            if node_name not in self.history:
                self.history.append(node_name)
            self.profile.update_metrics("PASS", node_name)
            return "GOAL_REACHED"

        if "视频" in res_type:
            # 视频资源容易消化，必定成功降焦虑
            feedback = "PASS_REST"

        elif node_name in self.kg.G.nodes():
            # --- 失败判定逻辑 ---

            # 1. 焦虑导致的心态崩盘 (Anxiety Failure)
            # 焦虑值越高，越容易心烦意乱学不进去
            if random.random() < (self.profile.anxiety * 0.8):
                feedback = "FAIL_ANXIOUS" # 太烦了

            # 2. 能力不足导致的硬伤 (Difficulty Failure)
            else:
                success_prob = self.profile.ability - (difficulty * 0.6) + 0.4
                if random.random() < success_prob:
                    self.curr_node = node_name
                    if node_name not in self.history: self.history.append(node_name)
                    feedback = "PASS"
                else:
                    feedback = "FAIL_HARD" # 太难了

        self.profile.update_metrics(feedback, node_name)
        return feedback

# ==========================================
# 4. 智能体 (双重策略路由)
# ==========================================
class T5ModelAgent:
    def __init__(self, correct_path, model_path, kg):
        self.path = correct_path
        self.kg = kg
        self.model_loaded = False
        if T5_AVAILABLE and USE_T5_MODEL:
            try:
                print(f"🤖 加载模型: {model_path}")
                self.tokenizer = AutoTokenizer.from_pretrained(model_path)
                self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
                self.model_loaded = True
            except: pass

    def generate(self, prompt, current_node, profile):
        # -----------------------------------------------
        # 🧠 核心策略逻辑 (对应您的要求)
        # -----------------------------------------------

        # 1. 应对“太烦了” (FAIL_ANXIOUS 或 高焦虑)
        # 策略：不换节点，换形式 (推荐视频)
        if profile.last_feedback == "FAIL_ANXIOUS" or profile.anxiety > 0.7:
            print(f"      💡 [策略] 检测到焦虑/厌倦 -> 切换多模态资源(视频)")
            return f"{current_node}(视频)"

        # 2. 应对“太难了” (FAIL_HARD)
        # 策略：换节点 (降级到简单点)
        if profile.last_feedback == "FAIL_HARD":
            easier_node = self.kg.find_easier_related_node(current_node, self.path)
            # 如果找不到更简单的，就推荐当前节点的基础概念
            if easier_node == current_node:
                print(f"      💡 [策略] 检测到困难 -> 推荐拆解基础概念")
                return f"{current_node}(视频)" # 降级为视频也是一种降低难度的方法
            else:
                print(f"      💡 [策略] 检测到困难 -> 降级推荐简单节点: {easier_node}")
                return f"{easier_node}(基础概念)"

        # 3. 正常推进
        # 找到路径上的下一个点
        try:
            curr_idx = self.path.index(current_node)
            next_node = self.path[curr_idx + 1] if curr_idx < len(self.path)-1 else current_node
        except:
            next_node = current_node

        return f"{next_node}(进阶概念)"

# ==========================================
# 主程序
# ==========================================
if __name__ == "__main__":
    print("="*60)
    print(f"🚀 实验启动 (V10 完美逻辑版)")
    print("="*60)

    kg_path = os.path.join(SCRIPT_DIR, "kg_transition_cache1.json")
    kg = KnowledgeGraph(kg_path)
    start_node, end_node = "模式识别", "近似解"

    # 设定路径长度 (12步)
    path = kg.generate_personalized_path(start_node, end_node, length=20)
    print(f"✅ 规划路径: {' -> '.join(path)}")

    # 初始化画像 (传入路径总长度，用于计算掌握度)
    student = UserProfile("Student_001", len(path), ability=0.55, anxiety=0.3)

    agent = T5ModelAgent(path, MODEL_PATH, kg)
    sim = StudentSimulator(path, student, kg)

    print("-" * 60)

    step = 0
    max_steps = 60 # 安全上限，防止死循环

    # 改用 while 循环，确保达成目标
    while step < max_steps:
        step += 1
        time.sleep(0.3)

        curr = sim.curr_node
        diff = kg.get_difficulty(curr)
        est_time = student.estimate_time(diff)

        # 获取包含“总体掌握度”的 Prompt
        prompt_metrics = student.get_prompt_text()
        full_prompt = f"当前:[{curr}] | 难度:{diff} | {prompt_metrics} | 预估:{est_time}分"

        print(f"\n[Step {step}]")
        print(f"   📊 状态: {full_prompt}")

        # Agent 决策
        action = agent.generate(full_prompt, curr, student)
        print(f"   🤖 Agent: {action}")

        # Simulator 反馈
        feedback = sim.step(action)

        if feedback == "GOAL_REACHED":
            print(f"   🎉 恭喜！达成学习目标！")
            print(f"   📈 最终掌握度: {student.overall_mastery:.1%}")
            break
        elif feedback == "PASS":
            print(f"   ✅ 学习成功")
        elif feedback == "PASS_REST":
            print(f"   ☕ 视频学习/休息 (焦虑↓↓)")
        elif feedback == "FAIL_HARD":
            print(f"   ❌ 学习失败 (难度过高)")
        elif feedback == "FAIL_ANXIOUS":
            print(f"   💢 学习失败 (心态焦虑)")

    if step >= max_steps:
        print("\n⚠️ 达到最大步数，实验强制结束。")
