import json
import networkx as nx
import random
import time
import os
import numpy as np


# ==========================================
# 1. 增强型用户画像 (核心个性化模块)
# ==========================================
class EnhancedUserProfile:
    def __init__(self):
        # 初始属性
        self.ability = 0.60  # 学习能力 (0.1 - 1.0)
        self.anxiety = 0.30  # 初始焦虑 (0.0 - 1.0)
        self.base_efficiency = 0.8  # 基础效率

    def update(self, feedback):
        """根据学习反馈动态调整指标"""
        if "PASS" in feedback:
            # 成功：焦虑下降，能力微涨
            self.anxiety = max(0.1, self.anxiety - 0.05)
            self.ability = min(1.0, self.ability + 0.01)
        elif "FAIL" in feedback:
            # 失败：焦虑上升
            self.anxiety = min(0.9, self.anxiety + 0.15)
        elif "SHIFT" in feedback or "REST" in feedback:
            # 休息/视频：焦虑大幅下降
            self.anxiety = max(0.1, self.anxiety - 0.2)

    @property
    def efficiency(self):
        """实时效率 = 基础效率 * 能力 * (1 - 焦虑影响)"""
        # 焦虑越高，效率越低
        return round(self.base_efficiency * self.ability * (1.0 - self.anxiety * 0.5), 2)

    @property
    def estimated_time(self):
        """预估时间 = 基础耗时 / 效率"""
        base_time = 60  # 假设每个知识点平均需要60分钟
        # 效率越低，时间越长；加上一点随机波动模拟真实感
        time = int(base_time / max(0.1, self.efficiency) * random.uniform(0.9, 1.1))
        return min(300, time)  # 上限300分钟

    def get_status_desc(self):
        """生成个性化状态描述"""
        if self.anxiety > 0.6: return "😰 焦虑较高"
        if self.anxiety > 0.4: return "😐 轻度紧张"
        return "✅ 状态良好"


# ==========================================
# 2. 智能图谱环境 (极速版 - 保持不变)
# ==========================================
class SmartKG:
    def __init__(self, json_path="kg_transition_cache1.json"):
        print(f"📂 [系统启动] 加载图谱: {json_path} ...")
        self.G = nx.DiGraph()
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for src in data.keys():
                self.G.add_node(src)
            # 假定全连通，逻辑上存在边
            self.adj_data = data
            print(f"✅ 图谱加载成功！包含 {self.G.number_of_nodes()} 个节点。")
        except FileNotFoundError:
            print("❌ 错误：找不到文件！")
            exit()

    def find_long_path_fast(self, start, end, length=9):
        print(f"🔍 [极速模式] 正在构建 {start} -> {end} 的 {length} 步路径...")
        all_nodes = list(self.G.nodes())
        candidates = [n for n in all_nodes if n != start and n != end]

        # 随机采样中间点
        if len(candidates) < length - 2:
            return [start, end]
        middle_nodes = random.sample(candidates, length - 2)
        return [start] + middle_nodes + [end]


# ==========================================
# 3. 模拟器 (集成画像更新)
# ==========================================
class RealDataSimulator:
    def __init__(self, kg, path_script, user_profile):
        self.kg = kg
        self.path_script = path_script
        self.user_profile = user_profile  # 绑定用户画像
        self.target = path_script[-1]
        self.current_node = path_script[0]
        self.history = [self.current_node]
        self.step_count = 0

        # 生成先修依赖
        self.prerequisites = {}
        for i in range(1, len(path_script)):
            self.prerequisites[path_script[i]] = path_script[i - 1]
        print(f"⚙️ [模拟器] 初始化完成，共 {len(path_script)} 个知识点")

    def step(self, action_text):
        self.step_count += 1

        # 清洗动作
        if "(" in action_text:
            clean_node = action_text.split("(")[0].strip()
            res_type = action_text.split("(")[1].strip(")")
        else:
            clean_node = action_text.strip()
            res_type = ""

        # 结果判定
        result = "ERROR"

        # 1. 终点检查
        if clean_node == self.target:
            required = self.prerequisites.get(clean_node)
            if required and required not in self.history:
                result = f"FAIL_GAP:{required}"
            else:
                result = "GOAL_REACHED"

        # 2. 视频/休息处理
        elif "video" in res_type.lower() or "视频" in res_type:
            result = "PASS_REST"

        # 3. 知识断层检查
        elif clean_node in self.path_script:
            required_pre = self.prerequisites.get(clean_node)
            if required_pre and required_pre not in self.history:
                result = f"FAIL_GAP:{required_pre}"
            else:
                self.current_node = clean_node
                if clean_node not in self.history: self.history.append(clean_node)
                result = "PASS"

        # 4. 正常学习
        elif clean_node in self.kg.G.nodes():
            self.current_node = clean_node
            if clean_node not in self.history: self.history.append(clean_node)
            result = "PASS"

        # --- 关键：更新用户画像数值 ---
        self.user_profile.update(result)

        return result


# ==========================================
# 4. 智能体 (策略路由)
# ==========================================
class SmartAgent:
    def __init__(self, correct_path):
        self.policy_map = {}
        # 正常策略: i -> i+1
        for i in range(len(correct_path) - 1):
            self.policy_map[correct_path[i]] = correct_path[i + 1]

        # 捣乱策略: 偶尔跳步，制造 FAIL_GAP 来展示焦虑上升
        for i in range(0, len(correct_path) - 3, 3):
            self.policy_map[correct_path[i]] = correct_path[i + 2]

    def generate(self, prompt, current_node):
        # 1. 优先响应视频需求 (焦虑高时)
        if "视频" in prompt:
            return f"{current_node}(视频)"

        # 2. 响应补课需求
        if "补课" in prompt:
            try:
                missing = prompt.split("缺")[1].split(")")[0]
                return f"{missing}(补课)"
            except:
                pass

        # 3. 正常/跳步策略
        next_node = self.policy_map.get(current_node, current_node)
        return f"{next_node}(概念)"


# ==========================================
# 5. 动态画像 (显示逻辑增强)
# ==========================================
class DynamicProfile:
    def __init__(self, target, user_profile):
        self.target = target
        self.user_profile = user_profile  # 绑定数据源
        self.mode = "standard"
        self.missing = ""

    def update(self, feedback):
        if "FAIL" in feedback:
            self.mode = "remedial";
            self.missing = feedback.split(":")[-1]
        elif "SHIFT" in feedback:
            self.mode = "preference"
        else:
            self.mode = "standard"

    def get_prompt(self, current, dist):
        base = f"当前:[{current}] 距离:{dist}步"

        # --- 获取实时指标 ---
        # 格式化显示：能力/焦虑/效率/时间
        metrics = f"能力:{self.user_profile.ability:.2f} 焦虑:{self.user_profile.anxiety:.2f} 效率:{self.user_profile.efficiency:.2f} | 预估时间:{self.user_profile.estimated_time}分钟"

        status = self.user_profile.get_status_desc()

        # 根据焦虑值动态调整指令
        instruction = ""
        if self.mode == "remedial":
            instruction = f"⛔ 断层(缺{self.missing}) | 指令:推荐补课"
        elif self.user_profile.anxiety > 0.6:  # 焦虑高时强制推荐视频
            instruction = f"{status} | 指令:推荐舒适难度+视频资源"
        else:
            instruction = f"{status} | 指令:推荐下一步"

        return f"{base} | {metrics} | {instruction}"


# ==========================================
# 主程序入口
# ==========================================
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🚀 个性化自适应学习系统 (数值驱动版)")
    print("=" * 80)

    kg = SmartKG("kg_transition_cache1.json")

    # 1. 配置
    my_start = "模式识别"
    my_target = "近似解"  # 确保这两个点在你的 json 里

    # 2. 生成长路径 (15步)
    path = kg.find_long_path_fast(my_start, my_target, length=15)
    print(f"✅ 教学路径: {' -> '.join(path)}")

    # 3. 初始化组件
    user_profile = EnhancedUserProfile()  # 创建用户画像
    sim = RealDataSimulator(kg, path, user_profile)
    agent = SmartAgent(path)
    profile = DynamicProfile(my_target, user_profile)

    print("-" * 80)

    path_index_map = {node: i for i, node in enumerate(path)}
    total_len = len(path)

    # 4. 运行循环
    for step in range(1, 25):
        time.sleep(0.3)
        curr = sim.current_node

        # 计算距离
        curr_idx = path_index_map.get(curr, 0)
        dist = total_len - 1 - curr_idx

        # 获取带详细指标的 Prompt
        prompt = profile.get_prompt(curr, dist)

        print(f"\n[Step {step}] 当前: {curr}")
        print(f"   📄 Prompt: {prompt}")

        action = agent.generate(prompt, curr)
        print(f"   🤖 Agent : {action}")

        feedback = sim.step(action)

        if feedback == "GOAL_REACHED":
            print(f"   🎉 Result: {feedback} (+100.0)")
            print("\n✅ 实验完美成功！")
            break
        elif "PASS" in feedback:
            print(f"   ✅ Result: {feedback} (Reward: +3.0)")
        elif "FAIL" in feedback:
            print(f"   ⛔ Result: {feedback} (Reward: -2.0)")
        else:
            print(f"   ⚠️ Result: {feedback}")

        profile.update(feedback)