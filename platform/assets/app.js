/* =========================================================================
 * app.js —— 平台交互层
 * 依赖：engine.js（与 Title2/8_dynamic_path_evolution.py 对齐的概率模型）
 *       echarts.min.js（本地）
 * 数据：data/graph.json、task.json、aggregate.json（由 Title2/10 号脚本导出）
 * ===================================================================== */

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const fmt = (v, d = 2) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d));
const clamp01 = (x) => Math.max(0, Math.min(1, x));

const S = {
  graph: null, task: null, agg: null, subjects: [], subject: null, viewSet: null,
  kg: null, planner: null,
  personas: [], persona: null,
  params: { C: .35, N: .70, O: .65, a: .42, e: .34, budget: 50, pressure: .30 },
  targets: [],
  epStatic: null, epDyn: null,
  idx: 0, timer: null, speed: 320, played: false,
  charts: {}, lastGraphState: null,
  prevPlan: null, planSeq: 0, cum: null,
};

/* ----------------------------- 数据加载 ----------------------------- */
async function loadJSON(p) {
  const r = await fetch(p, { cache: "no-store" });
  if (!r.ok) throw new Error(p + " 读取失败：" + r.status);
  return r.json();
}

async function boot() {
  try {
    const [graph, task, agg, subjects] = await Promise.all([
      loadJSON("data/graph.json"), loadJSON("data/task.json"),
      loadJSON("data/aggregate.json"), loadJSON("data/subjects.json").catch(() => null),
    ]);
    S.graph = graph; S.task = task; S.agg = agg;
    S.subjects = (subjects && subjects.subjects) || [];
  } catch (err) {
    document.querySelector(".wrap").innerHTML =
      '<div class="card"><h3>数据未就绪</h3><p class="small muted">' +
      "请先运行 <code>Title2/10_export_platform_data.py</code> 生成 data/*.json，" +
      "再通过 <code>server.py</code> 启动（直接双击 html 会被浏览器的本地文件策略拦截）。</p></div>";
    console.error(err);
    return;
  }
  buildKG();
  buildPersonas();
  renderPersonas();
  renderSliders();
  // 学科任务：默认第一个（计算机网络），没有 subjects.json 时退回 task.json
  if (S.subjects.length) {
    S.subject = S.subjects[0];
    S.task.start = S.subject.start;
    S.task.targets = S.subject.targets.slice();
    S.task.path = [S.subject.start, ...S.subject.targets];
    S.viewSet = new Set(S.subject.view);
  } else {
    S.viewSet = new Set(S.graph.view);
  }
  renderSubjectPick();
  renderTargets();
  bindUI();
  initCharts();
  updateKPI();
  renderGraphMeta();
  renderResults();
  drawGraph();
  applyPersona(S.personas[1]);
  doPlan();
  renderSubjectOverview();

  const q = new URLSearchParams(location.search);
  const v = q.get("view") || (location.hash ? location.hash.slice(1) : "home");
  switchView(v || "home");
  const fr = Number(q.get("frame") || 0);
  if (v === "dual") {
    resetPlayback();
    for (let i = 0; i < fr; i++) stepOnce();
  }
}

function buildKG() {
  const nodes = S.graph.nodes.map((n) => ({ id: n.id, d: n.difficulty, o: n.outdegree }));
  const edges = S.graph.edges.map((e) => [e.source, e.target]);
  S.kg = new KG({ nodes, edges });
  S.planner = new Replanner(S.kg);
}

function buildPersonas() {
  const base = S.task.personas.map((p) => ({
    id: p.id, name: p.name, desc: p.desc,
    C: p.conscientiousness, N: p.neuroticism, O: p.openness,
    a: p.ability, e: p.emotion, budget: p.budget, pressure: 0.30,
  }));
  base.push({
    id: "p4", name: "高压速成型", desc: "时间压力大、情绪阈值低，最容易在静态路径上掉队",
    C: 0.50, N: 0.80, O: 0.40, a: 0.40, e: 0.46, budget: 30, pressure: 0.70,
  });
  S.personas = base;
}

/* ----------------------------- 画像面板 ----------------------------- */
function renderSliders() {
  const defs = [
    ["C", "尽责性 C", "越高，能力增长与补救效力越强"],
    ["N", "神经质 N", "越高，情绪基线越高、失败越敏感"],
    ["O", "开放性 O", "越高，视频等恢复性资源越有效"],
    ["a", "初始能力 a", "决定条件成功概率"],
    ["e", "初始情绪负荷 e", "≥0.70 触发资源切换，≥0.95 退出"],
  ];
  const box = $("#sliders");
  box.innerHTML = "";
  defs.forEach(([k, label, tip]) => {
    const wrap = document.createElement("div");
    wrap.className = "field";
    wrap.innerHTML =
      `<label title="${tip}">${label}<b id="v-${k}">${fmt(S.params[k], 2)}</b></label>
       <input type="range" id="s-${k}" min="0" max="1" step="0.01" value="${S.params[k]}">`;
    box.appendChild(wrap);
    const inp = wrap.querySelector("input");
    inp.addEventListener("input", () => {
      S.params[k] = Number(inp.value);
      $("#v-" + k).textContent = fmt(S.params[k], 2);
      paintRange(inp);
      S.persona = null;
      $$("#personaList .persona").forEach((b) => b.classList.remove("on"));
      schedulePlan();
    });
    paintRange(inp);
  });
  $("#budget").addEventListener("input", (ev) => {
    S.params.budget = Number(ev.target.value);
    $("#budgetVal").textContent = S.params.budget;
    paintRange(ev.target);
    schedulePlan();
  });
  $("#pressure").addEventListener("input", (ev) => {
    S.params.pressure = Number(ev.target.value);
    $("#pressureVal").textContent = fmt(S.params.pressure, 2);
    paintRange(ev.target);
    schedulePlan();
  });
  paintRange($("#budget")); paintRange($("#pressure"));
}

let _planTimer = null;
function schedulePlan() {
  S.epStatic = null; S.epDyn = null;      // 画像已变，旧回放作废
  if (!$("#view-profile").classList.contains("active")) return;
  clearTimeout(_planTimer);
  _planTimer = setTimeout(() => {
    try { doPlan(); renderSubjectOverview(); } catch (e) { console.error(e); }
  }, 110);
}

function paintRange(inp) {
  if (!inp) return;
  const min = Number(inp.min), max = Number(inp.max), v = Number(inp.value);
  inp.style.setProperty("--pct", ((v - min) / (max - min) * 100) + "%");
}

function applyPersona(p) {
  S.persona = p;
  S.params = { C: p.C, N: p.N, O: p.O, a: p.a, e: p.e, budget: p.budget, pressure: p.pressure ?? 0.30 };
  ["C", "N", "O", "a", "e"].forEach((k) => {
    const inp = $("#s-" + k);
    if (inp) { inp.value = S.params[k]; paintRange(inp); $("#v-" + k).textContent = fmt(S.params[k], 2); }
  });
  $("#budget").value = S.params.budget; $("#budgetVal").textContent = S.params.budget; paintRange($("#budget"));
  $("#pressure").value = S.params.pressure; $("#pressureVal").textContent = fmt(S.params.pressure, 2); paintRange($("#pressure"));
  $$("#personaList .persona").forEach((b) => b.classList.toggle("on", b.dataset.id === p.id));
}

function renderPersonas() {
  const box = $("#personaList");
  box.innerHTML = "";
  S.personas.forEach((p) => {
    const b = document.createElement("button");
    b.className = "persona"; b.dataset.id = p.id;
    b.innerHTML = `<b>${p.name}</b><span>${p.desc}</span>`;
    b.onclick = () => { applyPersona(p); S.played = false; };
    box.appendChild(b);
  });
}

/* ----------------------------- 目标选择 ----------------------------- */
function renderTargets() {
  const box = $("#targetPick");
  box.innerHTML = "";
  const pool = S.task.targets.slice();
  S.targets = pool.slice();
  pool.forEach((t) => {
    const b = document.createElement("button");
    b.className = "chip-pick on"; b.dataset.t = t; b.textContent = t;
    b.onclick = () => {
      const on = b.classList.toggle("on");
      if (on) S.targets.push(t);
      else S.targets = S.targets.filter((x) => x !== t);
      if (!S.targets.length) { b.classList.add("on"); S.targets.push(t); }
      S.anc = null;
      $("#planMsg").textContent = "";
    };
    box.appendChild(b);
  });
  $("#taskHint").innerHTML =
    (S.subject ? `<b>${S.subject.name}</b>：${S.subject.desc}。` : "") +
    `起点为「${S.task.start}」，共 ${pool.length} 个待掌握目标，规划在全图 ${S.graph.meta.nodes} 个概念上进行。` +
    `目标可自由增减；取消勾选后路径会重新规划。`;
}

/* ----------------------------- 学科任务 ----------------------------- */
function renderSubjectPick() {
  const box = $("#subjectPick");
  if (!box) return;
  box.innerHTML = "";
  S.subjects.forEach((sj) => {
    const b = document.createElement("button");
    const on = S.subject && S.subject.id === sj.id;
    b.className = "chip-pick subj-chip" + (on ? " on" : "");
    b.textContent = sj.short;
    b.title = `${sj.name}：${sj.desc}`;
    b.onclick = () => { if (!(S.subject && S.subject.id === sj.id)) applySubject(sj); };
    box.appendChild(b);
  });
  const note = $("#subjNote");
  if (note && S.subject) note.textContent = `${S.subjects.length} 个学科任务，起点与目标均取自全图`;
}

/* 用当前画像把一个学科任务规划一次，返回展示用统计 */
function planStat(sj) {
  const lr = makeLearner();
  const pl = new Replanner(S.kg);
  const targets = sj.targets.slice();
  const unreachable = targets.filter((t) => t !== sj.start && !S.kg.shortestPath(sj.start, t));
  const p = pl.plan(lr, sj.start, targets, 0.35, 4, new Set(), new Set([sj.start])) || targets;
  const path = [sj.start, ...p];
  const bridges = path.filter((n) => n !== sj.start && !targets.includes(n));
  const dAvg = path.slice(1).reduce((s, n) => s + S.kg.d(n), 0) / Math.max(1, path.length - 1);
  const dStar = pl.targetDifficulty(lr);
  return { path, steps: path.length, bridges: bridges.length, dAvg, dStar, unreachable };
}

function applySubject(sj) {
  S.subject = sj;
  S.task.start = sj.start;
  S.task.targets = sj.targets.slice();
  S.task.path = [sj.start, ...sj.targets];
  S.viewSet = new Set(sj.view);
  S.targets = sj.targets.slice();
  S.anc = null; S.prevPlan = null;
  S.epStatic = null; S.epDyn = null;
  renderSubjectPick();
  renderTargets();
  renderGraphMeta();
  drawGraph();
  doPlan();
  renderSubjectOverview();
}

/* 跨学科对照：同一个学习者、同一张图谱，换学科后的路径差别 */
function renderSubjectOverview() {
  const box = $("#subjOverview");
  if (!box || !S.subjects.length) return;
  const rows = S.subjects.map((sj) => ({ sj, st: planStat(sj) }));
  const cur = rows.find((r) => S.subject && r.sj.id === S.subject.id);
  box.innerHTML = "";
  rows.forEach(({ sj, st }) => {
    const on = cur && cur.sj.id === sj.id;
    const diff = cur ? st.steps - cur.st.steps : 0;
    const el = document.createElement("div");
    el.className = "subj-card" + (on ? " on" : "");
    el.innerHTML =
      `<div class="nm">${sj.short}${on ? '<span class="badge">当前</span>' : ""}</div>
       <div class="st">起点「${sj.start}」· ${sj.targets.length} 个目标</div>
       <div class="st"><b>${st.steps}</b> 步 · 支架 <b>${st.bridges}</b> · 均难 <b>${fmt(st.dAvg, 2)}</b></div>
       <div class="st">${on ? `理想难度 d* ${fmt(st.dStar, 2)}` :
        (diff === 0 ? `与当前同样 ${st.steps} 步` : `比当前${diff > 0 ? "多" : "少"} ${Math.abs(diff)} 步`)}</div>
       <div class="pt">${st.path.slice(0, 4).join(" → ")}${st.path.length > 4 ? " …" : ""}</div>`;
    el.title = `${sj.name}：${sj.desc}\n完整路径：${st.path.join(" → ")}`;
    el.onclick = () => { if (!on) applySubject(sj); };
    box.appendChild(el);
  });
  const fn = $("#subjFootnote");
  if (fn) {
    fn.innerHTML =
      `同一名学习者（当前画像）在五个学科上分别需要 <b>${rows.map((r) => r.st.steps).join(" / ")}</b> 步。` +
      `路径长度与支架密度的差别来自三处：起点在学科中的位置、目标与起点的先修距离、` +
      `以及画像权重在"补前置"与"直接推进"之间的取舍。` +
      `各学科目标均取自全图原有概念并通过有向可达性校验；卡片按该学科的全部目标计算，不含上方手动取消的勾选。`;
  }
}

/* ----------------------------- 初始规划 ----------------------------- */
function makeLearner() {
  return new Learner(
    { conscientiousness: S.params.C, neuroticism: S.params.N, openness: S.params.O, pressure: S.params.pressure },
    S.params.a, S.params.e, S.params.budget
  );
}

function initialPlan() {
  const lr = makeLearner();
  S.planner._prevHead = null;
  const plan = S.planner.plan(lr, S.task.start, S.targets.slice(), 0.35, 4,
    new Set(), new Set([S.task.start])) || S.targets.slice();
  S.planner._prevHead = null;
  const path = [S.task.start, ...plan];
  return { path, lr, dStar: S.planner.targetDifficulty(lr), w: S.planner.weights(lr) };
}

function planDiffMsg(prev, cur) {
  if (!prev || !prev.length) return "";
  if (prev.join(">") === cur.join(">")) {
    return "与上一版相比：<b>路径未变</b>。这组目标在当前图谱里结构相近（难度、与起点的距离都接近），"
      + "本次改动只改变了排序权重，没有改变先后顺序。可以把「时间压力」或「初始能力」推得更大一些，再看排序是否翻转。";
  }
  let first = 0;
  while (first < Math.min(prev.length, cur.length) && prev[first] === cur[first]) first++;
  const added = cur.filter((x) => !prev.includes(x));
  const removed = prev.filter((x) => !cur.includes(x));
  const bits = [`第 <b>${first + 1}</b> 位起改变`];
  if (removed.length) bits.push(`省去「${removed.slice(0, 3).join("、")}」${removed.length > 3 ? " 等" : ""}`);
  if (added.length) bits.push(`补上「${added.slice(0, 3).join("、")}」${added.length > 3 ? " 等" : ""}`);
  bits.push(`路径长度 ${prev.length} → <b>${cur.length}</b>`);
  return "与上一版相比：" + bits.join("；") + "。";
}

function doPlan() {
  if (S.targets.length < 3) {
    $("#planMsg").textContent = "请至少选择 3 个学习目标。";
    return;
  }
  const r = initialPlan();
  const path = r.path;
  const box = $("#planPreview");
  box.innerHTML = "";
  path.forEach((n, i) => {
    const sp = document.createElement("span");
    sp.className = "pnode" + (i === 0 ? " head" : "");
    sp.textContent = n;
    sp.title = `结构难度 ${fmt(S.kg.d(n), 2)}${S.targets.includes(n) ? "　本任务目标" : "　支架节点"}`;
    box.appendChild(sp);
  });

  const bridges = path.filter((n) => n !== S.task.start && !S.targets.includes(n)).length;

  const dAvg = path.slice(1).reduce((s2, n) => s2 + S.kg.d(n), 0) / Math.max(1, path.length - 1);
  $("#planStats").innerHTML =
    `<span>规划步数 <b>${path.length}</b></span>
     <span>支架节点 <b>${bridges}</b></span>
     <span>平均难度 <b>${fmt(dAvg, 2)}</b></span>
     <span>理想难度 d* <b>${fmt(r.dStar, 2)}</b></span>`;

  const w = r.w;
  const rank = [["风险规避", w.risk], ["难度匹配", w.diff], ["先修完备", w.gap], ["绕行成本", w.detour], ["长期价值", w.value]]
    .sort((a, b) => b[1] - a[1]);
  $("#planWhy").innerHTML =
    `排序依据（按权重）：` + rank.map((x, i) => `${i === 0 ? "<b>" : ""}${x[0]} ${fmt(x[1], 2)}${i === 0 ? "</b>" : ""}`).join(" · ")
    + `<br>神经质 N=${fmt(S.params.N, 2)} 抬高风险权重，开放性 O=${fmt(S.params.O, 2)} 放宽难度容忍，`
    + `尽责性 C=${fmt(S.params.C, 2)} 加重先修完备与长期价值，时间压力 τ=${fmt(S.params.pressure, 2)} 压低绕行意愿；`
    + `能力 a=${fmt(S.params.a, 2)} 决定理想难度 d* 与各节点的失败风险。`
    + `<br><span id="planDiff">${planDiffMsg(S.prevPlan, path)}</span>`;

  S.prevPlan = path;
  S.planSeq += 1;
  $("#planMsg").textContent = "已按当前画像生成（调整滑块会自动重新规划）。";
  S.epStatic = null; S.epDyn = null;
}

/* ----------------------------- 仿真与回放 ----------------------------- */
function runBoth() {
  const seed = 20261108;
  const proto = {
    conscientiousness: S.params.C, neuroticism: S.params.N,
    openness: S.params.O, pressure: S.params.pressure,
  };
  const task = [S.task.start, ...S.targets];
  S.planner = new Replanner(S.kg);

  const l1 = new Learner(proto, S.params.a, S.params.e, S.params.budget);
  const l2 = new Learner(proto, S.params.a, S.params.e, S.params.budget);
  S.epStatic = runEpisode(S.kg, S.planner, l1, task, "static", new RNG(seed + 7), { replanEvery: 8, lamStab: .5 });
  S.epDyn = runEpisode(S.kg, S.planner, l2, task, "roll", new RNG(seed + 7), { replanEvery: 8, lamStab: .5 });
  S.idx = 0; S.played = false;
  resetTracks();
  updateCharts();
  renderAbilityNote();
  renderCumulative();
  updateSummary();
}

function resetTracks() {
  ["#trackStatic", "#trackDynamic"].forEach((sel) => {
    const t = $(sel);
    t.querySelector(".pathlist").innerHTML = "";
    t.querySelector(".feed").innerHTML = "";
    t.querySelector(".statline").innerHTML = "";
    t.querySelectorAll(".meter").forEach((m) => {
      m.querySelector("b").textContent = "—";
      m.querySelector("i").style.width = "0%";
    });
  });
  $("#roundLabel").textContent = "第 0 轮 / 共 0 轮";
  $("#tlFill").style.width = "0%";
  updateChartSeries(0);
}

function meters(track, lr, plan) {
  const set = (cls, v, txt) => {
    const m = track.querySelector("." + cls);
    m.querySelector("b").textContent = txt;
    m.querySelector("i").style.width = Math.round(clamp01(v) * 100) + "%";
  };
  set("ability", lr.ability, fmt(lr.ability, 2));
  set("emotion", lr.emotion, fmt(lr.emotion, 2));
}

function actionText(log) {
  const { action, result, node, role } = log;
  if (action === "REST") {
    if (log.reason === "AFTER_FAIL") {
      return { cls: "aff", html: `上一轮为情感性失败 → 再次切换<b>视频资源</b>恢复，暂缓「${node}」` };
    }
    return { cls: "aff", html: `观测负荷 <b>${fmt(log.emotion, 2)}</b> 超过阈值 0.70 → 切换<b>视频资源</b>恢复，暂缓「${node}」` };
  }
  if (action === "REM") {
    const easy = S.kg.easierPred(node);
    return { cls: "cog", html: `认知失败 → 插入<b>先修补救</b>「${easy || "—"}」，掌握后再回到「${node}」` };
  }
  if (result === "PASS") {
    return { cls: "ok", html: `尝试「${node}」（难度 ${fmt(log.difficulty, 2)}）→ <em>通过</em>，${role === "target" ? "掌握 +1" : "桥梁节点"}` };
  }
  if (result === "FAIL_COG") return { cls: "cog", html: `尝试「${node}」→ 认知失败（难度高于当前能力）` };
  if (result === "FAIL_AFF") return { cls: "aff", html: `尝试「${node}」→ 情绪性失败（焦虑抬升）` };
  return { cls: "", html: `尝试「${node}」` };
}

function renderFrame(trackSel, ep, i) {
  const track = $(trackSel);
  const log = ep.stepLog[i];
  const list = track.querySelector(".pathlist");
  const feed = track.querySelector(".feed");

  if (!log) {
    if (i === 0) {
      meterInit(track, ep);
      list.innerHTML = "";
      feed.innerHTML = "";
    }
    return;
  }

  // 已掌握集合（重放）
  const passed = new Set([S.task.start]);
  for (let k = 0; k <= i; k++) {
    const l = ep.stepLog[k];
    if (l.result === "PASS") passed.add(l.node);
  }

  // 路径
  list.innerHTML = "";
  const plan = log.plan.length ? log.plan : [];
  if (!plan.length) {
    const s = document.createElement("span");
    s.className = "pnode done"; s.textContent = "全部目标已掌握";
    list.appendChild(s);
  }
  plan.forEach((n, k) => {
    const s = document.createElement("span");
    s.className = "pnode" + (k === 0 ? " head" : "");
    if (passed.has(n)) s.classList.add("done");
    if (log.replanned && k > 0) s.classList.add("new");
    s.textContent = n;
    list.appendChild(s);
  });

  // 事件流
  feed.innerHTML = "";
  const start = Math.max(0, i - 14);
  for (let k = start; k <= i; k++) {
    const l = ep.stepLog[k];
    if (l.replanned) {
      const d = document.createElement("div");
      d.className = "fitem replan";
      const sw = l.switches != null ? l.switches : ep.switches;
      d.innerHTML = `<span class="no">↻</span><span class="txt">状态偏离预期 → <em>触发滚动重规划</em>，剩余目标重新排序（累计 ${sw} 次）</span>`;
      feed.appendChild(d);
    }
    const t = actionText(l);
    const d = document.createElement("div");
    d.className = "fitem " + t.cls;
    d.innerHTML = `<span class="no">${l.step}</span><span class="txt">${t.html}</span>`;
    feed.appendChild(d);
  }
  feed.scrollTop = feed.scrollHeight;

  // 状态条
  const m = track.querySelectorAll(".meter");
  m[0].querySelector("b").textContent = fmt(log.ability, 2);
  m[0].querySelector("i").style.width = Math.round(log.ability * 100) + "%";
  m[1].querySelector("b").textContent = fmt(log.emotion, 2);
  m[1].querySelector("i").style.width = Math.round(log.emotion * 100) + "%";

  // 统计行
  const nSw = log.switches != null ? log.switches : ep.switches;
  track.querySelector(".statline").innerHTML =
    `<span>已掌握 <b>${log.mastered}/${S.targets.length}</b></span>
     <span>重规划 <b>${nSw}</b> 次</span>
     <span>补救 <b>${log.remedial != null ? log.remedial : ep.remedial}</b></span>
     <span>恢复 <b>${log.rest != null ? log.rest : ep.rest}</b></span>`;
}

function meterInit(track, ep) {
  const m = track.querySelectorAll(".meter");
  m[0].querySelector("b").textContent = fmt(S.params.a, 2);
  m[0].querySelector("i").style.width = Math.round(S.params.a * 100) + "%";
  m[1].querySelector("b").textContent = fmt(S.params.e, 2);
  m[1].querySelector("i").style.width = Math.round(S.params.e * 100) + "%";
  track.querySelector(".statline").innerHTML =
    `<span>已掌握 <b>0/${S.targets.length}</b></span><span>重规划 <b>0</b> 次</span>
     <span>补救 <b>0</b></span><span>恢复 <b>0</b></span>`;
}

function totalRounds() {
  return Math.max(S.epStatic ? S.epStatic.stepLog.length : 0, S.epDyn ? S.epDyn.stepLog.length : 0);
}

function stepOnce() {
  const N = totalRounds();
  if (S.idx >= N) { pause(); return; }
  S.idx += 1;
  renderFrame("#trackStatic", S.epStatic, Math.min(S.idx - 1, S.epStatic.stepLog.length - 1));
  renderFrame("#trackDynamic", S.epDyn, Math.min(S.idx - 1, S.epDyn.stepLog.length - 1));
  $("#roundLabel").textContent = `第 ${S.idx} 轮 / 两轨较长者 ${N} 轮`;
  $("#tlFill").style.width = (S.idx / N * 100) + "%";
  updateChartSeries(S.idx);
  if (S.idx >= N) finishPlayback();
}

function finishPlayback() {
  pause();
  const d = S.epDyn, s = S.epStatic;
  $("#dualHint").innerHTML =
    `回放结束：静态路径在第 <b>${s.steps}</b> 轮${s.completed ? "完成" : "停止"}，峰值情绪 <b>${fmt(s.peakEmotion, 2)}</b>；` +
    `动态策略在第 <b>${d.steps}</b> 轮${d.completed ? "完成" : "停止"}，峰值情绪 <b>${fmt(d.peakEmotion, 2)}</b>，` +
    `期间触发重规划 <b>${d.switches}</b> 次、先修补救 <b>${d.remedial}</b> 次、视频恢复 <b>${d.rest}</b> 次。`;
}

function play() {
  if (!S.epStatic) runBoth();
  if (S.idx >= totalRounds()) resetPlayback();
  S.played = true;
  $("#btnPlay").textContent = "❚❚ 暂停";
  pause(true);
  S.timer = setInterval(stepOnce, S.speed);
}
function pause(keep) {
  if (S.timer) { clearInterval(S.timer); S.timer = null; }
  if (!keep) { $("#btnPlay").textContent = "▶ 继续"; S.played = false; }
}
function resetPlayback() {
  pause();
  S.idx = 0;
  const subjLab = $("#dualSubject");
  if (subjLab) subjLab.textContent = S.subject ? `学科：${S.subject.short}　` : "";
  runBoth();
  renderFrame("#trackStatic", S.epStatic, 0);
  renderFrame("#trackDynamic", S.epDyn, 0);
  $("#btnPlay").textContent = "▶ 开始回放";
  $("#dualHint").textContent = "左轨保持入学时的计划不变，只在执行期做局部修补；右轨每轮根据双态画像重新估计“下一步学什么”。";
}

/* ----------------------------- 图表 ----------------------------- */
function initCharts() {
  S.charts.emotion = echarts.init($("#chartEmotion"));
  S.charts.ability = echarts.init($("#chartAbility"));
  S.charts.summary = echarts.init($("#chartSummary"));
  S.charts.graph = echarts.init($("#chartGraph"));
  S.charts.strategies = echarts.init($("#chartStrategies"));
  S.charts.budget = echarts.init($("#chartBudget"));
  S.charts.hetero = echarts.init($("#chartHetero"));
  S.charts.cum = echarts.init($("#chartCum"));
  window.addEventListener("resize", () => Object.values(S.charts).forEach((c) => c && c.resize()));
}

const AXIS = {
  grid: { left: 44, right: 18, top: 30, bottom: 30 },
  tooltip: { trigger: "axis" },
  xAxis: { type: "category", boundaryGap: false, axisLine: { lineStyle: { color: "#dbe3ee" } }, axisLabel: { color: "#6b7a90", fontSize: 11 } },
  yAxis: { type: "value", min: 0, max: 1, splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { color: "#6b7a90", fontSize: 11 } },
};

function lineOption() {
  return {
    ...AXIS,
    legend: { right: 8, top: 2, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11, color: "#334155" } },
    series: [],
  };
}

function seriesOf(ep, name, color, key, n) {
  const data = [];
  for (let i = 0; i < n; i++) {
    const v = i < ep.stepLog.length ? ep.stepLog[i][key] : null;
    data.push(v == null ? null : Number(v.toFixed(3)));
  }
  return {
    name, type: "line", data, smooth: .25, symbol: "circle", symbolSize: 4,
    lineStyle: { width: 2, color }, itemStyle: { color },
    connectNulls: false,
  };
}

function updateCharts() {
  if (!S.epStatic) return;
  const n = totalRounds();
  const label = Array.from({ length: n }, (_, i) => i + 1);
  const mk = (key, name1, name2) => {
    const o = lineOption();
    o.xAxis.data = label;
    o.yAxis.max = 1;
    o.series = [
      seriesOf(S.epStatic, name1, "#8a99ad", key, n),
      seriesOf(S.epDyn, name2, "#1f5fa8", key, n),
    ];
    return o;
  };
  S.charts.emotion.setOption(mk("emotion", "静态", "动态（双态）"), true);

  const aOpt = mk("ability", "静态（不演化）", "动态（双态）");
  const [aLo, aHi] = abilityRange();
  aOpt.yAxis = Object.assign({}, aOpt.yAxis, {
    min: +aLo.toFixed(3), max: +aHi.toFixed(3),
    name: "能力 a（局部放大）", nameTextStyle: { fontSize: 10, color: "#6b7a90" },
    splitLine: { lineStyle: { color: "#eef2f7" } },
    axisLabel: { color: "#6b7a90", fontSize: 11, formatter: (v) => Number(v).toFixed(3) },
  });
  aOpt.grid = { left: 58, right: 18, top: 34, bottom: 30 };
  S.charts.ability.setOption(aOpt, true);

  S.charts.emotion.setOption({
    series: [{
      markLine: {
        silent: true, symbol: "none", label: { formatter: "切换 0.70", fontSize: 10, color: "#c47d15" },
        lineStyle: { type: "dashed", color: "#c47d15" }, data: [{ yAxis: 0.70 }],
      },
    }, {}],
  });
}

function abilityRange() {
  const vals = [];
  [S.epStatic, S.epDyn].forEach((ep) => ep && ep.stepLog.forEach((l) => vals.push(l.ability)));
  if (!vals.length) return [0, 1];
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max(0.008, (hi - lo) * 0.4);
  let a = Math.max(0, lo - pad), b = Math.min(1, hi + pad);
  if (b - a < 0.05) { const mid = (a + b) / 2; a = Math.max(0, mid - 0.025); b = Math.min(1, mid + 0.025); }
  return [a, b];
}

function renderAbilityNote() {
  if (!S.epStatic || !S.epDyn) return;
  const a0 = S.params.a;
  const sEnd = S.epStatic.abilityTrail.length ? S.epStatic.abilityTrail[S.epStatic.abilityTrail.length - 1] : a0;
  const dEnd = S.epDyn.abilityTrail.length ? S.epDyn.abilityTrail[S.epDyn.abilityTrail.length - 1] : a0;
  const pp = (x) => ((x - a0) * 100).toFixed(1);
  $("#abilNote").innerHTML =
    `入学 a=<b>${fmt(a0, 3)}</b>；单次任务后 静态 <b>${fmt(sEnd, 3)}</b>（${pp(sEnd) >= 0 ? "+" : ""}${pp(sEnd)} pp，不演化），`
    + `双态 <b>${fmt(dEnd, 3)}</b>（${pp(dEnd) >= 0 ? "+" : ""}${pp(dEnd)} pp）。`
    + `能力是慢变量，单次任务的增幅本来就小，纵轴已按实际范围放大；累积效应见图「慢变量的累积效应」。`;
}

function cumTrail(strategy, C) {
  const lr = new Learner(
    { conscientiousness: C, neuroticism: S.params.N, openness: S.params.O, pressure: S.params.pressure },
    S.params.a, S.params.e, S.params.budget
  );
  const trail = [lr.ability];
  for (let k = 0; k < 5; k++) {
    runEpisode(S.kg, new Replanner(S.kg), lr, [S.task.start, ...S.targets], strategy,
      new RNG(7100 + k * 137), { replanEvery: 8, lamStab: .5 });
    trail.push(+lr.ability.toFixed(4));
  }
  return trail;
}

function renderCumulative() {
  if (!S.charts.cum) return;
  const flat = cumTrail("static", S.params.C);
  const cur = cumTrail("roll", S.params.C);
  const series = [
    { name: "静态（不演化）", type: "line", data: flat, symbol: "circle", symbolSize: 5,
      lineStyle: { color: "#9aa8ba", width: 2, type: "dashed" }, itemStyle: { color: "#9aa8ba" } },
    { name: `双态（C=${fmt(S.params.C, 2)}）`, type: "line", data: cur, symbol: "circle", symbolSize: 5,
      lineStyle: { color: "#1f5fa8", width: 2.4 }, itemStyle: { color: "#1f5fa8" } },
  ];
  if (S.params.C < 0.9) {
    series.push({ name: "双态（C=0.95 参照）", type: "line", data: cumTrail("roll", 0.95), symbol: "none",
      lineStyle: { color: "#0e9488", width: 1.6, type: "dotted" }, itemStyle: { color: "#0e9488" } });
  }
  const all = series.reduce((acc, sr) => acc.concat(sr.data), []);
  let lo = Math.min(...all), hi = Math.max(...all);
  const pad = Math.max(0.006, (hi - lo) * 0.3);
  S.charts.cum.setOption({
    tooltip: { trigger: "axis", valueFormatter: (v) => Number(v).toFixed(3) },
    legend: { top: 0, right: 6, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11, color: "#334155" } },
    grid: { left: 62, right: 20, top: 32, bottom: 30 },
    xAxis: {
      type: "category", boundaryGap: false,
      data: ["入学", "第1次", "第2次", "第3次", "第4次", "第5次"],
      axisLine: { lineStyle: { color: "#dbe3ee" } }, axisLabel: { color: "#6b7a90", fontSize: 11 },
    },
    yAxis: {
      type: "value", min: +(Math.max(0, lo - pad)).toFixed(3), max: +(Math.min(1, hi + pad)).toFixed(3),
      name: "能力 a", nameTextStyle: { fontSize: 10, color: "#6b7a90" },
      splitLine: { lineStyle: { color: "#eef7f7" } }, axisLabel: { color: "#6b7a90", fontSize: 11, formatter: (v) => v.toFixed(2) },
    },
    series,
  }, true);
}

function updateChartSeries(i) {
  const n = totalRounds();
  const idx = Math.min(i, n);
  S.charts.emotion.setOption({
    series: [
      { data: Array.from({ length: n }, (_, k) => (k < idx && S.epStatic.stepLog[k] ? +S.epStatic.stepLog[k].emotion.toFixed(3) : null)) },
      { data: Array.from({ length: n }, (_, k) => (k < idx && S.epDyn.stepLog[k] ? +S.epDyn.stepLog[k].emotion.toFixed(3) : null)) },
    ],
  });
  S.charts.ability.setOption({
    series: [
      { data: Array.from({ length: n }, (_, k) => (k < idx && S.epStatic.stepLog[k] ? +S.epStatic.stepLog[k].ability.toFixed(3) : null)) },
      { data: Array.from({ length: n }, (_, k) => (k < idx && S.epDyn.stepLog[k] ? +S.epDyn.stepLog[k].ability.toFixed(3) : null)) },
    ],
  });
}

/* 群体比较：同一画像下抽 60 名学生，分别跑 static / roll */
function updateSummary() {
  const proto = { conscientiousness: S.params.C, neuroticism: S.params.N, openness: S.params.O, pressure: S.params.pressure };
  const task = [S.task.start, ...S.targets];
  const rng = new RNG(20261108);
  const acc = { static: { c: 0, steps: 0, peak: 0, n: 0, sw: 0 }, roll: { c: 0, steps: 0, peak: 0, n: 0, sw: 0 } };
  for (let i = 0; i < 60; i++) {
    const a = clamp01(S.params.a + (rng.random() - 0.5) * 0.12);
    const e = clamp01(S.params.e + (rng.random() - 0.5) * 0.10);
    ["static", "roll"].forEach((st) => {
      const pl = new Replanner(S.kg);
      const lr = new Learner(proto, a, e, S.params.budget);
      const ep = runEpisode(S.kg, pl, lr, task, st, new RNG(9182 + i * 13), { replanEvery: 8, lamStab: .5 });
      acc[st].c += ep.completed ? 1 : 0;
      acc[st].steps += ep.steps;
      acc[st].peak += ep.peakEmotion;
      acc[st].sw += ep.switches;
      acc[st].n += 1;
    });
  }
  const pct = (v, n) => +(v / n * 100).toFixed(1);
  const st = acc.static, ro = acc.roll;
  S.charts.summary.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, right: 6, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { left: 62, right: 14, top: 28, bottom: 26 },
    xAxis: {
      type: "category",
      data: ["完成率 %", "平均步数", "峰值情绪 ×100"],
      axisLabel: { fontSize: 11, color: "#6b7a90" },
      axisLine: { lineStyle: { color: "#dbe3ee" } },
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { fontSize: 11, color: "#6b7a90" } },
    series: [
      {
        name: "静态", type: "bar", barWidth: 18, itemStyle: { color: "#9aa8ba", borderRadius: [4, 4, 0, 0] },
        data: [pct(st.c, st.n), +(st.steps / st.n).toFixed(1), Math.round(st.peak / st.n * 100)],
      },
      {
        name: "动态", type: "bar", barWidth: 18, itemStyle: { color: "#1f5fa8", borderRadius: [4, 4, 0, 0] },
        data: [pct(ro.c, ro.n), +(ro.steps / ro.n).toFixed(1), Math.round(ro.peak / ro.n * 100)],
      },
    ],
  }, true);
  $("#chartSummary").dataset.detail =
    JSON.stringify({ completion: [pct(st.c, st.n), pct(ro.c, ro.n)], steps: [+(st.steps / st.n).toFixed(2), +(ro.steps / ro.n).toFixed(2)] });

  // 学科任务的目标结构相近时，两轨可能给出相同结局：如实说明，并给出可操作的对照方式
  const gap = pct(ro.c, ro.n) - pct(st.c, st.n);
  const note = $("#summaryNote");
  if (note) {
    note.innerHTML = Math.abs(gap) < 0.05 && ro.sw === 0
      ? `本学科（${S.subject ? S.subject.short : "当前任务"}）的目标先修距离短、状态稳定，默认画像下两轨结局相同：`
        + `动态策略没有找到需要改道的时机。把<b>神经质</b>调到 0.75 以上或把<b>初始能力</b>降到 0.45 以下，`
        + `再回到本页即可看到改道；也可以切到<b>计算机网络</b>看完整对照。`
      : `同一批学生（n=60）：${Math.abs(gap) < 0.05 ? "<b>两轨完成率持平</b>" :
        `动态比静态的完成率高 <b>${gap.toFixed(1)}</b> pp`}，`
        + `人均步数 ${(st.steps / st.n).toFixed(1)} → ${(ro.steps / ro.n).toFixed(1)}，`
        + `平均触发重规划 ${(ro.sw / ro.n).toFixed(1)} 次。`
        + (Math.abs(gap) < 0.05
          ? "本学科上动态策略改变的是执行顺序与补救时机，不是完成率；完成率差异要看计算机网络。"
          : "这是群体平均，单次回放只用于解释机制。");
  }
}

/* ----------------------------- 知识图谱 ----------------------------- */
function renderGraphMeta() {
  const m = S.graph.meta;
  const view = viewIdSet();
  const vNodes = view.size;
  const vEdges = S.graph.edges.filter((e) => view.has(e.source) && view.has(e.target)).length;
  $("#graphMeta").innerHTML = `
    <dt>数据来源</dt><dd>${m.source}</dd>
    <dt>子图范围</dt><dd>${m.scope}</dd>
    <dt>全图规模</dt><dd>${m.nodes} 概念 / ${m.edges} 边</dd>
    <dt>当前学科</dt><dd>${S.subject ? S.subject.name : "—"}</dd>
    <dt>绘图子图</dt><dd>${vNodes} 概念 / ${vEdges} 边</dd>
    <dt>任务起点</dt><dd>${S.task.start}</dd>
    <dt>目标数</dt><dd>${S.targets.length}</dd>`;
  $("#graphNote").innerHTML =
    `<b>说明：</b>路径规划在 ${m.nodes} 个概念的全图上执行；为避免视觉拥挤，本页只绘制当前学科任务节点及其一跳邻居（${vNodes} 个概念）。` +
    "原始先修关系并非严格无环，这与第 4 章 4.1 节的说明一致。";
}

function viewIdSet() { return S.viewSet || new Set(S.graph.view); }

function depthMap() {
  const indeg = {}, depth = {};
  const nodes = S.graph.nodes.filter((n) => n.inView).map((n) => n.id);
  nodes.forEach((n) => { indeg[n] = 0; depth[n] = 0; });
  S.graph.edges.filter((e) => e.inView).forEach((e) => { indeg[e.target] = (indeg[e.target] || 0) + 1; });
  const q = nodes.filter((n) => !indeg[n]);
  const seen = new Set();
  while (q.length) {
    const u = q.shift(); seen.add(u);
    S.graph.edges.filter((e) => e.inView && e.source === u).forEach((e) => {
      depth[e.target] = Math.max(depth[e.target], depth[u] + 1);
      indeg[e.target] -= 1;
      if (indeg[e.target] === 0) q.push(e.target);
    });
  }
  nodes.forEach((n) => { if (!seen.has(n)) depth[n] = depth[n] || 1; });
  return depth;
}

function diffColor(d) {
  const t = clamp01((d - 0.25) / 0.6);
  const a = [214, 226, 240], b = [31, 95, 168];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c.join(",")})`;
}

function drawGraph(highlight) {
  const hl = highlight || new Set(S.task.path);
  const view = viewIdSet();
  const tgt = new Set(S.targets);
  const data = S.graph.nodes.filter((n) => view.has(n.id)).map((n) => {
    const isStart = n.id === S.task.start, isT = tgt.has(n.id);
    let color = diffColor(n.difficulty);
    if (isStart) color = "#1f5fa8";
    else if (isT) color = "#c47d15";
    if (hl.has(n.id) && !isStart && !isT) color = "#0e9488";
    const onPath = S.task.path.includes(n.id);
    return {
      name: n.id,
      symbolSize: 13 + Math.min(15, n.outdegree * 3.2) + (onPath ? 3 : 0),
      itemStyle: {
        color, borderColor: "#fff", borderWidth: 2,
        shadowBlur: onPath ? 10 : 4, shadowColor: "rgba(23,33,47,.18)",
      },
      label: {
        show: true, position: "right", fontSize: 11,
        color: onPath ? "#17212f" : "#4a5a6e",
        fontWeight: onPath ? 700 : 400,
      },
      value: n.difficulty, difficulty: n.difficulty,
      indegree: n.indegree, outdegree: n.outdegree, isTarget: isT,
    };
  });
  const links = S.graph.edges.filter((e) => view.has(e.source) && view.has(e.target)).map((e) => ({
    source: e.source, target: e.target,
    lineStyle: {
      color: (hl.has(e.source) && hl.has(e.target)) ? "#1f5fa8" : "#cbd5e1",
      width: (hl.has(e.source) && hl.has(e.target)) ? 2.2 : 1,
      curveness: 0.08, opacity: (hl.has(e.source) && hl.has(e.target)) ? 0.95 : 0.45,
    },
  }));
  S.charts.graph.setOption({
    tooltip: {
      formatter: (p) => p.dataType === "edge" ? `${p.data.source} → ${p.data.target}`
        : `<b>${p.name}</b><br/>结构难度 ${fmt(p.data.difficulty, 2)}<br/>出度 ${p.data.outdegree}　入度 ${p.data.indegree}${p.data.isTarget ? "<br/><span style='color:#c47d15'>本任务目标</span>" : ""}`,
    },
    series: [{
      type: "graph", layout: "force", roam: true, draggable: true,
      data, links,
      force: { repulsion: 380, edgeLength: [72, 142], gravity: 0.05, friction: 0.16, layoutAnimation: true },
      edgeSymbol: ["none", "arrow"], edgeSymbolSize: 5,
      emphasis: { focus: "adjacency", lineStyle: { width: 2.6 } },
      labelLayout: { hideOverlap: true, moveOverlap: "shiftY" },
    }],
  }, true);
  S.charts.graph.off("click");
  S.charts.graph.on("click", (p) => {
    if (p.dataType !== "node") return;
    showNode(p.name);
    drawGraph(new Set([p.name, ...S.kg.succOf(p.name), ...S.kg.predOf(p.name)]));
  });
}

function showNode(n) {
  const preds = S.kg.predOf(n), succs = S.kg.succOf(n);
  $("#nodeDetail").innerHTML = `
    <div class="grid g3">
      <div><b>${n}</b><div class="small muted">结构难度 ${fmt(S.kg.d(n), 2)}　出度 ${succs.length}　入度 ${preds.length}</div></div>
      <div><span class="pill blue">先修</span><div class="small">${preds.length ? preds.join("、") : "无（起点概念）"}</div></div>
      <div><span class="pill teal">后继</span><div class="small">${succs.length ? succs.join("、") : "无（末端概念）"}</div></div>
    </div>`;
}

/* ----------------------------- 实验证据 ----------------------------- */
function renderResults() {
  const b = S.agg.blocks;
  const d1 = b.d1_main.overall;
  const order = [
    ["static", "静态路径"], ["evolve", "双态演化"], ["roll", "演化+重规划"], ["roll_nostab", "无稳定性正则"],
  ];
  S.charts.strategies.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, right: 4, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { left: 46, right: 14, top: 30, bottom: 42 },
    xAxis: {
      type: "category", data: order.map((o) => o[1]),
      axisLabel: { fontSize: 11, color: "#6b7a90", interval: 0 },
      axisLine: { lineStyle: { color: "#dbe3ee" } },
    },
    yAxis: { type: "value", max: 100, name: "%", nameTextStyle: { fontSize: 10 }, splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { fontSize: 11, color: "#6b7a90" } },
    series: [
      { name: "完成率", type: "bar", barWidth: 22, itemStyle: { color: "#1f5fa8", borderRadius: [4, 4, 0, 0] }, data: order.map((o) => d1[o[0]].completion) },
      { name: "掌握率", type: "bar", barWidth: 22, itemStyle: { color: "#7fb3d5", borderRadius: [4, 4, 0, 0] }, data: order.map((o) => d1[o[0]].mastery) },
    ],
  }, true);

  const bud = b.d5_budget.budget;
  S.charts.budget.setOption({
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 4, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { left: 46, right: 46, top: 34, bottom: 34 },
    xAxis: { type: "category", data: bud.map((x) => x.budget + " 轮"), axisLabel: { fontSize: 11, color: "#6b7a90" }, axisLine: { lineStyle: { color: "#dbe3ee" } } },
    yAxis: [
      { type: "value", name: "完成率 %", nameTextStyle: { fontSize: 10 }, splitLine: { lineStyle: { color: "#eef2f7" } }, axisLabel: { fontSize: 11, color: "#6b7a90" } },
      { type: "value", name: "增益", nameGap: 12, splitLine: { show: false }, axisLabel: { fontSize: 10, color: "#0e9488" } },
    ],
    series: [
      { name: "静态", type: "line", symbolSize: 6, lineStyle: { color: "#9aa8ba", width: 2 }, itemStyle: { color: "#9aa8ba" }, data: bud.map((x) => x.static) },
      { name: "动态", type: "line", symbolSize: 6, lineStyle: { color: "#1f5fa8", width: 2 }, itemStyle: { color: "#1f5fa8" }, data: bud.map((x) => x.roll) },
      { name: "增益", type: "bar", yAxisIndex: 1, barWidth: 14, itemStyle: { color: "rgba(14,148,136,.55)", borderRadius: [3, 3, 0, 0] }, data: bud.map((x) => x.gain) },
    ],
  }, true);

  const grid = b.d2_heterogeneity.grid;
  const cs = [...new Set(grid.map((g) => g.conscientiousness))];
  const ns = [...new Set(grid.map((g) => g.neuroticism))];
  const hd = [];
  grid.forEach((g, i) => {
    hd.push([ns.indexOf(g.neuroticism), cs.indexOf(g.conscientiousness), g.gain]);
  });
  S.charts.hetero.setOption({
    tooltip: { formatter: (p) => `C=${cs[p.value[1]].toFixed(1)}　N=${ns[p.value[0]].toFixed(1)}<br/>增益 ${p.value[2].toFixed(2)} pp` },
    grid: { left: 58, right: 20, top: 16, bottom: 46 },
    xAxis: { type: "category", data: ns.map((x) => "N=" + x.toFixed(1)), splitArea: { show: true }, axisLabel: { fontSize: 11, color: "#6b7a90" } },
    yAxis: { type: "category", data: cs.map((x) => "C=" + x.toFixed(1)), splitArea: { show: true }, axisLabel: { fontSize: 11, color: "#6b7a90" } },
    visualMap: {
      min: -8, max: 8, calculable: true, orient: "horizontal", left: "center", bottom: 0,
      itemWidth: 11, itemHeight: 70, textStyle: { fontSize: 10, color: "#6b7a90" },
      inRange: { color: ["#c8553d", "#f2f4f8", "#1f5fa8"] },
    },
    series: [{
      type: "heatmap", data: hd,
      label: { show: true, fontSize: 11, formatter: (p) => p.value[2].toFixed(1) },
      itemStyle: { borderColor: "#fff", borderWidth: 2 },
    }],
  }, true);

  // 消融表（第一篇论文，表 3-4）
  const rows = [
    ["Baseline（Soft RAG）", 30.40, 55.42, 9.91, 4.28, ""],
    ["w/o Centrality", 0.00, 90.44, 70.42, 14.81, ""],
    ["w/o Penalty（Hard Only）", 0.00, 84.47, 83.00, 15.43, ""],
    ["Ours（Fusion）", 0.00, 100.00, 97.99, 19.92, "best"],
  ];
  $("#tbAblation").innerHTML =
    `<thead><tr><th>实验组别</th><th>幻觉率 /%</th><th>无环率 /%</th><th>有效路径率 /%</th><th>平均长度</th></tr></thead><tbody>` +
    rows.map((r) => `<tr class="${r[5]}"><td>${r[0]}</td><td class="num">${r[1].toFixed(2)}</td><td class="num">${r[2].toFixed(2)}</td><td class="num">${r[3].toFixed(2)}</td><td class="num">${r[4].toFixed(2)}</td></tr>`).join("") +
    "</tbody>";
}

function updateKPI() {
  const ov = S.agg.blocks.d1_main.overall;
  const p = S.agg.blocks.d1_main.paired || {};
  const g = p.roll_vs_static ? p.roll_vs_static.delta_completion : (ov.roll.completion - ov.static.completion);
  const drop = (ov.roll.peak_emotion - ov.static.peak_emotion) * 100;
  $("#kpi-legality").innerHTML = "100<small>%</small>";
  $("#kpi-epr").innerHTML = "97.99<small>%</small>";
  $("#kpi-gain").innerHTML = (g >= 0 ? "+" : "") + g.toFixed(1) + "<small>pp</small>";
  $("#kpi-drop").innerHTML = (drop >= 0 ? "+" : "−") + Math.abs(drop).toFixed(1) + "<small>pp</small>";
}

/* ----------------------------- 视图切换 ----------------------------- */
function switchView(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  setTimeout(() => Object.values(S.charts).forEach((c) => c && c.resize()), 60);
  window.scrollTo({ top: 0, behavior: "smooth" });
  history.replaceState(null, "", "#" + name);
  if (name === "graph") drawGraph();
  if (name === "dual") {
    const lab = $("#dualSubject");
    if (lab) lab.textContent = S.subject ? `学科：${S.subject.short}　` : "";
  }
  if (name === "results") { renderResults(); }
}

/* ----------------------------- 事件绑定 ----------------------------- */
function bindUI() {
  $$("#tabs button").forEach((b) => (b.onclick = () => switchView(b.dataset.view)));
  $("#btnPlan").onclick = () => { doPlan(); };
  $("#btnToDual").onclick = () => { switchView("dual"); resetPlayback(); };
  $("#btnPlay").onclick = () => { if (S.timer) pause(); else play(); };
  $("#btnStep").onclick = () => { pause(); if (!S.epStatic) resetPlayback(); stepOnce(); };
  $("#btnReset").onclick = () => resetPlayback();
  $$("#speed button").forEach((b) => (b.onclick = () => {
    $$("#speed button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    S.speed = Number(b.dataset.ms);
    if (S.timer) { pause(true); S.timer = setInterval(stepOnce, S.speed); }
  }));
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space" && $("#view-dual").classList.contains("active")) {
      e.preventDefault();
      if (S.timer) pause(); else play();
    }
  });
}

boot();
