# -----------------------------------------------------------------------------
# 【脚本 1: train_cost_model.py】
# 目的：(对应PPT 创新点3) 训练一个“成本模型” (Cost Model)
#
# 1. 运行前请确保已安装: pip install transformers datasets accelerate bitsandbytes
# 2. 此脚本依赖 '样本数据集_data.jsonl' (来自 "方案B" 脚本1)
# -----------------------------------------------------------------------------

import os
import sys
import json
import random
from transformers import (
    MT5TokenizerFast,
    # (关键) 我们需要一个用于“序列分类”的模型，而不是“生成”
    MT5ForSequenceClassification,
    Trainer,
    TrainingArguments
)
from datasets import load_dataset, Dataset

# ---------------------------------------------------------------
# 1. 配置项
# ---------------------------------------------------------------
# (输入) 基础模型：使用您下载的 "mt5_small_files"
BASE_MODEL_PATH = r"/T5_small/MT5_small"

# (输入) 我们重用之前生成的训练数据
TRAIN_DATA_FILE = "样本数据集_data.jsonl"

# (输出) 您的成本模型的保存路径
COST_MODEL_PATH = r"/T5_small/chengbenmodel"


# ---------------------------------------------------------------
# 2. (新) 辅助函数：自动标注“成本”
# ---------------------------------------------------------------
def label_cost_for_path(prompt, path):
    """
    自动标注“成本”(即“安全性”/“偏好”)。
    这是 Safe RLHF 的核心步骤之一。

    规则：
    - 成本 0 (安全): 路径遵循了 Prompt 中的个性化偏好。
    - 成本 1 (不安全): 路径违反了 Prompt 中的个性化偏好。
    """

    # 查找偏好
    prefer_video = "偏好'视频'" in prompt

    # 检查路径
    uses_video = "[视频]" in path
    uses_course = "[课程]" in path

    # 规则1: 如果学生偏好视频，但路径推荐了课程且没有视频
    if prefer_video and uses_course and not uses_video:
        return 1.0  # (高成本/不安全)

    # 规则2: (您可以添加更多规则，例如 "难度跳跃")

    # 默认：
    return 0.0  # (低成本/安全)


# ---------------------------------------------------------------
# 3. 加载和预处理数据集
# ---------------------------------------------------------------
print(f"正在加载训练集: {TRAIN_DATA_FILE}")
if not os.path.exists(TRAIN_DATA_FILE):
    print(f"❌ [错误] 训练文件未找到: {TRAIN_DATA_FILE}")
    sys.exit(1)

# 加载数据
data = []
with open(TRAIN_DATA_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        item = json.loads(line)
        # (关键) 为每条数据自动打上“成本”标签
        # 'input' 是 Prompt, 'output' 是理想路径
        cost = label_cost_for_path(item['input'], item['output'])
        # T5 分类器需要 "input_text [SEP] output_text" 这种格式
        input_text = item['input'] + " [SEP] " + item['output']
        data.append({"text": input_text, "label": cost})

print(f"成功加载并标注了 {len(data)} 条成本数据。")
dataset = Dataset.from_list(data).train_test_split(test_size=0.1)

# ---------------------------------------------------------------
# 4. 加载模型和分词器
# ---------------------------------------------------------------
print(f"正在加载基础模型: {BASE_MODEL_PATH}")
tokenizer = MT5TokenizerFast.from_pretrained(BASE_MODEL_PATH)

# (关键) 加载用于 *分类* 的 MT5 模型
# num_labels=1 表示这是一个回归任务 (0.0 到 1.0)
model = MT5ForSequenceClassification.from_pretrained(
    BASE_MODEL_PATH,
    num_labels=1  # 我们在预测一个连续的“成本”值
)


# --- 5. 预处理 (Tokenize) ---
def preprocess_function(examples):
    # (注意) "text" 对应上面 data.append 中的 "text" 键
    return tokenizer(
        examples['text'],
        max_length=1024,  # (Prompt + Path)
        truncation=True,
        padding='max_length'
    )


print("正在对数据集进行分词...")
tokenized_datasets = dataset.map(preprocess_function, batched=True)

# ---------------------------------------------------------------
# 6. 定义训练参数
# ---------------------------------------------------------------
training_args = TrainingArguments(
    output_dir=COST_MODEL_PATH,
    num_train_epochs=3,
    per_device_train_batch_size=2,
    per_device_eval_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=5e-5,
    save_strategy="epoch",
    eval_strategy="epoch",
    save_total_limit=1,
    load_best_model_at_end=True,
    fp16=True,
    logging_steps=100,
    report_to="none",
)

# ---------------------------------------------------------------
# 7. 初始化训练器
# ---------------------------------------------------------------
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets['train'],
    eval_dataset=tokenized_datasets['test'],
    tokenizer=tokenizer,
)

# ---------------------------------------------------------------
# 8. 开始训练
# ---------------------------------------------------------------
print("\n==========================================")
print("--- 开始训练 *成本模型* (Cost Model)... ---")
print(f"输出目录: {COST_MODEL_PATH}")
print("==========================================\n")

trainer.train()

# ---------------------------------------------------------------
# 9. 保存最终模型
# ---------------------------------------------------------------
print("--- 成本模型训练完成！正在保存... ---")
trainer.save_model(COST_MODEL_PATH)
print(f"\n✅ 成本模型已保存到: {COST_MODEL_PATH}")