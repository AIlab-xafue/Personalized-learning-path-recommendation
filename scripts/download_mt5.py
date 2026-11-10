# -----------------------------------------------------------------------------
# 【脚本 1: download_mt5.py】
# 目的：将 "google/mt5-small" 完整下载到本地
#
# 1. 运行前请确保:
#    a. 已安装: pip install huggingface_hub
#    b. 您的网络可以访问 huggingface.co (例如，已开启 VPN)
# 2. 请务必修改下方 "配置项" 部分
# -----------------------------------------------------------------------------
import os
from huggingface_hub import snapshot_download

# ---------------------------------------------------------------
# 1. 配置项 (*** 请务必修改以下配置 ***)
# ---------------------------------------------------------------
# (关键) 基础模型的 ID
BASE_MODEL_ID = "google/mt5-small"

# (关键) 您想将模型保存在哪？(必须是纯英文路径)
# 这是一个新的、干净的基础模型路径
LOCAL_MODEL_PATH = os.environ.get("MOOCUBE_BASE_MODEL", "models/MT5_small")

# ---------------------------------------------------------------
# 2. 执行下载
# ---------------------------------------------------------------
print(f"--- 正在下载模型: {BASE_MODEL_ID} ---")
print(f"--- 保存到本地: {LOCAL_MODEL_PATH} ---")

if os.path.exists(LOCAL_MODEL_PATH):
    print(f"警告：目录 {LOCAL_MODEL_PATH} 已存在。")
    print("如果您下载不完整，请先手动删除此文件夹。")

try:
    snapshot_download(
        repo_id=BASE_MODEL_ID,
        local_dir=LOCAL_MODEL_PATH,
        repo_type="model",
        local_dir_use_symlinks=False,  # 强制复制文件 (防止 Windows 符号链接错误)

        # (可选优化) 忽略我们不需要的模型格式
        allow_patterns=[
            "*.json",
            "*.py",
            "*.md",
            "spiece.model",
            "pytorch_model.bin",
            "*.safetensors"
        ],
        ignore_patterns=["*.onnx*", "onnx/*", "*.h5"]
    )

    print("\n==========================================")
    print(f"✅ 基础模型下载成功！")
    print(f"   已保存到: {LOCAL_MODEL_PATH}")
    print("==========================================")
    print("\n下一步：请运行 'finetune_mt5.py' 脚本。")

except Exception as e:
    print(f"\n❌ [严重错误] 下载失败: {e}")
    print("!!! 请检查：")
    print("    1. 您的网络连接 (VPN/代理) 是否正常？")
    print("    2. 'repo_id' 是否拼写正确？")
    print("    3. 磁盘空间是否足够？")