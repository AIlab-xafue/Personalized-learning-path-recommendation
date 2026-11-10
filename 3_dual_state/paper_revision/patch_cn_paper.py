# -*- coding: utf-8 -*-
"""改写第二篇小论文（中文稿）：加入状态演化与滚动重规划，改动处标红。

用法：
    python patch_cn_paper.py "01_中文论文_双栏图表嵌入版.docx" 输出.docx
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

# 本脚本依赖论文排版工具 _docx_kit.py。该工具属本地私有代码，未随仓库分发。
# 使用前请把 _docx_kit.py 放到本脚本同目录，或用环境变量 DOCX_KIT_DIR 指向它所在目录。
sys.path.insert(0, os.environ.get("DOCX_KIT_DIR", str(Path(__file__).resolve().parent)))
from _docx_kit import add_math  # noqa: E402

RED = RGBColor(0xC0, 0x00, 0x00)
RED_HEX = "C00000"


# ---------------------------------------------------------------- 查找
def find_para(doc, startswith, style=None, occurrence=1):
    n = 0
    for p in doc.paragraphs:
        if p.text.strip().startswith(startswith) and (style is None or p.style.name == style):
            n += 1
            if n == occurrence:
                return p
    raise KeyError(startswith)


def find_style_para(doc, style):
    for p in doc.paragraphs:
        if p.style.name == style and p.text.strip():
            return p
    raise KeyError(style)


def ppr_of(para):
    pPr = para._p.find(qn("w:pPr"))
    return copy.deepcopy(pPr) if pPr is not None else None


# ---------------------------------------------------------------- 构造
def mk_par(text, pPr, red=True, bold=None):
    el = OxmlElement("w:p")
    if pPr is not None:
        el.append(copy.deepcopy(pPr))
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    if bold:
        b = OxmlElement("w:b")
        rPr.append(b)
    if red:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), RED_HEX)
        rPr.append(c)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    el.append(r)
    return el


def mk_eq(latex, number, pPr, parent):
    el = OxmlElement("w:p")
    el.append(copy.deepcopy(pPr))
    para = Paragraph(el, parent)
    r0 = para.add_run("\t")
    r0.font.color.rgb = RED
    add_math(para, latex, size=10.5, color=(0xC0, 0x00, 0x00))
    r1 = para.add_run("\t（%s）" % number)
    r1.font.color.rgb = RED
    return el


def append_red(p, text):
    r = p.add_run(text)
    r.font.color.rgb = RED
    return r


def rewrite_with_red(p, parts):
    runs = p.runs
    if not runs:
        raise ValueError("no run to copy format")
    rPr = runs[0]._r.find(qn("w:rPr"))
    rPr = copy.deepcopy(rPr) if rPr is not None else None
    for r in list(runs):
        r._r.getparent().remove(r._r)
    for text, is_red in parts:
        r = p.add_run(text)
        if rPr is not None:
            r._r.insert(0, copy.deepcopy(rPr))
        if is_red:
            r.font.color.rgb = RED


# ---------------------------------------------------------------- 主流程
def main(src: Path, dst: Path):
    doc = Document(str(src))

    p_body = ppr_of(find_para(doc, "设初始路径由L个互不重复概念组成"))
    p_h2 = ppr_of(find_style_para(doc, "Heading 2"))
    p_eq = ppr_of(find_para(doc, "其中c表示认知准备度")._p.getprevious() is not None and
                  doc.paragraphs[22]) if False else ppr_of(doc.paragraphs[22])
    p_cap = ppr_of(find_para(doc, "表8 选定参数条件与反例"))
    p_small = ppr_of(find_para(doc, "完成率均值；每条件十条长度10路径"))

    # 1) 标题
    t = doc.paragraphs[0]
    assert t.style.name == "Title", t.style.name
    rewrite_with_red(t, [("面向工程教育的认知与情感双态学习路径局部重构", False),
                         ("与滚动重规划", True),
                         ("方法", False)])

    # 2) 摘要
    ab = find_para(doc, "工程知识学习同时受到先修依赖")
    append_red(ab, "在局部重构之上，本文将状态由认知准备度与情感负荷两个标量扩展为性格、能力、情绪与条件"
                   "四个分量：情绪按轮向个人基线回归，能力按窗口饱和累积。路径因此不再在开始时一次确定，"
                   "而在状态显著变化时按风险、难度匹配、绕行成本与重复访问四项代价重新求解，并以触发条件、"
                   "保护当前目标与稳定性正则限制改道频率。18个任务、2160个配对回合的评估显示，含重规划的"
                   "策略完成率57.82%，比“仅演化”策略高3.29个百分点（95%区间1.16至5.42），比静态基线高"
                   "2.08个百分点但区间下界接近0；增益在预算适中与能力跃迁时放大，在预算充裕与情绪冲击时消失。")

    # 3) 关键词
    kw = find_para(doc, "关键词：")
    rewrite_with_red(kw, [("关键词：工程教育；认知与情感自适应；学习路径重构；", False),
                          ("滚动重规划；", True),
                          ("学习者建模；学习者仿真", False)])

    # 4) 引言补一段（四个研究问题之后）
    q9 = find_para(doc, "研究依次检验四个问题")
    q9._p.addnext(mk_par(
        "上述检验针对的是“路径已定、只在原目标上做临时支持”的情形。实际学习中，学习者的性格、能力、情绪与"
        "可用时间持续变化，开局合理的序列几轮之后可能不再合适。本文将这一层变化纳入同一框架：以四分量画像"
        "描述学习者，以双时间尺度区分快变的情绪与慢变的能力，在状态显著变化时对“接下来先学什么”重新求解，"
        "并以触发条件与稳定性约束限制改道频率。第5.7节用四策略配对实验回答两个新问题：动态带来的收益是否"
        "来自重规划本身，以及它在什么条件下消失。", p_body))

    # 5) 3.4 节：在表1注之后追加
    anchor = find_para(doc, "状态限制在[0,1]")
    cur = anchor

    def after(ref_el, el):
        ref_el.addnext(el)
        return el

    cur = after(cur._p, mk_par("3.4 状态演化与滚动重规划", p_h2))
    cur = after(cur, mk_par(
        "3.3节的重构在给定路径上选择操作，目标集合与先后次序保持不变。若学习者在数轮内发生明显变化，例如"
        "情绪持续偏高或能力显著提升，原序列便不再合适：较难的目标应后移，较易的目标可以提前，部分中间概念"
        "甚至可以跳过。本节把这一层决定纳入同一框架，状态由两个标量扩展为四分量画像，路径由一次确定改为在"
        "触发条件下重新求解。", p_body))
    cur = after(cur, mk_par(
        "四个分量包括性格、能力、情绪与条件。性格取尽责性C、神经质N与开放性O，在一个学习周期内视为不变，"
        "仅通过调制演化速率与动作效力间接起作用；能力a为慢变量；情绪e为快变量；条件由交互预算B与时间压力τ"
        "刻画。情绪按轮向个人基线回归：", p_body))
    cur = after(cur, mk_eq(
        r"e_{t+1} = \mathrm{clip}\left(e_t + \rho(\bar{e}-e_t) + \delta_f \mathbb{1}[\mathrm{fail}] "
        r"- \delta_r \mathbb{1}[\mathrm{rest}] - \delta_p \mathbb{1}[\mathrm{pass}]\right)",
        "13", p_eq, doc._body))
    cur = after(cur, mk_par(
        "其中基线ē=0.12+0.40N+0.15τ，回归速率ρ=0.08+0.12(1−N)，失败增量δf=0.12+0.06N，恢复降幅δr=0.25，"
        "通过降幅δp=0.04。基线使情绪具有回到个人常态的倾向：神经质低者回落更快，神经质高者即使恢复也回"
        "不到低负荷区间。能力只在窗口内成功率过半时增长，采用饱和形式：", p_body))
    cur = after(cur, mk_eq(
        r"a_{t+1} = a_t + \eta(1-a_t)\max\left(0,\ \bar{s}_t - 0.50\right),\quad \eta = 0.03 + 0.05C",
        "14", p_eq, doc._body))
    cur = after(cur, mk_par(
        "式中s̄t为最近5轮的成功率。饱和形式使同样一次成功在能力较高时增量更小，乘子max(0,·)使连续失败不产生"
        "能力增长，避免把反复失败也折算为练习量。两个尺度的差别是本节方法的立足点：情绪是几轮内可改变的快"
        "变量，能力是只能靠持续成功累积的慢变量，因此“先降负荷”与“先补基础”是作用于不同时间尺度的干预，"
        "而非两种并列策略。", p_body))
    cur = after(cur, mk_par("当状态变化使原计划不再合适时，重规划为每个剩余目标v计算代价：", p_body))
    cur = after(cur, mk_eq(
        r"J(v) = \lambda_r R(v) + \lambda_d\left|d(v)-d^{*}(a_t,e_t)\right| + \lambda_b\min(\ell(v),6) "
        r"+ \lambda_v\mathbb{1}[v\in\mathcal{V}]", "15", p_eq, doc._body))
    cur = after(cur, mk_par(
        "其中R(v)为3.3节的预计失败概率，d*=0.30+0.45at−0.25et为当前状态下最合适的难度，ℓ(v)为需经过的桥梁节点"
        "数，V为已访问集合。四项分别对应风险规避、难度匹配、绕行成本与重复访问惩罚；按J升序排列剩余目标并"
        "拼接为路径。d*的符号方向使同一名学生在不同状态下得到不同排序，这是“动态”区别于“每轮重新洗牌”的"
        "关键：后者没有最优化对象。", p_body))
    cur = after(cur, mk_par(
        "重规划并非每轮执行。触发条件有四个：开局、每八轮复核、当前目标连续两次认知失败、情绪跨越0.70。常规"
        "触发锁定当前目标，只重排其后部分；只有连续受阻才允许把当前目标整体后移。为抑制抖动，若上一轮首目标"
        "与当前最优目标的代价差小于0.50，保留原首目标。改道幅度用最长公共子序列度量：", p_body))
    cur = after(cur, mk_eq(
        r"\Delta(\pi,\pi') = 1 - \frac{\left|\mathrm{LCS}(\pi,\pi')\right|}{\max\left(|\pi|,|\pi'|\right)}",
        "16", p_eq, doc._body))
    cur = after(cur, mk_par(
        "Δ取0表示路径未变，取1表示完全不同，用于诊断改道频率并向学习者解释改动范围。此外，3.3节的失败概率"
        "增加一项先修准备度prep(v)，即v的直接前驱中已被掌握的比例。这一项是“顺序为何重要”的因果前提：没有"
        "它，任何排序在概率上等价，重规划无从产生收益。它同时说明桥梁概念必须计入“已学”而非“已达成”——前者"
        "用于计算准备度，后者用于计算完成率。当R(v)≤0.45时允许跳过桥梁直接挑战目标，称为路径压缩；压缩只"
        "跳过桥梁、不跳过目标，因此不违背目标保持原则。", p_body))

    # 6) 4.8 节
    ref5 = find_para(doc, "5 结果与分析", style="Heading 1")
    ref5._p.addprevious(mk_par("4.8 动态重规划的配对实验", p_h2))
    ref5._p.addprevious(mk_par(
        "前述实验的任务是固定链，其难度沿路径单调递增。在这种任务上，任何重排都会破坏“由易到难”的既有结构，"
        "动态与静态在构造上不可区分，因此不能用来检验重规划。动态实验改用“起点加六个待掌握目标”的任务定义："
        "目标集合给定而顺序待定，难度按低、中、高三层分层抽取，并保证至少两个目标与起点直接相邻。只有在这种"
        "任务上，“先学哪个”才真正成为一个决策。", p_body))
    ref5._p.addprevious(mk_par(
        "比较四种策略：静态（一次性规划后仅做局部修补）、仅演化（加入双时间尺度更新）、演化加重规划、去稳定性"
        "正则的变体。四类画像各30名学习者、18个任务，共2160个配对回合，固定种子20261108。四组共享初始画像、"
        "任务与随机流，唯一差别是是否允许改道以及是否施加稳定性约束，因此差值可归因于重规划本身。"
        "动态实验由独立脚本执行（8_dynamic_path_evolution.py），只读取先修关系并输出新结果，不覆盖前述脚本的"
        "既有输出。结果见表9。",
        p_body))

    # 表9：原稿的宽表都放在“单栏节”中，这里沿用同样的分节方式
    def grab_sect(num):
        for el in doc.element.body.iterchildren():
            if el.tag != qn("w:p"):
                continue
            pPr = el.find(qn("w:pPr"))
            if pPr is None:
                continue
            sp = pPr.find(qn("w:sectPr"))
            if sp is None:
                continue
            c = sp.find(qn("w:cols"))
            if c is not None and c.get(qn("w:num")) == num:
                return copy.deepcopy(sp)
        raise KeyError("sect " + num)

    def mk_break(sectPr):
        el = OxmlElement("w:p")
        pPr = OxmlElement("w:pPr")
        pPr.append(sectPr)
        el.append(pPr)
        return el

    ref5._p.addprevious(mk_break(grab_sect("2")))
    ref5._p.addprevious(mk_par("表9 四策略配对比较（18个任务、四类画像、每类30名，共2160回合）", p_cap))

    tbl_el = copy.deepcopy(doc.tables[3]._tbl)
    ref5._p.addprevious(tbl_el)
    rows = [["策略", "完成（%）", "掌握（%）", "峰值情绪", "改道次数"],
            ["静态", "55.74", "81.04", "0.659", "0"],
            ["仅演化", "54.54", "79.54", "0.656", "0"],
            ["演化加重规划", "57.82", "81.01", "0.650", "3.1"],
            ["去稳定性正则", "56.99", "80.55", "0.650", "3.0"]]
    tb = Table(tbl_el, doc._body)
    while len(tb.rows) > len(rows):
        tb._tbl.remove(tb.rows[-1]._tr)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tb.cell(i, j)
            cell.text = ""
            r = cell.paragraphs[0].add_run(val)
            r.font.color.rgb = RED
            if i == 0:
                r.font.bold = True
    ref5._p.addprevious(mk_par(
        "四组共享初始画像、任务与随机种子20261108；改道次数为每回合平均；峰值情绪取回合内最大值。", p_small))
    ref5._p.addprevious(mk_break(grab_sect("1")))

    # 7) 5.7 节
    ref6 = find_para(doc, "6 讨论与限制", style="Heading 1")
    ref6._p.addprevious(mk_par("5.7 动态重规划的增益与边界", p_h2))
    ref6._p.addprevious(mk_par(
        "表9显示，含重规划的策略完成率57.82%，高于仅演化的54.54%（差值3.29个百分点，95%区间1.16至5.42）与"
        "静态基线的55.74%（差值2.08，区间−0.05至4.31）。前者区间不含0，后者下界贴近0，因此可以确认重规划"
        "相对“只更新状态、不调整顺序”确有增益，但不足以断言它普遍优于静态规划。轮次由36.7降至33.9，说明"
        "增益并非以更多交互换取；峰值情绪基本持平。", p_body))
    ref6._p.addprevious(mk_par(
        "增益依赖条件。按交互预算分组，30、40、50、70轮时相对静态的差值分别为+0.78、+4.69、+7.81与−0.78个"
        "百分点，呈倒U形：预算过紧时没有改道余地，过松时静态序列也能走完，改道只在预算适中时产生价值。扰动"
        "实验给出同样结论：施加情绪冲击后差值降为0.00，能力跃迁后升至+5.47——前者使状态变化失去可利用的"
        "结构，后者使部分中间概念可被压缩跳过。", p_body))
    ref6._p.addprevious(mk_par(
        "去稳定性正则的变体完成率为56.99%，与完整策略相差0.83个百分点，区间含0，说明稳定性约束的作用不是"
        "提升完成率，而是把改道次数控制在可解释范围内并减少已投入补救的作废。四类画像之间的差异不具一致"
        "方向：九组画像对比中五组为正、四组为负，范围−10.10至+6.25个百分点，提示“哪类学生更受益”仍需真实"
        "数据回答。", p_body))

    # 8) 讨论补一段限制
    ref7 = find_para(doc, "7 结论", style="Heading 1")
    ref7._p.addprevious(mk_par(
        "动态部分的证据同样来自规则化模拟器，且规模有限。18个任务与四类画像的配对比较中，相对静态基线的"
        "区间下界贴近0，尚不足以支持“普遍优于静态”的断言；轮次数与真实学习时长之间没有换算关系，故只报告"
        "相对差异。此外，重规划依赖先修准备度这一项，若真实图谱的先修关系存在方向错误，改道可能沿错误方向"
        "优化，这一点在真实部署前需要教师审阅子图加以确认。", p_body))

    # 9) 结论补一句
    concl = find_para(doc, "本文以分离的认知与情感状态路由")
    append_red(concl, "在此之上，本文将状态扩展为四分量画像并引入滚动重规划，使路径由一次确定的序列变为随状态"
                      "更新的对象；配对实验确认其增益来自重规划本身，并界定了增益消失的条件。")

    doc.save(str(dst))
    print("saved", dst)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
