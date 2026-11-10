import json
import networkx as nx
import os


class GoalDrivenKG:
    def __init__(self, json_path="kg_transition_cache1.json"):
        """
        初始化目标导向图谱，加载用户自定义的 JSON 文件。
        """
        self.json_path = json_path
        self.G = nx.DiGraph()  # 创建有向图

        # 1. 加载您的真实数据
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"❌ 错误：找不到文件 {json_path}，请确认文件名和路径！")

        print(f"📂 正在加载图谱文件: {json_path} ...")
        with open(json_path, 'r', encoding='utf-8') as f:
            self.transitions = json.load(f)

        # 2. 构建 NetworkX 图结构 (用于计算距离)
        # 假设您的 json 格式是: {"当前知识点": ["后继知识点1", "后继知识点2", ...]}
        edge_count = 0
        for source_node, next_nodes in self.transitions.items():
            self.G.add_node(source_node)  # 添加节点

            # 容错处理：确保 next_nodes 是列表
            if isinstance(next_nodes, list):
                for target_node in next_nodes:
                    self.G.add_edge(source_node, target_node)  # 添加有向边
                    edge_count += 1
            else:
                # 如果您的json结构比较特殊(例如包含权重)，可能需要在这里调整
                pass

        self.all_nodes = list(self.G.nodes())
        print(f"✅ 图谱加载成功！")
        print(f"   - 节点数 (Nodes): {len(self.all_nodes)}")
        print(f"   - 边数 (Edges):   {edge_count}")
        print("--------------------------------------------------")

    def get_distance(self, current, target):
        """
        [核心功能] 计算从 current 到 target 的最短路径跳数。
        这是计算“势能奖励”的基础。
        """
        try:
            if current == target:
                return 0
            # 使用 Dijkstra 算法计算最短路径长度
            return nx.shortest_path_length(self.G, source=current, target=target)
        except nx.NetworkXNoPath:
            return 999  # 如果不可达 (断路)，返回无穷大
        except Exception as e:
            # 如果节点不在图里 (幻觉)，也返回无穷大
            return 999

    def is_valid_step(self, current, next_node):
        """判断是否是合法的直接后继 (用于模拟器判断是否断层)"""
        # 宽松验证：只要图里有这条边，或者就是原地不动，都算合法
        if self.G.has_edge(current, next_node) or current == next_node:
            return True
        return False


# ==========================================
# 单元测试 (运行此文件以验证加载是否正确)
# ==========================================
if __name__ == "__main__":
    # 实例化
    try:
        kg = GoalDrivenKG("kg_transition_cache1.json")

        # 测试数据 (请根据您图谱里的真实节点修改这里的测试用例)
        test_start = "数据结构"  # 替换为您图谱里真实存在的起点
        test_target = "二叉树"  # 替换为您图谱里真实存在的终点

        # 1. 测试距离计算
        dist = kg.get_distance(test_start, test_target)
        print(f"🧪 [测试] '{test_start}' -> '{test_target}' 距离: {dist} 跳")

        if dist == 999:
            print("   ⚠️ 警告：这两个点之间不可达，或者节点名写错了。")
        else:
            print("   ✅ 距离计算正常，可以用于目标导向奖励！")

        # 2. 测试邻接关系
        print(f"🧪 [测试] '{test_start}' 的直接后继: {list(kg.G.successors(test_start))}")

    except Exception as e:
        print(f"\n❌ 运行出错: {e}")