"""
增强的用户画像模型 - 包含完整的个性化量化指标
Based on 老师要求的个性化属性
"""
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import json


class EnhancedUserProfile:
    """
    增强的用户画像类 - 包含所有个性化量化指标
    """

    def __init__(self, user_id: str):
        self.user_id = user_id

        # ==========================================
        # 1. 知识状态 (Knowledge State)
        # ==========================================
        # 学习者对所有已学知识的整体掌握情况
        self.knowledge_state = {
            'overall_mastery': 0.0,  # 总体掌握度 [0-1]
            'concept_mastery': {},  # {知识点ID: 掌握度[0-1]}
            'mastered_concepts': [],  # 已掌握的知识点列表
            'weak_concepts': [],  # 薄弱知识点列表
            'learning_curve': []  # 学习曲线记录
        }

        # ==========================================
        # 2. 知识点掌握情况 (Concept Mastery Details)
        # ==========================================
        # 某一特定知识点的掌握程度,是知识状态的具体体现
        self.concept_details = {}
        # 格式: {
        #   'concept_id': {
        #       'mastery_level': 0.0-1.0,      # 掌握水平
        #       'confidence': 0.0-1.0,          # 掌握信心
        #       'last_study_time': datetime,    # 最后学习时间
        #       'study_count': 0,               # 学习次数
        #       'correct_rate': 0.0-1.0,        # 正确率
        #       'time_spent': 0,                # 学习时长(分钟)
        #       'forgetting_rate': 0.0-1.0,     # 遗忘率
        #       'difficulty_perception': 0.0-1.0 # 难度感知
        #   }
        # }

        # ==========================================
        # 3. 学习能力指数 (Learning Ability Index)
        # ==========================================
        self.learning_ability = {
            # 3.1 理解能力相关
            'comprehension_speed': 0.5,  # 理解速度 [0-1], 0.5为平均水平
            'abstract_thinking': 0.5,  # 抽象思维能力
            'logical_reasoning': 0.5,  # 逻辑推理能力

            # 3.2 记忆能力相关
            'retention_rate': 0.7,  # 记忆保持率 [0-1]
            'working_memory': 0.6,  # 工作记忆容量
            'long_term_memory': 0.7,  # 长期记忆能力

            # 3.3 迁移能力相关
            'transfer_ability': 0.6,  # 知识迁移能力
            'application_ability': 0.5,  # 应用能力

            # 3.4 问题解决相关
            'problem_solving': 0.5,  # 问题解决能力
            'critical_thinking': 0.5,  # 批判性思维

            # 3.5 自我调节相关
            'self_regulation': 0.6,  # 自我调节能力
            'time_management': 0.5,  # 时间管理能力
            'attention_span': 45,  # 注意力持续时间(分钟)

            # 3.6 综合指标
            'overall_ability': 0.55,  # 综合学习能力指数
            'learning_efficiency': 1.0  # 学习效率系数 (影响时间预估)
        }

        # ==========================================
        # 4. 当前焦虑情绪指数 (Current Anxiety Index)
        # ==========================================
        self.anxiety_index = {
            'current_level': 0.3,  # 当前焦虑水平 [0-1]
            'test_anxiety': 0.4,  # 考试焦虑
            'time_pressure_anxiety': 0.3,  # 时间压力焦虑
            'difficulty_anxiety': 0.2,  # 难度焦虑
            'social_anxiety': 0.2,  # 社交焦虑(讨论/展示)
            'baseline_anxiety': 0.25,  # 基线焦虑水平
            'anxiety_history': [],  # 焦虑变化历史
            'triggers': []  # 焦虑触发因素
        }

        # ==========================================
        # 5. 资源偏好 (Resource Preference)
        # ==========================================
        self.resource_preference = {
            # 5.1 内容类型偏好
            'video': 0.7,  # 视频资源偏好 [0-1]
            'text': 0.5,  # 文本资源偏好
            'audio': 0.3,  # 音频资源偏好
            'interactive': 0.8,  # 互动练习偏好
            'code_practice': 0.6,  # 代码实践偏好
            'case_study': 0.5,  # 案例学习偏好
            'simulation': 0.6,  # 模拟实验偏好

            # 5.2 难度偏好
            'difficulty_preference': 'adaptive',  # 'easy', 'medium', 'hard', 'adaptive'
            'challenge_seeking': 0.5,  # 挑战寻求倾向

            # 5.3 学习风格
            'visual_learning': 0.7,  # 视觉学习偏好
            'auditory_learning': 0.4,  # 听觉学习偏好
            'kinesthetic_learning': 0.6,  # 动觉学习偏好

            # 5.4 其他偏好
            'pace_preference': 'moderate',  # 'slow', 'moderate', 'fast'
            'depth_preference': 'balanced'  # 'overview', 'balanced', 'deep'
        }

        # ==========================================
        # 6. 时间相关属性 (用于时间规划)
        # ==========================================
        self.time_attributes = {
            'available_hours_per_day': 2.0,  # 每天可用学习时间(小时)
            'preferred_time_slots': [],  # 偏好学习时段
            'average_session_time': 45,  # 平均学习时长(分钟)
            'break_frequency': 50,  # 休息频率(分钟)
            'optimal_study_duration': 90,  # 最佳单次学习时长
            'deadline': None,  # 学习截止日期
            'total_available_time': 0  # 总可用时间(小时)
        }

        # ==========================================
        # 7. 学习历史与行为数据
        # ==========================================
        self.learning_history = {
            'total_study_time': 0,  # 总学习时长(分钟)
            'completed_concepts': [],  # 已完成知识点
            'dropout_points': [],  # 历史放弃点
            'completion_rate': 0.0,  # 任务完成率
            'average_daily_time': 0,  # 平均每日学习时间
            'consistency_score': 0.5,  # 学习一致性分数
            'last_active': None  # 最后活跃时间
        }

        # ==========================================
        # 8. 目标与动机
        # ==========================================
        self.learning_goals = {
            'target_concepts': [],  # 目标知识点列表
            'current_goal': None,  # 当前学习目标
            'motivation_level': 0.7,  # 动机强度 [0-1]
            'goal_clarity': 0.8,  # 目标明确度
            'intrinsic_motivation': 0.6,  # 内在动机
            'extrinsic_motivation': 0.5  # 外在动机
        }

    def update_concept_mastery(self, concept_id: str, performance_data: Dict):
        """更新知识点掌握情况"""
        if concept_id not in self.concept_details:
            self.concept_details[concept_id] = {
                'mastery_level': 0.0,
                'confidence': 0.0,
                'last_study_time': datetime.now(),
                'study_count': 0,
                'correct_rate': 0.0,
                'time_spent': 0,
                'forgetting_rate': 0.3,
                'difficulty_perception': 0.5
            }

        detail = self.concept_details[concept_id]
        detail['study_count'] += 1

        # 更新掌握水平(使用指数移动平均)
        alpha = 0.3
        detail['mastery_level'] = (1 - alpha) * detail['mastery_level'] + alpha * performance_data['score']
        detail['confidence'] = performance_data.get('confidence', detail['mastery_level'] * 0.9)
        detail['correct_rate'] = (detail['correct_rate'] * (detail['study_count'] - 1) +
                                  performance_data['score']) / detail['study_count']
        detail['time_spent'] += performance_data.get('time_spent', 0)
        detail['last_study_time'] = datetime.now()
        detail['difficulty_perception'] = performance_data.get('difficulty', 0.5)

        # 更新知识状态
        self.knowledge_state['concept_mastery'][concept_id] = detail['mastery_level']
        if self.knowledge_state['concept_mastery']:
            self.knowledge_state['overall_mastery'] = np.mean(
                list(self.knowledge_state['concept_mastery'].values())
            )

        # 更新已掌握/薄弱知识点列表
        if detail['mastery_level'] >= 0.8:
            if concept_id not in self.knowledge_state['mastered_concepts']:
                self.knowledge_state['mastered_concepts'].append(concept_id)
        if detail['mastery_level'] < 0.5:
            if concept_id not in self.knowledge_state['weak_concepts']:
                self.knowledge_state['weak_concepts'].append(concept_id)

    def update_anxiety(self, anxiety_score: float, trigger: str = None):
        """更新焦虑情绪"""
        self.anxiety_index['current_level'] = np.clip(anxiety_score, 0, 1)
        self.anxiety_index['anxiety_history'].append({
            'time': datetime.now(),
            'level': anxiety_score,
            'trigger': trigger
        })

        if trigger and trigger not in self.anxiety_index['triggers']:
            self.anxiety_index['triggers'].append(trigger)

    def calculate_learning_efficiency(self) -> float:
        """计算当前学习效率系数"""
        base_efficiency = self.learning_ability['overall_ability']
        anxiety_factor = 1.0 - abs(self.anxiety_index['current_level'] - 0.3) * 0.5
        motivation_factor = self.learning_goals['motivation_level']
        efficiency = base_efficiency * anxiety_factor * motivation_factor
        self.learning_ability['learning_efficiency'] = np.clip(efficiency, 0.3, 1.5)
        return self.learning_ability['learning_efficiency']

    def estimate_learning_time(self, concept_difficulty: float,
                               prerequisite_met: bool = True) -> float:
        """预估学习某个知识点所需时间(分钟)"""
        base_time = 30 + concept_difficulty * 60
        ability_factor = 2.0 - self.learning_ability['comprehension_speed']
        efficiency = self.calculate_learning_efficiency()
        prerequisite_factor = 1.0 if prerequisite_met else 1.5
        estimated_time = base_time * ability_factor * prerequisite_factor / efficiency
        return max(15, min(180, estimated_time))

    def get_preferred_resource_type(self, concept_type: str = 'general') -> str:
        """获取推荐的资源类型"""
        if self.anxiety_index['current_level'] > 0.6:
            return 'video'

        prefs = self.resource_preference
        resource_scores = {
            'video': prefs['video'],
            'text': prefs['text'],
            'interactive': prefs['interactive'],
            'code_practice': prefs['code_practice'] if 'code' in concept_type.lower() else 0
        }
        return max(resource_scores.items(), key=lambda x: x[1])[0]