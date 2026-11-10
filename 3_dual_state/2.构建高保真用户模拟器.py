import random


# ==========================================
# 用户模拟器类 (User Simulator)
# ==========================================
class GoalUserSimulator:
    def __init__(self, kg, start_node, target_node):
        self.kg = kg
        self.current_node = start_node
        self.target_node = target_node
        self.history = [start_node]
        self.step_count = 0
        self.fatigue = 0.0

        # 【剧本设定】人工设定的先修课限制
        # 即使图谱上是连通的，我们强制规定：想学A，必须先学过B
        self.prerequisites = {
            "树": "递归",  # 想要学“树”，历史记录里必须有“递归”
            "二叉树": "树",  # 想要学“二叉树”，必须先学过“树”
            "递归": "线性表"  # 想要学“递归”，必须先学过“线性表”
        }

    def step(self, action_text):
        self.step_count += 1

        # 1. 简单清洗动作 (去除视频后缀、方括号等)
        clean_node = action_text.replace("(视频)", "").replace("[", "").replace("]", "").strip()

        # --- 交互情况 A: 到达终点 ---
        if clean_node == self.target_node:
            # 检查终点的先修条件
            required = self.prerequisites.get(clean_node)
            if required and required not in self.history:
                return f"FAIL_GAP:{required}"
            return "GOAL_REACHED"

        # --- 交互情况 B: 模拟疲劳 (Shift) ---
        # 设定：第 4 步时必定疲劳
        if self.step_count == 4:
            self.fatigue = 0.8
            print(f"      [Sim内部状态] ⚠️ 学生累了 (疲劳度: {self.fatigue})")

            # 处理疲劳逻辑
            if self.fatigue > 0.5:
                if "(视频)" in action_text:
                    self.fatigue = 0.0  # 给了视频，休息好了
                    self.current_node = clean_node

                    # 【修复点】看了视频也算学会了！必须加入历史记录
                    if clean_node not in self.history:
                        self.history.append(clean_node)

                    return "PASS"
                else:
                    # 累了但给的是文本 -> 拒绝
                    return "SHIFT_VIDEO"

        # --- 交互情况 C: 知识断层 (Fail Gap) ---
        # 检查剧本里的先修课限制
        required_pre = self.prerequisites.get(clean_node)
        if required_pre and required_pre not in self.history:
            return f"FAIL_GAP:{required_pre}"

        # --- 交互情况 D: 正常学习 (Pass) ---
        # 只要在图谱节点列表里，或者之前学过，或者通过了上面的检查
        if clean_node in self.kg.all_nodes:
            self.current_node = clean_node
            self.history.append(clean_node)
            return "PASS"

        # 兜底：如果是幻觉（图谱里根本没有这个词）
        return "ERROR_HALLUCINATION"


# ==========================================
# ✅ 测试代码 (只有直接运行此文件时才会执行)
# ==========================================
if __name__ == "__main__":
    print(">>> 正在测试用户模拟器逻辑 <<<")


    # 1. 造一个假的图谱对象 (Mock KG)，只要有 all_nodes 属性就行
    class MockKG:
        all_nodes = ["数据结构", "线性表", "递归", "树", "二叉树"]


    # 2. 初始化模拟器
    kg = MockKG()
    sim = GoalUserSimulator(kg, start_node="数据结构", target_node="二叉树")
    print(f"初始状态: {sim.current_node} -> 目标: {sim.target_node}")
    print("-" * 40)

    # 3. 手动输入动作进行测试

    # 测试 1: 正常推进
    action1 = "线性表"
    print(f"[Step 1] Agent推荐: '{action1}' -> 反馈: {sim.step(action1)}")

    # 测试 2: 触发断层 (故意跳过'递归'直接推'树')
    action2 = "树"
    print(f"[Step 2] Agent推荐: '{action2}' -> 反馈: {sim.step(action2)}")

    # 测试 3: 补课 (补上'递归')
    action3 = "递归"
    print(f"[Step 3] Agent推荐: '{action3}' -> 反馈: {sim.step(action3)}")

    # 测试 4: 触发疲劳 (第4步强制疲劳)
    action4 = "树"
    print(f"[Step 4] Agent推荐: '{action4}' -> 反馈: {sim.step(action4)}")

    # 测试 5: 风格迁移 (给视频)
    action5 = "树(视频)"
    print(f"[Step 5] Agent推荐: '{action5}' -> 反馈: {sim.step(action5)}")

    # 测试 6: 到达终点
    action6 = "二叉树"
    print(f"[Step 6] Agent推荐: '{action6}' -> 反馈: {sim.step(action6)}")