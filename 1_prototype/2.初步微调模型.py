# -----------------------------------------------------------------------------
# 【脚本 2: finetune_mt5.py】(本地加载版)
# 目的：(对应PPT 月2) 使用本地基础模型和中文数据进行微调
#
# 1. 运行前请确保:
#    a. "脚本 1" 已成功运行
#    b. "training_data.jsonl" (或 "样本数据集_data.jsonl") 已存在
# -----------------------------------------------------------------------------

import os
import sys

from transformers import (
    MT5TokenizerFast,
    MT5ForConditionalGeneration,
    Trainer,
    TrainingArguments,
    DataCollatorForSeq2Seq
)
from datasets import load_dataset

# ---------------------------------------------------------------
# 1. 配置项 (*** 请务必修改以下配置 ***)
# ---------------------------------------------------------------

# (修正) 基础模型：必须指向 "脚本 1" 的下载路径
BASE_MODEL_PATH = r"/T5_small/MT5_small"

# (修正) 输入：指向您之前生成的中文训练集
TRAIN_DATA_FILE = "样本数据集_data.jsonl"

# (输出) 您微调后的新模型的保存路径 (纯英文)
FINETUNED_MODEL_PATH = r"/T5_small/zhuanjiamodel"

# ---------------------------------------------------------------
# 2. 加载模型和分词器
# ---------------------------------------------------------------
print(f"--- 步骤 1: 正在从 *本地* 加载基础模型: {BASE_MODEL_PATH} ---")
try:
    tokenizer = MT5TokenizerFast.from_pretrained(BASE_MODEL_PATH)
    model = MT5ForConditionalGeneration.from_pretrained(BASE_MODEL_PATH)
    print("✅ 基础模型加载成功。")
except Exception as e:
    print(f"❌ [错误] 从本地加载模型失败: {e}")
    print("!!! 请检查：")
    print(f"    1. 路径 '{BASE_MODEL_PATH}' 是否正确？")
    print("    2. 您是否已成功运行 '脚本 1' (download_mt5.py)？")
    print("    3. 文件夹中是否包含 'config.json' 和 'pytorch_model.bin' 等文件？")
    sys.exit(1)

# ---------------------------------------------------------------
# 3. 加载数据集
# ---------------------------------------------------------------
print(f"正在加载训练集: {TRAIN_DATA_FILE}")
try:
    dataset = load_dataset('json', data_files={'train': TRAIN_DATA_FILE})
except FileNotFoundError:
    print(f"❌ [错误] 训练文件未找到: {TRAIN_DATA_FILE}")
    print("!!! 请先运行 'build_finetune_dataset.py' 脚本。")
    sys.exit(1)

# 拆分验证集
dataset_splits = dataset['train'].train_test_split(test_size=0.1)

# ---------------------------------------------------------------
# 4. 预处理 (Tokenize)
# ---------------------------------------------------------------
def preprocess_function(examples):
    inputs = tokenizer(
        examples['input'],
        max_length=1024,
        truncation=True,
        padding=False
    )
    with tokenizer.as_target_tokenizer():
        labels = tokenizer(
            examples['output'],
            max_length=256,
            truncation=True,
            padding=False
        )
    inputs['labels'] = labels['input_ids']
    return inputs

print("正在对数据集进行分词...")
tokenized_datasets = dataset_splits.map(
    preprocess_function,
    batched=True,
    remove_columns=dataset['train'].column_names
)

data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    model=model
)

# ---------------------------------------------------------------
# 5. 定义训练参数 (使用您已升级的 transformers 库)
# ---------------------------------------------------------------
training_args = TrainingArguments(
    output_dir=FINETUNED_MODEL_PATH,
    num_train_epochs=3,
    per_device_train_batch_size=2,
    per_device_eval_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=5e-5,
    save_strategy="epoch",
    eval_strategy="epoch", # <--- 您的库已支持此参数
    save_total_limit=1,
    load_best_model_at_end=True,
    fp16=True,
    logging_steps=100,
    report_to="none",
)

# ---------------------------------------------------------------
# 6. 初始化训练器
# ---------------------------------------------------------------
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets['train'],
    eval_dataset=tokenized_datasets['test'],
    tokenizer=tokenizer,
    data_collator=data_collator,
)

# ---------------------------------------------------------------
# 7. 开始训练
# ---------------------------------------------------------------
print("\n==========================================")
print("--- (方案 B) 开始微调 MT5-small... ---")
print(f"基础模型: {BASE_MODEL_PATH} (本地)")
print(f"训练数据: {TRAIN_DATA_FILE}")
print(f"输出目录: {FINETUNED_MODEL_PATH}")
print("==========================================\n")

trainer.train()

# ---------------------------------------------------------------
# 8. 保存最终模型
# ---------------------------------------------------------------
print("--- 微调完成！正在保存最终模型... ---")
trainer.save_model(FINETUNED_MODEL_PATH)
print(f"\n✅ 新模型已保存到: {FINETUNED_MODEL_PATH}")
print("\n下一步：请修改 '2.深度检索特征.py' 脚本中的 'T5_MODEL_PATH' 指向这个新路径并运行。")