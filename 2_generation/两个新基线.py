# -----------------------------------------------------------------------------
# 脚本十三：13_baseline_astar_and_grulstm.py
# 作用 (Role): 回应审稿意见12——补充两个新增基线：
#   (1) A*/BFS+先修约束（纯图搜索基线，无自然语言语义理解）
#   (2) GRU/LSTM 序列推荐基线（传统深度序列模型，无图谱硬约束）
#   并计算表3所需的 SL（结构合法率）、LR（无环率）、EV（关系真实性/Edge Validity）、
#   SC（语义连贯性，基于 Sentence-BERT 余弦相似度）四项指标，与 Ours (Fusion) 对比。
#
# ⚠️ 重要说明（请务必阅读）:
#   GRU/LSTM 基线的训练数据本应为学习者真实历史交互序列日志；由于当前工程中未提供
#   该原始日志文件，本脚本退而求其次，使用【图谱上的随机游走序列】作为训练语料的替代
#   （即假设"历史学习序列大体遵循图谱先修关系"）。该模型的输出层是对全词表的 softmax，
#   推理阶段【不施加任何图谱掩码】，因此仍可能生成图谱中不存在的边（结构性幻觉）——
#   这正是"传统深度序列模型缺乏硬约束"这一核心论点在实验中的体现，与 Ours(Fusion) 的
#   本质差异正在于此。如果你已有 MOOCCube 平台的真实学习者行为序列数据，请直接替换
#   build_pseudo_training_sequences() 的返回结果为真实序列，可获得更具说服力的结果。
#
# 依赖 (若未安装请先执行):
#   pip install sentence-transformers torch neo4j tqdm numpy
#
# 运行前请确认:
#   - Neo4j 服务已启动，且 kg_transition_cache.json 已由脚本一生成
#   - 如需与 Ours(Fusion) 一并对比，请确保 generated_results_fusion_final.txt 已存在
#     （由脚本四"终极融合脚本"生成）
# -----------------------------------------------------------------------------
import json, random, csv, os
import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm
from neo4j import GraphDatabase, basic_auth
from sentence_transformers import SentenceTransformer

# ================= 配置区 =================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER, NEO4J_PASSWORD = "neo4j", os.environ.get("NEO4J_PASSWORD", "neo4j")
KG_CACHE_FILE = "kg_transition_cache.json"

SAMPLE_SIZE = 150          # 测试起点数量（与消融实验保持同一量级，可按需调整）
MAX_STEPS = 10
RANDOM_SEED = 42

# GRU/LSTM 基线配置
RNN_TYPE = "GRU"           # 可选 "GRU" 或 "LSTM"，对应审稿意见中的"GRU/LSTM序列推荐基线"
EMBED_DIM = 64
HIDDEN_DIM = 128
NUM_WALKS_FOR_TRAINING = 4000      # 用于构造伪训练序列的随机游走条数
WALK_LEN_RANGE = (5, 10)
TRAIN_EPOCHS = 5
BATCH_SIZE = 64

# Sentence-BERT 模型（多语言，覆盖中文；需能访问 HuggingFace 或已缓存到本地）
SBERT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

FUSION_RESULT_FILE = "generated_results_fusion_final.txt"  # 若存在则一并纳入对比表
OUTPUT_CSV = "baseline_astar_grurnn_results.csv"

random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)


# ================= 0. 图谱加载 =================
def load_kg():
    with open(KG_CACHE_FILE, "r", encoding="utf-8") as f:
        kg_cache = json.load(f)
    entity_set = set(kg_cache.keys())
    for targets in kg_cache.values():
        entity_set.update(targets)
    return kg_cache, entity_set


def get_out_degree_map(driver):
    """从 Neo4j 拉取每个概念的出度，用于 A* 启发式代价函数"""
    query = """
    MATCH (n:Concept)
    OPTIONAL MATCH (n)-[r]->()
    RETURN n.name AS name, count(r) AS out_degree
    """
    out_degree = {}
    try:
        with driver.session() as session:
            for record in session.run(query):
                out_degree[record["name"]] = record["out_degree"]
    except Exception as e:
        print(f"⚠️ 出度查询失败，将退化为全 0 出度（不影响主流程）: {e}")
    return out_degree


# ================= 1. 基线一：A*/BFS + 先修约束 =================
def generate_astar_path(start_node, kg_cache, out_degree_map, max_steps=MAX_STEPS):
    """
    纯图搜索基线：
      - 每一步仅能在 kg_cache[current] 给出的真实后继中选择（硬约束天然满足，SL/EV=100%）
      - 使用 A* 启发式：优先选择出度更高（更"核心/热门"）的候选节点，模拟传统图算法
        "缺乏语义理解、倾向于选择热门节点"的局限
      - 显式剔除已访问节点，保证不产生死循环（LR=100%）
      - 不引入任何自然语言语义信息，因此其局限性将体现在 SC（语义连贯性）指标上
    """
    path = [start_node]
    visited = {start_node}
    curr = start_node

    for _ in range(max_steps):
        candidates = kg_cache.get(curr, [])
        unvisited = [c for c in candidates if c not in visited]
        if not unvisited:
            break
        # A* 代价函数: f = g(每步代价相同=1) + h(=-出度，出度越高优先级越高)
        unvisited.sort(key=lambda c: -out_degree_map.get(c, 0))
        top_k = unvisited[: max(1, min(3, len(unvisited)))]
        next_node = random.choice(top_k)

        path.append(next_node)
        visited.add(next_node)
        curr = next_node

    return " -> ".join(path)


# ================= 2. 基线二：GRU/LSTM 序列推荐 =================
def build_pseudo_training_sequences(kg_cache, num_walks, walk_len_range):
    """
    用图谱随机游走构造伪训练序列（详见脚本顶部说明）。
    若你已有真实学习者交互序列（如 [[c1,c2,c3,...], [c5,c9,...], ...]），
    请直接替换本函数的返回值。
    """
    nodes = [k for k, v in kg_cache.items() if len(v) > 0]
    sequences = []
    for _ in range(num_walks):
        start = random.choice(nodes)
        walk_len = random.randint(*walk_len_range)
        seq = [start]
        curr = start
        for _ in range(walk_len - 1):
            nexts = kg_cache.get(curr, [])
            if not nexts:
                break
            curr = random.choice(nexts)
            seq.append(curr)
        if len(seq) >= 3:
            sequences.append(seq)
    return sequences


class Seq2NextDataset(torch.utils.data.Dataset):
    """(输入前缀, 目标下一个概念) 样本对"""
    def __init__(self, sequences, vocab):
        self.samples = []
        for seq in sequences:
            ids = [vocab[c] for c in seq if c in vocab]
            for i in range(1, len(ids)):
                self.samples.append((ids[:i], ids[i]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


def collate_fn(batch):
    prefixes, targets = zip(*batch)
    max_len = max(len(p) for p in prefixes)
    padded = torch.zeros(len(prefixes), max_len, dtype=torch.long)
    lengths = torch.zeros(len(prefixes), dtype=torch.long)
    for i, p in enumerate(prefixes):
        padded[i, : len(p)] = torch.tensor(p, dtype=torch.long)
        lengths[i] = len(p)
    targets = torch.tensor(targets, dtype=torch.long)
    return padded, lengths, targets


class RNNRecommender(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_dim, rnn_type="GRU"):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        rnn_cls = nn.GRU if rnn_type.upper() == "GRU" else nn.LSTM
        self.rnn = rnn_cls(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x, lengths):
        emb = self.embedding(x)
        packed = nn.utils.rnn.pack_padded_sequence(emb, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, hidden = self.rnn(packed)
        h_n = hidden[0] if isinstance(hidden, tuple) else hidden  # LSTM 返回 (h_n, c_n)，GRU 只返回 h_n
        last_hidden = h_n[-1]  # shape: [batch, hidden_dim]
        return self.fc(last_hidden)

    def step(self, x_ids, hidden=None):
        """单步推理：给定当前 token（张量, shape=[1,1]）与历史隐状态，返回下一个概念的 logits 及更新后的隐状态"""
        emb = self.embedding(x_ids)
        out, hidden = self.rnn(emb, hidden)
        logits = self.fc(out[:, -1, :])
        return logits, hidden


def train_rnn_recommender(kg_cache, device):
    print(f"🧩 [GRU/LSTM 基线] 正在构造伪训练序列（{NUM_WALKS_FOR_TRAINING} 条随机游走）...")
    sequences = build_pseudo_training_sequences(kg_cache, NUM_WALKS_FOR_TRAINING, WALK_LEN_RANGE)

    vocab_nodes = sorted({n for seq in sequences for n in seq})
    vocab = {n: i + 1 for i, n in enumerate(vocab_nodes)}  # 0 留给 padding
    id2node = {i: n for n, i in vocab.items()}
    vocab_size = len(vocab) + 1

    dataset = Seq2NextDataset(sequences, vocab)
    loader = torch.utils.data.DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)

    model = RNNRecommender(vocab_size, EMBED_DIM, HIDDEN_DIM, RNN_TYPE).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    print(f"🚀 [GRU/LSTM 基线] 开始训练（{RNN_TYPE}, {TRAIN_EPOCHS} epochs, 样本数={len(dataset)}）...")
    model.train()
    for epoch in range(TRAIN_EPOCHS):
        total_loss = 0.0
        for x, lengths, y in loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x, lengths)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"   Epoch {epoch + 1}/{TRAIN_EPOCHS}  Loss={total_loss / len(loader):.4f}")

    model.eval()
    return model, vocab, id2node


def generate_gru_path(model, vocab, id2node, start_node, device, max_steps=MAX_STEPS):
    """
    GRU/LSTM 基线推理：不做任何图谱约束，直接从全词表 softmax 中采样，
    因此存在生成非法边（结构性幻觉）的可能——这正是与 Ours(Fusion) 的核心差异所在。
    """
    if start_node not in vocab:
        return start_node  # 起点不在训练词表中，直接返回单节点路径

    path = [start_node]
    input_ids = torch.tensor([[vocab[start_node]]], dtype=torch.long).to(device)
    hidden = None

    with torch.no_grad():
        for _ in range(max_steps):
            logits, hidden = model.step(input_ids[:, -1:], hidden)
            probs = torch.softmax(logits, dim=-1).squeeze(0)
            next_id = torch.multinomial(probs, num_samples=1).item()
            if next_id == 0 or next_id not in id2node:
                break
            next_node = id2node[next_id]
            path.append(next_node)
            input_ids = torch.cat([input_ids, torch.tensor([[next_id]], device=device)], dim=1)

    return " -> ".join(path)


# ================= 3. 指标计算：SL / LR / EV / SC =================
def compute_sl_lr(path_list_strs, kg_cache):
    """SL: 路径级结构合法率的整体平均；LR: 无环率"""
    total_paths, total_sl, loop_free_count = 0, 0.0, 0
    for line in path_list_strs:
        nodes = [n.strip() for n in line.split("->") if n.strip()]
        if len(nodes) < 2:
            continue
        total_paths += 1
        legal_edges, total_edges = 0, len(nodes) - 1
        for i in range(total_edges):
            if nodes[i] in kg_cache and nodes[i + 1] in kg_cache[nodes[i]]:
                legal_edges += 1
        total_sl += legal_edges / total_edges if total_edges > 0 else 0
        if len(set(nodes)) == len(nodes):
            loop_free_count += 1
    if total_paths == 0:
        return 0.0, 0.0
    return (total_sl / total_paths) * 100, (loop_free_count / total_paths) * 100


def compute_edge_validity(path_list_strs, kg_cache):
    """EV: 全局边级别的关系真实性（与脚本十 evaluate_edge_validity 口径一致，取所有边的整体占比而非按路径平均）"""
    total_edges, valid_edges = 0, 0
    for line in path_list_strs:
        nodes = [n.strip() for n in line.split("->") if n.strip()]
        for i in range(len(nodes) - 1):
            total_edges += 1
            if nodes[i + 1] in kg_cache.get(nodes[i], []):
                valid_edges += 1
    return (valid_edges / total_edges * 100) if total_edges > 0 else 0.0


def compute_semantic_coherence(path_list_strs, sbert_model):
    """SC: 基于 Sentence-BERT 的相邻节点语义余弦相似度均值（与论文口径一致，替代早期字面 Jaccard 近似版本）"""
    all_nodes = sorted({n.strip() for line in path_list_strs for n in line.split("->") if n.strip()})
    if not all_nodes:
        return 0.0
    embeddings = sbert_model.encode(all_nodes, normalize_embeddings=True, show_progress_bar=False)
    emb_map = {n: e for n, e in zip(all_nodes, embeddings)}

    scores = []
    for line in path_list_strs:
        nodes = [n.strip() for n in line.split("->") if n.strip()]
        if len(nodes) < 2:
            continue
        sims = []
        for i in range(len(nodes) - 1):
            e1, e2 = emb_map[nodes[i]], emb_map[nodes[i + 1]]
            sims.append(float(np.dot(e1, e2)))  # 已归一化，点积即余弦相似度
        if sims:
            scores.append(sum(sims) / len(sims))

    return (sum(scores) / len(scores) * 100) if scores else 0.0


def evaluate_all_metrics(path_list_strs, kg_cache, sbert_model, label):
    sl, lr = compute_sl_lr(path_list_strs, kg_cache)
    ev = compute_edge_validity(path_list_strs, kg_cache)
    sc = compute_semantic_coherence(path_list_strs, sbert_model)
    return {"Method": label, "SL(%)": round(sl, 2), "LR(%)": round(lr, 2),
            "EV(%)": round(ev, 2), "SC(%)": round(sc, 2)}


# ================= 4. 主程序 =================
if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"⚙️ 运行设备: {device}")

    kg_cache, entity_set = load_kg()
    driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

    print("⏳ 正在加载 Sentence-BERT 模型（用于计算 SC 指标，首次运行需联网下载权重）...")
    sbert_model = SentenceTransformer(SBERT_MODEL_NAME, device=device)

    valid_starts = [k for k, v in kg_cache.items() if len(v) > 2]
    test_starts = random.sample(valid_starts, min(SAMPLE_SIZE, len(valid_starts)))
    print(f"✅ 已抽取 {len(test_starts)} 个测试起点。")

    # ---------- 基线一：A*/BFS + 先修约束 ----------
    print("\n🚀 [1/2] 正在生成 A*/BFS+先修约束 基线路径...")
    out_degree_map = get_out_degree_map(driver)
    astar_paths = [generate_astar_path(s, kg_cache, out_degree_map) for s in tqdm(test_starts, desc="A*/BFS")]

    # ---------- 基线二：GRU/LSTM 序列推荐 ----------
    print(f"\n🚀 [2/2] 正在训练并生成 {RNN_TYPE} 序列推荐 基线路径...")
    rnn_model, vocab, id2node = train_rnn_recommender(kg_cache, device)
    gru_paths = [generate_gru_path(rnn_model, vocab, id2node, s, device) for s in tqdm(test_starts, desc=RNN_TYPE)]

    # ---------- 汇总评估 ----------
    print("\n📊 正在计算 SL / LR / EV / SC 四项指标...")
    results = [
        evaluate_all_metrics(astar_paths, kg_cache, sbert_model, "A*/BFS+先修约束"),
        evaluate_all_metrics(gru_paths, kg_cache, sbert_model, f"{RNN_TYPE}序列推荐"),
    ]

    # 若已存在 Ours(Fusion) 的生成结果文件，一并计入对比表，方便直接生成完整表3
    if os.path.exists(FUSION_RESULT_FILE):
        with open(FUSION_RESULT_FILE, "r", encoding="utf-8") as f:
            fusion_paths = [line.strip() for line in f if line.strip()]
        results.append(evaluate_all_metrics(fusion_paths, kg_cache, sbert_model, "Ours (Fusion)"))
    else:
        print(f"ℹ️ 未找到 {FUSION_RESULT_FILE}，对比表中将不包含 Ours(Fusion) 行；"
              f"如需一并展示，请先运行融合生成脚本得到该文件。")

    print("\n" + "=" * 90)
    print("📊 表3 新增基线对比（A*/BFS、GRU/LSTM 与 Ours）")
    print("=" * 90)
    print(f"{'方法':<20} | {'SL(%)':<8} | {'LR(%)':<8} | {'EV(%)':<8} | {'SC(%)'}")
    print("-" * 90)
    for row in results:
        print(f"{row['Method']:<20} | {row['SL(%)']:<8} | {row['LR(%)']:<8} | {row['EV(%)']:<8} | {row['SC(%)']}")
    print("=" * 90)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"💾 结果已保存至 {OUTPUT_CSV}，可直接粘贴入论文表3。")

    driver.close()