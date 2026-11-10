/* =========================================================================
 * engine.js —— 个性化学习路径推荐引擎（前端复刻版）
 *
 * 严格对齐 Title2/8_dynamic_path_evolution.py 的算法逻辑：
 *   1) 学习者四维画像（尽责性C / 神经质N / 开放性O / 时间压力τ）
 *   2) 双时间尺度状态演化（快尺度情绪 + 慢尺度能力）
 *   3) 目标保持的滚动重规划（Replanner 束搜索 + 稳定性正则）
 *   4) 类型化反馈路由（认知补救 REM / 情感恢复 REST / 目标尝试 GOAL）
 *
 * 策略：static（静态规划+局部修补）、evolve（+双态演化）、roll（+滚动重规划）
 * ===================================================================== */

const CLAMP = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));

const CFG = {
  GAP_PENALTY: 0.25,     // 持续缺口惩罚
  ALPHA_GOAL: 0.80,      // 目标尝试的情感失败系数
  ALPHA_REM: 0.36,       // 补救尝试的情感失败系数
  DROPOUT: 0.95,         // 退出阈值
  SWITCH: 0.70,          // 转恢复的资源切换阈值
  WINDOW: 5,             // 慢尺度更新窗口
};

/* ------------------------------ 知识图谱 ------------------------------ */
class KG {
  constructor(data) {
    this.nodes = {};           // id -> {d, o}
    this.succ = {};            // id -> [succ]
    this.pred = {};            // id -> [pred]
    for (const n of data.nodes) {
      this.nodes[n.id] = { d: n.d, o: n.o };
      this.succ[n.id] = [];
      this.pred[n.id] = [];
    }
    for (const [u, v] of data.edges) {
      if (this.succ[u]) this.succ[u].push(v);
      if (this.pred[v]) this.pred[v].push(u);
    }
    /* 下游覆盖度：掌握该概念后能解锁多少后续概念（归一化），
       用于“先学枢纽还是先拿快目标”的取舍 */
    this.descCount = {};
    let mx = 1;
    for (const n of Object.keys(this.nodes)) {
      const seen = new Set(), st = [n];
      while (st.length) {
        const u = st.pop();
        for (const v of this.succ[u]) if (!seen.has(v)) { seen.add(v); st.push(v); }
      }
      this.descCount[n] = seen.size;
      if (seen.size > mx) mx = seen.size;
    }
    this._maxDesc = Math.log1p(mx);
  }
  /* 归一化的下游价值 0~1 */
  value(n) {
    return Math.log1p(this.descCount[n] || 0) / this._maxDesc;
  }
  d(n) { return this.nodes[n] ? this.nodes[n].d : 0.5; }
  succOf(n) { return this.succ[n] || []; }
  predOf(n) { return this.pred[n] || []; }

  /* 严格先修：难度至少低 0.05 的直接前驱中最容易者 */
  easierPred(n) {
    const cand = this.predOf(n).filter(p => this.d(p) <= this.d(n) - 0.05);
    if (!cand.length) return null;
    return cand.reduce((a, b) => (this.d(a) <= this.d(b) ? a : b));
  }

  /* 最短通路（BFS，用于桥梁节点与绕行成本） */
  shortestPath(s, t) {
    if (s === t) return [];
    if (!this.nodes[s] || !this.nodes[t]) return null;
    const prev = {};
    const q = [s];
    const seen = new Set([s]);
    while (q.length) {
      const cur = q.shift();
      if (cur === t) break;
      for (const nx of this.succOf(cur)) {
        if (!seen.has(nx)) { seen.add(nx); prev[nx] = cur; q.push(nx); }
      }
    }
    if (!(t in prev) && s !== t) return null;
    const path = [];
    let c = t;
    while (c !== s) { path.unshift(c); c = prev[c]; if (c === undefined) return null; }
    return path.slice(0, -1); // 不含两端
  }

  /* 抽取一个学习任务：起点 + 若干待掌握目标（难度分层） */
  sampleProblem(rng, nTargets = 8) {
    const starts = Object.keys(this.nodes)
      .filter(n => this.succOf(n).length > 0 && this.d(n) < 0.45);
    rng.shuffle(starts);
    for (const s0 of starts) {
      // 计算从 s0 可达的节点并按难度排序
      const reachSet = new Set();
      const q = [s0];
      while (q.length) {
        const c = q.shift();
        for (const nx of this.succOf(c)) if (!reachSet.has(nx)) { reachSet.add(nx); q.push(nx); }
      }
      const reach = [...reachSet].sort((a, b) => this.d(a) - this.d(b));
      if (reach.length < nTargets * 3) continue;
      const third = Math.floor(reach.length / 3);
      const picks = [];
      for (const bucket of [reach.slice(0, third), reach.slice(third, 2 * third), reach.slice(2 * third)]) {
        const take = Math.min(3, bucket.length);
        if (take) picks.push(...rng.sample(bucket, take));
      }
      if (picks.length < nTargets) continue;
      const final = picks.length > nTargets ? rng.sample(picks, nTargets) : picks;
      rng.shuffle(final);
      return [s0, ...final];
    }
    // 兜底：取前 nTargets+1 个节点
    const all = Object.keys(this.nodes);
    return all.slice(0, nTargets + 1);
  }
}

/* ------------------------------ 学习者画像 ------------------------------ */
class Learner {
  constructor(proto, ability, emotion, budget = 50) {
    this.conscientiousness = proto.conscientiousness;
    this.neuroticism = proto.neuroticism;
    this.openness = proto.openness;
    this.pressure = proto.pressure;
    this.ability = ability;
    this.emotion = emotion;
    this.budget = budget;
    this._peak = emotion;
  }
  get emotionBaseline() {
    return CLAMP(0.12 + 0.40 * this.neuroticism + 0.15 * this.pressure);
  }
  get reversion() { return 0.08 + 0.12 * (1.0 - this.neuroticism); }
  get failGain() { return 0.12 + 0.06 * this.neuroticism; }
  get growthRate() { return 0.03 + 0.05 * this.conscientiousness; }
  get videoEfficacy() {
    return CLAMP(0.60 + 0.25 * this.openness + 0.10 * (1 - this.neuroticism), 0.30, 0.95);
  }
  fastUpdate(event) {
    let e = this.emotion + this.reversion * (this.emotionBaseline - this.emotion);
    if (event === "FAIL") e += this.failGain;
    else if (event === "REST") e -= 0.25;
    else if (event === "PASS") e -= 0.04;
    else if (event === "REM") e -= 0.03;
    this.emotion = CLAMP(e);
  }
  slowUpdate(windowSuccess) {
    const gain = this.growthRate * (1.0 - this.ability) * Math.max(0.0, windowSuccess - 0.50);
    this.ability = CLAMP(this.ability + gain);
  }
}

/* ------------------------------ 概率模型 ------------------------------ */
function pAffective(learner, remedial) {
  const alpha = remedial ? CFG.ALPHA_REM : CFG.ALPHA_GOAL;
  return CLAMP(alpha * learner.emotion);
}
function pSuccess(learner, difficulty, gap, remedial, modulated = true, prep = 0) {
  const bonus = remedial && modulated ? 0.04 * learner.conscientiousness : 0.0;
  const val = learner.ability - 0.60 * difficulty + 0.40 + 0.35 * prep
    + bonus - (gap ? CFG.GAP_PENALTY : 0.0);
  return CLAMP(val, 0.05, 0.95);
}
function readiness(kg, node, learned) {
  const preds = kg.predOf(node);
  if (!preds.length) return 1.0;
  return preds.reduce((s, u) => s + (learned.has(u) ? 1 : 0), 0) / preds.length;
}
function risk(learner, node, kg, gap = false, remedial = false, modulated = true, prep = 0) {
  const pa = pAffective(learner, remedial);
  const ps = pSuccess(learner, kg.d(node), gap, remedial, modulated, prep);
  return pa + (1.0 - pa) * (1.0 - ps);
}

/* ------------------------------ 规划器 ------------------------------ */
class Replanner {
  constructor(kg) {
    this.kg = kg;
    this._cache = {};
    this._prevHead = null;
    this.hopThreshold = 0.45;
  }
  targetDifficulty(learner) {
    return CLAMP(0.30 + 0.45 * learner.ability - 0.25 * learner.emotion, 0.25, 0.85);
  }
  /* 性格进入目标函数的权重：同一份图谱、同一组目标，不同性格的学生应当得到不同的排序 */
  /* 跳步意愿：允许在多高的失败风险下直接跳到目标，而不先补中间节点。
     神经质高 → 不敢跳；开放性高 → 愿意冒一点险；时间压力大 → 想少绕路。 */
  hopThresholdFor(learner) {
    const N = learner.neuroticism, O = learner.openness;
    const T = learner.pressure == null ? 0.30 : learner.pressure;
    return CLAMP(0.30 + 0.45 * (1 - N) + 0.15 * O - 0.10 * T, 0.30, 0.85);
  }
  /* 单段最多愿意绕几个桥梁节点：尽责性高更愿意补齐先修，时间压力大则压短 */
  maxBridgeFor(learner) {
    const C = learner.conscientiousness;
    const T = learner.pressure == null ? 0.30 : learner.pressure;
    return Math.max(1, Math.round(2 + 3 * C - 2 * T));
  }
  /* 排序权重：五项指标的份额，和为 1。由画像决定，界面上直接显示。 */
  weights(learner) {
    const C = learner.conscientiousness, N = learner.neuroticism;
    const O = learner.openness, T = learner.pressure == null ? 0.30 : learner.pressure;
    const raw = {
      risk: 0.55 + 0.75 * N + 0.20 * T,                    // 风险规避：神经质高/时间紧 → 更怕失败
      diff: 0.90 - 0.55 * O,                               // 舒适区：开放性高 → 容忍更难的节点
      gap: 0.30 + 0.70 * C,                                // 先修完备：尽责性高 → 不愿跳过未掌握的前驱
      detour: 0.45 * (1 + 0.60 * T) * (1 - 0.40 * O),      // 绕行成本：时间紧 → 少绕路
      value: (0.10 + 1.45 * C) * (1 - 0.50 * T),           // 长期价值：尽责性高 → 先打枢纽；时间紧 → 先拿快目标
    };
    const sum = raw.risk + raw.diff + raw.gap + raw.detour + raw.value;
    return {
      risk: raw.risk / sum, diff: raw.diff / sum, gap: raw.gap / sum,
      detour: raw.detour / sum, value: raw.value / sum,
    };
  }
  /* 单个候选的五项指标（均为 0~1 量纲，便于按权重合成） */
  terms(learner, node, cur, visited, mastered) {
    let bridge;
    if (node === cur || this.kg.succOf(cur).includes(node)) bridge = 0;
    else {
      const b = this._bridge(cur, node);
      bridge = b.length ? b.length : 6;
    }
    const prep = readiness(this.kg, node, mastered);
    return {
      risk: risk(learner, node, this.kg, false, false, true, prep),
      diff: Math.min(1, Math.abs(this.kg.d(node) - this.targetDifficulty(learner)) / 0.60),
      gap: Math.max(0, 1 - prep),
      detour: Math.min(bridge, 6) / 6,
      value: this.kg.value(node),
      visited: visited && visited.has(node) ? 1 : 0,
    };
  }
  /* 归一化加权：先把各指标在本步候选内缩放到同一量纲，再按画像权重合成 */
  rank(learner, pool, cur, visited, mastered, stabBonus) {
    const w = this.weights(learner);
    const rows = pool.map(t => ({ t, x: this.terms(learner, t, cur, visited, mastered) }));
    const mx = { risk: 0, diff: 0, gap: 0 };
    rows.forEach(r => {
      mx.risk = Math.max(mx.risk, r.x.risk);
      mx.diff = Math.max(mx.diff, r.x.diff);
      mx.gap = Math.max(mx.gap, r.x.gap);
    });
    const nz = (v, m) => (m > 1e-9 ? v / m : 0);
    rows.forEach(r => {
      r.j = w.risk * nz(r.x.risk, mx.risk)
        + w.diff * nz(r.x.diff, mx.diff)
        + w.gap * nz(r.x.gap, mx.gap)
        + w.detour * r.x.detour
        - w.value * r.x.value
        + 0.15 * r.x.visited
        - (stabBonus && stabBonus.t === r.t ? stabBonus.v : 0);
    });
    rows.sort((a, b) => a.j - b.j);
    return rows;
  }
  _bridge(start, goal) {
    if (start === goal) return [];
    const key = start + "|" + goal;
    if (key in this._cache) return this._cache[key];
    const p = this.kg.shortestPath(start, goal);
    const out = p ? p : [];
    this._cache[key] = out;
    return out;
  }
  /* 兼容用的标量打分（界面展示"为什么排它第一"时调用） */
  score(learner, node, cur, visited, mastered) {
    const w = this.weights(learner);
    const x = this.terms(learner, node, cur, visited, mastered);
    return w.risk * x.risk + w.diff * x.diff + w.gap * x.gap
      + w.detour * x.detour - w.value * x.value + 0.15 * x.visited;
  }
  plan(learner, start, remaining, lamStab = 0.35, maxBridge = 4, visited = null, mastered = null) {
    mastered = mastered || new Set();
    visited = visited || new Set();
    const pool = remaining.filter(r => r !== start);
    if (!pool.length) return [];

    /* 逐位贪心：每一步都以「当前所在节点」为参照重新打分，
       这样前一步学了什么、当前情绪与能力如何，都会改变下一步选谁。 */
    const seq = [];
    const sched = new Set();
    const doneSet = () => {
      const s = new Set(mastered);
      sched.forEach(n => s.add(n));
      return s;
    };
    let cur = start;
    const prevHead = this._prevHead;

    while (pool.length) {
      const bonus = prevHead && seq.length === 0 ? { t: prevHead, v: lamStab } : null;
      const ranked = this.rank(learner, pool, cur, visited, doneSet(), bonus);
      if (!ranked.length) break;
      const best = ranked[0].t;
      pool.splice(pool.indexOf(best), 1);

      if (cur === best || this.kg.succOf(cur).includes(best)) {
        seq.push(best); sched.add(best); cur = best; continue;
      }
      if (risk(learner, best, this.kg, false, false, true, readiness(this.kg, best, doneSet())) <= this.hopThresholdFor(learner)) {
        seq.push(best); sched.add(best); cur = best; continue;
      }
      const bridges = (this._bridge(cur, best) || []).filter(b => b !== cur && !sched.has(b) && b !== best);
      const cap = Math.min(maxBridge, this.maxBridgeFor(learner));
      if (bridges.length && bridges.length <= cap) {
        for (const b of bridges) { seq.push(b); sched.add(b); cur = b; }
      }
      seq.push(best); sched.add(best); cur = best;
    }

    this._prevHead = seq.length ? seq[0] : null;
    return seq;
  }
}

/* ------------------------------ 路径差异度 ------------------------------ */
function lcsLen(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
  return dp[m][n];
}
function pathDivergence(oldP, newP) {
  if (!oldP.length || !newP.length) return 0;
  return 1 - lcsLen(oldP, newP) / Math.max(oldP.length, newP.length);
}

/* ------------------------------ 执行一集 ------------------------------ */
function runEpisode(kg, planner, learner, initial, strategy, rng, opts = {}) {
  const {
    replanEvery = 8, lamStab = 0.50, lag = 0, shock = null, known = null,
  } = opts;

  const ep = {
    strategy,
    completed: false,
    mastery: 0,
    peakEmotion: 0,
    steps: 0,
    dropout: false,
    replans: 0,
    divergence: [],
    switches: 0,
    remedial: 0,
    rest: 0,
    hist: [],           // 已访问路径（可视化）
    emotionTrail: [],   // 情绪轨迹
    abilityTrail: [],   // 能力轨迹
    actionTrail: [],    // 动作轨迹
    planTrail: [],      // 每轮的计划快照（用于展示"改道"）
    stepLog: [],        // 每轮的结构化日志（用于事件流）
  };

  const useEvolve = strategy !== "static";
  const useRoll = strategy === "roll" || strategy === "roll_nostab";
  const stab = strategy === "roll_nostab" ? 0.0 : lamStab;

  const targets = initial.slice(1);
  const targetSet = new Set(targets);
  const learned = new Set([initial[0]]);
  if (known) known.forEach(n => learned.add(n));   // 按能力免修的先修概念
  const mastered = new Set();

  let plan;
  if (!useRoll) {
    planner._prevHead = null;
    plan = planner.plan(learner, initial[0], targets, 0.0, 4, new Set(), learned) || [...targets];
    planner._prevHead = null;
  } else {
    plan = [...targets];
  }
  let cur = initial[0];
  planner._prevHead = null;

  let blocked = null;
  const remediated = new Set();
  let lastAction = "GOAL";
  const hist = [initial[0]];
  let window = [];
  const emotionHist = [learner.emotion];
  let stuck = 0;
  let prevEmotion = learner.emotion;

  const observe = () => (lag <= 0 ? learner.emotion : emotionHist[Math.max(0, emotionHist.length - 1 - lag)]);
  const done = () => mastered.size >= targetSet.size;

  ep.emotionTrail.push(learner.emotion);
  ep.abilityTrail.push(learner.ability);
  ep.hist.push(initial[0]);

  for (let step = 1; step <= learner.budget; step++) {
    if (shock && step === shock.step) {
      if (shock.emotion != null) learner.emotion = CLAMP(learner.emotion + shock.emotion);
      if (shock.ability != null) learner.ability = CLAMP(learner.ability + shock.ability);
      learner._peak = Math.max(learner._peak, learner.emotion);
    }

    if (learner.emotion >= CFG.DROPOUT) {
      ep.dropout = true; ep.steps = step; break;
    }

    let replannedFlag = false;
    if (useRoll) {
      const fresh = targets.filter(t => !mastered.has(t));
      if (lastAction === "PASS") stuck = 0;
      else if (lastAction.startsWith("FAIL")) stuck += 1;
      const crossed = (prevEmotion < CFG.SWITCH && learner.emotion >= CFG.SWITCH)
        || (prevEmotion >= CFG.SWITCH && learner.emotion < CFG.SWITCH);
      const trigger = step === 1 || (step - 1) % replanEvery === 0 || stuck >= 2 || crossed;
      if (trigger && fresh.length) {
        let neu;
        if (stuck >= 2 && plan.length && targetSet.has(plan[0])) {
          neu = planner.plan(learner, cur, fresh, stab, 4, new Set(hist), learned);
        } else {
          const head = plan.length && targetSet.has(plan[0]) ? plan[0] : null;
          const rest = fresh.filter(t => t !== head);
          const tail = planner.plan(learner, head || cur, rest, stab, 4, new Set(hist), learned);
          neu = (head ? [head] : []).concat(tail || []);
          if (head === null) {
            neu = planner.plan(learner, cur, fresh, stab, 4, new Set(hist), learned);
          }
        }
        if (neu && neu.length && neu.join("|") !== plan.join("|")) {
          ep.switches += 1;
          ep.divergence.push(pathDivergence(plan, neu));
          ep.replans += 1;
          plan = neu;
          replannedFlag = true;
        }
      }
    }

    if (!plan.length) plan = targets.filter(t => !mastered.has(t));
    if (!plan.length || done()) {
      ep.completed = true; ep.steps = step - 1; break;
    }

    const curNode = plan[0];
    const role = targetSet.has(curNode) ? "target" : "bridge";
    const prepNow = readiness(kg, curNode, learned);
    if (risk(learner, curNode, kg, blocked === curNode, false, true, prepNow) > 0.60) {
      ep.mismatchSteps = (ep.mismatchSteps || 0) + 1;
    }

    const obs = observe();
    const remedialNode = kg.easierPred(curNode);
    let action;
    if (obs > CFG.SWITCH || lastAction === "FAIL_AFF") action = "REST";
    else if ((lastAction === "FAIL_COG" || lastAction === "FAIL") && remedialNode && !remediated.has(curNode)) action = "REM";
    else action = "GOAL";

    ep.actionTrail.push({ step, action, node: curNode, role, emotion: learner.emotion, ability: learner.ability });
    ep.planTrail.push({
      step, cur: curNode, role, action,
      plan: plan.slice(),
      replanned: replannedFlag,
      switches: ep.switches,
    });

    if (action === "REST") {
      ep.rest += 1;
      const restReason = obs > CFG.SWITCH ? "THRESHOLD" : "AFTER_FAIL";
      const efficacy = useEvolve ? learner.videoEfficacy : 0.80;
      if (rng.random() <= efficacy) { learner.fastUpdate("REST"); lastAction = "REST_OK"; }
      else { learner.fastUpdate("FAIL"); lastAction = "FAIL_AFF"; }
      prevEmotion = learner.emotion;
      learner._peak = Math.max(learner._peak, learner.emotion);
      emotionHist.push(learner.emotion);
      ep.emotionTrail.push(learner.emotion);
      ep.abilityTrail.push(learner.ability);
      ep.steps = step;
      ep.stepLog.push({
        step, node: curNode, role, action, result: lastAction,
        emotion: obs,            // 记录触发恢复时的观测负荷，而非恢复后的数值
        emotionAfter: learner.emotion,
        reason: restReason,
        ability: learner.ability,
        difficulty: kg.d(curNode), plan: plan.slice(), replanned: replannedFlag,
        mastered: mastered.size,
        rest: ep.rest, remedial: ep.remedial, switches: ep.switches,
      });
      continue;
    }

    const node = action === "REM" ? remedialNode : curNode;
    const gap = (blocked === curNode && !remediated.has(curNode) && action === "GOAL");
    if (rng.random() < pAffective(learner, action === "REM")) {
      learner.fastUpdate("FAIL");
      lastAction = "FAIL_AFF";
      window.push(0);
    } else {
      const ps = pSuccess(learner, kg.d(node), gap, action === "REM", useEvolve, readiness(kg, node, learned));
      if (rng.random() < ps) {
        if (action === "REM") {
          ep.remedial += 1;
          remediated.add(curNode);
          learner.fastUpdate("REM");
          lastAction = "REM_OK";
          window.push(1);
        } else {
          learner.fastUpdate("PASS");
          learned.add(curNode);
          if (role === "target") mastered.add(curNode);
          cur = curNode;
          blocked = null;
          plan = plan.slice(1);
          if (!hist.includes(node)) hist.push(node);
          lastAction = "PASS";
          window.push(1);
          if (done()) {
            ep.completed = true; ep.steps = step;
            ep.mastery = 100.0;
            ep.peakEmotion = Math.round(Math.max(learner._peak, learner.emotion) * 10000) / 10000;
            ep.emotionTrail.push(learner.emotion);
            ep.abilityTrail.push(learner.ability);
            ep.hist = hist.slice();
            ep.stepLog.push({
              step, node: curNode, role, action, result: "PASS",
              emotion: learner.emotion, ability: learner.ability,
              difficulty: kg.d(curNode), plan: plan.slice(),
              replanned: replannedFlag, mastered: mastered.size,
              rest: ep.rest, remedial: ep.remedial, switches: ep.switches,
            });
            return ep;
          }
        }
      } else {
        learner.fastUpdate("FAIL");
        if (action === "GOAL") blocked = curNode;
        lastAction = "FAIL_COG";
        window.push(0);
      }
    }

    if (useEvolve && window.length >= CFG.WINDOW) {
      learner.slowUpdate(window.reduce((a, b) => a + b, 0) / window.length);
      window = [];
    }

    prevEmotion = learner.emotion;
    learner._peak = Math.max(learner._peak, learner.emotion);
    ep.peakEmotion = Math.round(Math.max(learner._peak, learner.emotion) * 10000) / 10000;
    emotionHist.push(learner.emotion);
    ep.emotionTrail.push(learner.emotion);
    ep.abilityTrail.push(learner.ability);
    ep.steps = step;
    ep.stepLog.push({
      step, node: curNode, role, action, result: lastAction,
      emotion: learner.emotion, ability: learner.ability,
      difficulty: kg.d(curNode), plan: plan.slice(), replanned: replannedFlag,
      mastered: mastered.size,
      rest: ep.rest, remedial: ep.remedial, switches: ep.switches,
    });
  }

  ep.mastery = Math.round(((mastered.size + 1) / initial.length) * 10000) / 100;
  ep.peakEmotion = Math.round(Math.max(learner._peak, learner.emotion) * 10000) / 10000;
  ep.completed = done();
  ep.hist = hist.slice();
  return ep;
}

/* ------------------------------ RNG（可复现） ------------------------------ */
class RNG {
  constructor(seed = 20261108) {
    this.s = seed >>> 0;
  }
  next() {
    this.s = (this.s * 1664525 + 1013904223) >>> 0;
    return this.s / 4294967296;
  }
  random() { return this.next(); }
  shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(this.next() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }
  sample(arr, k) {
    const a = arr.slice();
    this.shuffle(a);
    return a.slice(0, k);
  }
}

/* ------------------------------ 导出 ------------------------------ */
if (typeof module !== "undefined") {
  module.exports = {
    KG, Learner, Replanner, RNG, runEpisode, pathDivergence, CLAMP, CFG,
    readiness, risk, pSuccess, pAffective,
  };
}
