# -----------------------------------------------------------------------------
# 【简化版 RL训练框架.py】
# 目的：不使用 PPOTrainer，手动实现简化的 RLHF 训练循环
# 这个版本避免了 TRL 版本兼容性问题，完全不依赖 trl 库
# -----------------------------------------------------------------------------

import os
import torch
from transformers import MT5TokenizerFast, MT5ForConditionalGeneration
from transformers import AutoModelForSequenceClassification
from datasets import load_dataset
from torch.optim import AdamW
from tqdm import tqdm
import json

# ---------------------------------------------------------------
# 1. 配置项
# ---------------------------------------------------------------
POLICY_MODEL_PATH = r"/T5_small/zhuanjiamodel"
COST_MODEL_PATH = r"/T5_small/chengbenmodel"
PROMPT_DATA_FILE = "样本数据集_data.jsonl"
SAFE_MODEL_PATH = r"/T5_small/finalsafemodel"

# 训练超参数
BATCH_SIZE = 4
LEARNING_RATE = 1.4e-6
NUM_EPOCHS = 2
MAX_LENGTH = 256
LAMBDA_COST = 5.0  # 成本惩罚系数


# ---------------------------------------------------------------
# 2. 辅助函数
# ---------------------------------------------------------------

def get_reward_signal(path, facts):
    """奖励函数 (硬约束：连贯性)"""
    if facts["missing_prereqs"]:
        first_prereq = facts["missing_prereqs"][0]
        if first_prereq in path:
            return 1.0
        else:
            return -1.0
    return 1.0


def get_cost_signal(cost_model, cost_tokenizer, prompt, path, device):
    """成本函数 (软约束：个性化)"""
    input_text = prompt + " [SEP] " + path
    inputs = cost_tokenizer(
        input_text,
        return_tensors="pt",
        max_length=512,
        truncation=True,
        padding=True
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = cost_model(**inputs).logits
        cost = torch.sigmoid(logits[0]).item()  # 归一化到 [0, 1]

    return cost


def compute_kl_divergence(policy_logits, ref_logits):
    """计算 KL 散度"""
    policy_probs = torch.softmax(policy_logits, dim=-1)
    ref_probs = torch.softmax(ref_logits, dim=-1)

    kl = torch.sum(policy_probs * (torch.log(policy_probs + 1e-10) - torch.log(ref_probs + 1e-10)), dim=-1)
    return kl.mean()


# ---------------------------------------------------------------
# 3. 简化的 RLHF 训练循环
# ---------------------------------------------------------------
def main_simplified_rl_training():
    print("--- 开始简化版 Safe RLHF 训练 ---")

    # 设置设备
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    # --- 加载模型 ---
    print("正在加载模型...")

    # 策略模型 (我们要优化的)
    policy_model = MT5ForConditionalGeneration.from_pretrained(POLICY_MODEL_PATH)
    policy_model = policy_model.to(device)

    # 参考模型 (冻结，用于 KL 散度)
    ref_model = MT5ForConditionalGeneration.from_pretrained(POLICY_MODEL_PATH)
    ref_model = ref_model.to(device)
    ref_model.eval()
    for param in ref_model.parameters():
        param.requires_grad = False

    # 成本模型
    cost_model = AutoModelForSequenceClassification.from_pretrained(COST_MODEL_PATH)
    cost_model = cost_model.to(device)
    cost_model.eval()
    for param in cost_model.parameters():
        param.requires_grad = False

    # 分词器
    tokenizer = MT5TokenizerFast.from_pretrained(POLICY_MODEL_PATH)
    cost_tokenizer = MT5TokenizerFast.from_pretrained(COST_MODEL_PATH)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if cost_tokenizer.pad_token is None:
        cost_tokenizer.pad_token = cost_tokenizer.eos_token

    print("✅ 所有模型加载完毕")

    # --- 加载数据集 ---
    try:
        dataset = load_dataset('json', data_files={'train': PROMPT_DATA_FILE})['train']
        dataset = dataset.shuffle()
        print(f"✅ 数据集加载完毕，共 {len(dataset)} 条记录")
    except Exception as e:
        print(f"❌ 数据集加载失败: {e}")
        return

    # --- 优化器 ---
    optimizer = AdamW(policy_model.parameters(), lr=LEARNING_RATE)

    # --- 训练循环 ---
    print("\n--- 开始训练 ---")
    example_facts = {"missing_prereqs": ["无线局域网"]}

    policy_model.train()
    global_step = 0

    for epoch in range(NUM_EPOCHS):
        print(f"\n{'=' * 60}")
        print(f"Epoch {epoch + 1}/{NUM_EPOCHS}")
        print(f"{'=' * 60}")

        epoch_rewards = []
        epoch_costs = []
        epoch_losses = []

        # 创建数据加载器
        for i in range(0, len(dataset), BATCH_SIZE):
            try:
                # 使用切片获取批次数据
                batch_data = dataset[i:min(i + BATCH_SIZE, len(dataset))]

                # 注意：dataset[i:j] 返回 {'input': [...], 'output': [...]}
                # 而不是 [{...}, {...}]
                if isinstance(batch_data, dict) and 'input' in batch_data:
                    prompts = batch_data['input']  # 这是一个列表
                else:
                    # 备用方案：逐个获取
                    prompts = []
                    for j in range(i, min(i + BATCH_SIZE, len(dataset))):
                        item = dataset[j]
                        if isinstance(item, dict) and 'input' in item:
                            prompts.append(item['input'])

                # 过滤空字符串
                prompts = [p for p in prompts if p]
                if not prompts:
                    continue

                inputs = tokenizer(
                    prompts,
                    return_tensors="pt",
                    max_length=512,
                    truncation=True,
                    padding=True
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}

                # 1. 生成响应 (使用策略模型)
                with torch.no_grad():
                    generated = policy_model.generate(
                        **inputs,
                        max_new_tokens=MAX_LENGTH,
                        do_sample=True,
                        top_k=50,
                        top_p=0.95,
                        temperature=0.7,
                    )

                # 解码生成的文本
                generated_texts = tokenizer.batch_decode(generated, skip_special_tokens=True)

                # 2. 计算奖励
                batch_rewards = []
                batch_costs = []

                for prompt, generated_text in zip(prompts, generated_texts):
                    # 硬约束奖励
                    reward_r = get_reward_signal(generated_text, example_facts)

                    # 软约束成本
                    cost_c = get_cost_signal(cost_model, cost_tokenizer, prompt, generated_text, device)

                    # 组合奖励
                    total_reward = reward_r - (LAMBDA_COST * cost_c)

                    batch_rewards.append(total_reward)
                    batch_costs.append(cost_c)

                # 3. 计算策略梯度损失
                # 准备目标 (生成的文本作为标签)
                labels = generated.clone()
                labels[labels == tokenizer.pad_token_id] = -100

                # 前向传播
                outputs = policy_model(**inputs, labels=labels)

                # 计算 KL 散度惩罚
                with torch.no_grad():
                    ref_outputs = ref_model(**inputs, labels=labels)

                kl_div = compute_kl_divergence(outputs.logits, ref_outputs.logits)

                # 总损失 = 负对数似然 + KL惩罚 - 奖励加权
                avg_reward = sum(batch_rewards) / len(batch_rewards)
                loss = outputs.loss + 0.1 * kl_div - avg_reward * 0.01  # 奖励作为梯度信号

                # 4. 反向传播
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy_model.parameters(), 1.0)
                optimizer.step()

                # 记录统计
                epoch_rewards.extend(batch_rewards)
                epoch_costs.extend(batch_costs)
                epoch_losses.append(loss.item())

                global_step += 1

                # 定期输出
                if global_step % 10 == 0:
                    print(f"Step {global_step} | "
                          f"Loss: {loss.item():.4f} | "
                          f"Avg Reward: {avg_reward:.4f} | "
                          f"Avg Cost: {sum(batch_costs) / len(batch_costs):.4f}")

            except Exception as e:
                print(f"⚠️ Step {global_step} 出现错误: {e}")
                continue

        # Epoch 统计
        if epoch_rewards:  # 只有在有数据时才计算
            print(f"\nEpoch {epoch + 1} 完成:")
            print(f"  平均奖励: {sum(epoch_rewards) / len(epoch_rewards):.4f}")
            print(f"  平均成本: {sum(epoch_costs) / len(epoch_costs):.4f}")
            print(f"  平均损失: {sum(epoch_losses) / len(epoch_losses):.4f}")
        else:
            print(f"\n⚠️ Epoch {epoch + 1} 没有有效数据")

    # --- 保存模型 ---
    print(f"\n--- 训练完成！正在保存到 {SAFE_MODEL_PATH} ---")
    try:
        os.makedirs(SAFE_MODEL_PATH, exist_ok=True)
        policy_model.save_pretrained(SAFE_MODEL_PATH)
        tokenizer.save_pretrained(SAFE_MODEL_PATH)
        print("✅ 模型保存成功！")

        # 保存训练统计
        if epoch_rewards:  # 只有在有数据时才保存
            stats = {
                "num_epochs": NUM_EPOCHS,
                "learning_rate": LEARNING_RATE,
                "lambda_cost": LAMBDA_COST,
                "final_avg_reward": sum(epoch_rewards) / len(epoch_rewards),
                "final_avg_cost": sum(epoch_costs) / len(epoch_costs),
            }
            with open(os.path.join(SAFE_MODEL_PATH, "training_stats.json"), "w") as f:
                json.dump(stats, f, indent=2)

    except Exception as e:
        print(f"❌ 模型保存失败: {e}")


if __name__ == "__main__":
    main_simplified_rl_training()