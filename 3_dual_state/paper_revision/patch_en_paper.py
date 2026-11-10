# -*- coding: utf-8 -*-
"""改写第二篇小论文（英文稿）：加入状态演化与滚动重规划，改动处标红。

用法：
    python patch_en_paper.py 输入.docx 输出.docx [inline|append]

inline = 图表就近嵌入（02 双栏稿）；append = 表格集中放在文末（03 投稿主文）
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


def find_para(doc, startswith, style=None):
    for p in doc.paragraphs:
        if p.text.strip().startswith(startswith) and (style is None or p.style.name == style):
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


def mk_par(text, pPr, red=True, bold=None):
    el = OxmlElement("w:p")
    if pPr is not None:
        el.append(copy.deepcopy(pPr))
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    if bold:
        rPr.append(OxmlElement("w:b"))
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
    add_math(para, latex, size=9.5, color=(0xC0, 0x00, 0x00))
    r1 = para.add_run("\t(%s)" % number)
    r1.font.color.rgb = RED
    return el


def append_red(p, text):
    r = p.add_run(text)
    r.font.color.rgb = RED
    return r


def rewrite_with_red(p, parts):
    runs = p.runs
    if not runs:
        raise ValueError("no run")
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


TITLE_PARTS = [
    ("Target-preserving cognitive and affective adaptation", False),
    (" and rolling re-planning", True),
    (" of learning paths in engineering education", False),
]

ABSTRACT_ADD = (
    "Beyond local reconstruction, the learner state is extended from two scalars to four components, namely "
    "personality, ability, affect and context, with affect reverting to a personal baseline every round and "
    "ability accumulating in a saturating window. The path is therefore no longer fixed at the outset: whenever "
    "the state changes appreciably, the remaining sequence is re-solved against a cost combining failure risk, "
    "difficulty match, detour length and repeated visits, and redirection is bounded by trigger conditions, "
    "current-target protection and a stability regulariser. Across 18 tasks and 2,160 paired episodes, the "
    "re-planning strategy completes 57.82% of targets, 3.29 percentage points above an evolution-only strategy "
    "(95% interval 1.16 to 5.42) and 2.08 points above the static baseline, although the lower bound of the "
    "latter interval approaches zero. The gain grows when the budget is moderate or ability jumps, and vanishes "
    "when the budget is ample or an affective shock occurs."
)

INTRO_ADD = (
    "The four questions above concern a situation in which the path is fixed and support is temporary. In "
    "practice, personality, ability, affect and available time keep changing, so a sequence that was reasonable "
    "at the outset may no longer be appropriate a few rounds later. This study brings that layer into the same "
    "framework: the learner is described by a four-component profile, fast-changing affect and slow-changing "
    "ability are separated by two time scales, the remaining sequence is re-solved whenever the state changes "
    "appreciably, and redirection is limited by trigger conditions and a stability constraint. Section 5.7 uses "
    "a four-strategy paired comparison to answer two further questions: whether the benefit of the dynamic "
    "version comes from re-planning itself, and under which conditions it disappears."
)

S34 = [
    ("h2", "3.4 State evolution and rolling re-planning"),
    ("p", "The reconstruction in Section 3.3 selects operations on a given path; the set of targets and their order "
          "remain fixed. If the learner changes appreciably within a few rounds, for example because affect stays "
          "high or ability rises, the original sequence is no longer appropriate: harder targets should be "
          "postponed, easier ones can be advanced, and some intermediate concepts can be skipped. This section "
          "brings that decision into the same framework: the state is extended from two scalars to a "
          "four-component profile, and the path is re-solved under trigger conditions instead of being fixed once."),
    ("p", "The four components are personality, ability, affect and context. Personality is given by "
          "conscientiousness C, neuroticism N and openness O, treated as constant within a learning cycle and "
          "acting only through the modulation of evolution rates and action effectiveness. Ability a is slow, "
          "affect e is fast, and context is described by the interaction budget B and time pressure τ. Affect "
          "reverts towards a personal baseline every round:"),
    ("eq", (r"e_{t+1} = \mathrm{clip}\left(e_t + \rho(\bar{e}-e_t) + \Delta e_t\right)", "13")),
    ("p", "where Δet equals +δf on a failure, −δr after a recovery and −δp on a pass. The baseline is "
          "ē = 0.12+0.40N+0.15τ, the reversion rate is ρ = 0.08+0.12(1−N), the failure increment is "
          "δf = 0.12+0.06N, the recovery reduction is δr = 0.25 and the pass reduction is δp = 0.04. "
          "The baseline gives affect a tendency to return to the individual norm: learners low in neuroticism "
          "recover faster, whereas those high in neuroticism do not return to the low-load range even after "
          "recovery. Ability grows only when the success rate within a window exceeds one half, in a saturating "
          "form:"),
    ("eq", (r"a_{t+1} = a_t + \eta(1-a_t)\max\left(0,\ \bar{s}_t - 0.50\right)", "14")),
    ("p", "where η = 0.03+0.05C and s̄t is the success rate over the last five rounds. The saturating form makes an identical success "
          "contribute less when ability is already high, and the factor max(0,·) prevents consecutive failures "
          "from being counted as practice. The difference between the two scales is the basis of the method: "
          "affect can be changed within a few rounds, whereas ability accumulates only through sustained success, "
          "so reducing load and repairing prerequisites act on different time scales rather than being two "
          "parallel strategies."),
    ("p", "When the state makes the original plan inappropriate, re-planning computes a cost for each remaining "
          "target v:"),
    ("eq", (r"J(v) = \lambda_r R(v) + \lambda_d\left|d(v)-d^{*}\right| + \lambda_b\ell(v) "
            r"+ \lambda_v\mathbf{1}_v", "15")),
    ("p", "where R(v) is the failure probability of Section 3.3, d* = d*(at, et) = 0.30+0.45at−0.25et is the most appropriate "
          "difficulty under the current state, ℓ(v) is the number of bridge nodes required, capped at six, and the "
          "indicator 1v marks concepts already visited. The four terms represent risk avoidance, difficulty matching, detour cost and "
          "repeated visits; remaining targets are sorted by J and concatenated into a path. The sign of d* gives "
          "the same learner different orders in different states, which is what distinguishes a dynamic policy "
          "from reshuffling: the latter has no objective to optimise."),
    ("p", "Re-planning is not executed every round. Four triggers are used: the opening round, a review every "
          "eight rounds, two consecutive cognitive failures on the current target, and affect crossing 0.70. "
          "Routine triggers lock the current target and reorder only what follows; only sustained blockage allows "
          "the current target itself to be postponed. To suppress oscillation, the previous first target is "
          "retained if its cost is within 0.50 of the current optimum. The magnitude of redirection is measured "
          "by the longest common subsequence:"),
    ("eq", (r"\Delta(\pi,\pi') = 1 - \frac{\left|\mathrm{LCS}(\pi,\pi')\right|}"
            r"{\max\left(|\pi|,|\pi'|\right)}", "16")),
    ("p", "Δ = 0 means the path is unchanged and Δ = 1 means that it is entirely different; the quantity is used "
          "both to diagnose redirection frequency and to explain to the learner which part was altered. In "
          "addition, the failure probability of Section 3.3 gains a prerequisite readiness term prep(v), the "
          "proportion of the immediate predecessors of v that have been mastered. This term is the causal "
          "precondition for order to matter: without it, any ordering is probabilistically equivalent and "
          "re-planning cannot yield a gain. It also explains why bridge concepts must count as learned rather "
          "than achieved, since the former feeds readiness and the latter feeds completion. When R(v) ≤ 0.45 the "
          "bridges are skipped and the target is attempted directly, a rule called path compression; compression "
          "skips bridges but never targets and therefore does not violate target retention."),
]

S48 = [
    ("h2", "4.8 Paired experiment on rolling re-planning"),
    ("p", "The tasks used above are fixed chains whose difficulty increases monotonically. On such a task any "
          "reordering destroys the easy-to-hard structure, so a dynamic policy is indistinguishable from a static "
          "one by construction and cannot test re-planning. The dynamic experiment therefore uses a different "
          "task definition: a start concept plus six targets to be mastered, where the set is given but the order "
          "is not, drawn in three difficulty strata and with at least two targets adjacent to the start. Only "
          "here does the question of which target comes first become a decision."),
    ("p", "Four strategies are compared: static (a single planning pass followed by local repair), evolution only "
          "(two time-scale updates), evolution with re-planning, and a variant without the stability regulariser. "
          "Thirty learners per profile class, four classes and 18 tasks give 2,160 paired episodes under seed "
          "20261108. The four groups share initial profiles, tasks and random streams and differ only in whether "
          "redirection is allowed and whether the stability constraint is applied, so differences are "
          "attributable to re-planning itself. The dynamic experiment runs in a separate script (8_dynamic_path_evolution.py) that reads only the prerequisite relations and writes new outputs without overwriting those of the earlier scripts. Table 9 reports the results."),
]

S57 = [
    ("h2", "5.7 Gains and boundaries of rolling re-planning"),
    ("p", "Table 9 shows that the re-planning strategy completes 57.82% of targets, above evolution only (54.54%; "
          "difference 3.29 points, 95% interval 1.16 to 5.42) and the static baseline (55.74%; difference 2.08, "
          "interval −0.05 to 4.31). The former interval excludes zero while the lower bound of the latter is "
          "close to zero, so a gain over updating without reordering is established, but a general advantage over "
          "static planning is not. Rounds fall from 36.7 to 33.9, so the gain is not purchased with more "
          "interaction, and peak affect is essentially unchanged."),
    ("p", "The gain is conditional. Grouped by interaction budget, the differences from the static baseline at 30, "
          "40, 50 and 70 rounds are +0.78, +4.69, +7.81 and −0.78 points, an inverted U: with a tight budget "
          "there is no room to redirect, with a loose one the static sequence also finishes, and redirection pays "
          "only at intermediate budgets. The perturbation runs agree: after an affective shock the difference "
          "falls to 0.00, whereas after an ability jump it rises to +5.47, because the former removes the "
          "structure that redirection exploits and the latter makes some intermediate concepts compressible."),
    ("p", "The variant without the stability regulariser completes 56.99%, 0.83 points below the full strategy "
          "with an interval containing zero, which indicates that the constraint does not raise completion but "
          "keeps redirection within an interpretable range and reduces the waste of remediation already invested. "
          "Differences across profile classes have no consistent sign: five of nine contrasts are positive and "
          "four negative, ranging from −10.10 to +6.25 points, so which learners benefit most remains a question "
          "for real data."),
]

DISC_ADD = (
    "The dynamic evidence likewise comes from a rule-based simulator and is limited in scale. In the paired "
    "comparison over 18 tasks and four profile classes, the lower bound of the interval against the static "
    "baseline is close to zero, which does not support a claim of general superiority; rounds also have no "
    "conversion to real study time, so only relative differences are reported. Re-planning moreover depends on "
    "prerequisite readiness, and if the directions of prerequisite edges in a real graph are wrong, redirection "
    "may optimise in the wrong direction."
)

CONCL_ADD = (
    "Beyond this, the state is extended to a four-component profile and rolling re-planning is introduced, so "
    "that a path becomes an object updated with the state rather than a sequence fixed once; the paired "
    "experiment attributes the gain to re-planning itself and delineates the conditions under which it "
    "disappears."
)

TBL_ROWS = [
    ["Strategy", "Completion (%)", "Mastery (%)", "Peak affect", "Redirections"],
    ["Static", "55.74", "81.04", "0.659", "0"],
    ["Evolution only", "54.54", "79.54", "0.656", "0"],
    ["Evolution + re-planning", "57.82", "81.01", "0.650", "3.1"],
    ["Without stability", "56.99", "80.55", "0.650", "3.0"],
]
TBL_CAP = "Table 9. Paired comparison of the four strategies (18 tasks, four profile classes, 30 learners each; 2,160 episodes)"
TBL_NOTE = ("All groups share initial profiles, tasks and seed 20261108. Redirections are averaged per episode and "
            "peak affect is the maximum within an episode.")


def grab_sect(doc, num):
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


def fill_table(tb):
    while len(tb.rows) > len(TBL_ROWS):
        tb._tbl.remove(tb.rows[-1]._tr)
    for i, row in enumerate(TBL_ROWS):
        for j, val in enumerate(row):
            cell = tb.cell(i, j)
            cell.text = ""
            r = cell.paragraphs[0].add_run(val)
            r.font.color.rgb = RED
            if i == 0:
                r.font.bold = True


def main(src: Path, dst: Path, mode: str):
    doc = Document(str(src))
    p_body = ppr_of(find_para(doc, "Engineering learning paths require coordination"))
    p_h2 = ppr_of(find_style_para(doc, "Heading 2"))
    p_eq = ppr_of(find_style_para(doc, "Equation"))
    p_cap = ppr_of(find_style_para(doc, "Caption"))
    p_small = ppr_of(find_style_para(doc, "Small"))

    # 标题 / 摘要 / 关键词
    rewrite_with_red(doc.paragraphs[0], TITLE_PARTS)
    append_red(find_para(doc, "Engineering learning paths require coordination"), ABSTRACT_ADD)
    kw = find_para(doc, "Keywords:")
    rewrite_with_red(kw, [("Keywords: engineering education; cognitive and affective adaptation; learning path "
                           "reconstruction; ", False),
                          ("rolling re-planning; ", True),
                          ("learner modelling; student simulation", False)])

    # 引言
    intro = find_para(doc, "Four questions organise the study")
    intro._p.addnext(mk_par(INTRO_ADD, p_body))

    # 3.4 节：插在“4 Experimental methods”之前（3.3 之后）
    h4 = find_para(doc, "4 Experimental methods", style="Heading 1")
    for kind, payload in S34:
        if kind == "h2":
            el = mk_par(payload, p_h2)
        elif kind == "eq":
            el = mk_eq(payload[0], payload[1], p_eq, doc._body)
        else:
            el = mk_par(payload, p_body)
        h4._p.addprevious(el)

    # 4.8 + 表9
    h5 = find_para(doc, "5 Results and analysis", style="Heading 1")
    h5._p.addprevious(mk_par(S48[0][1], p_h2))
    h5._p.addprevious(mk_par(S48[1][1], p_body))
    h5._p.addprevious(mk_par(S48[2][1], p_body))

    if mode == "inline":
        h5._p.addprevious(mk_break(grab_sect(doc, "2")))
        h5._p.addprevious(mk_par(TBL_CAP, p_cap))
        tbl_el = copy.deepcopy(doc.tables[3]._tbl)
        h5._p.addprevious(tbl_el)
        fill_table(Table(tbl_el, doc._body))
        h5._p.addprevious(mk_par(TBL_NOTE, p_small))
        h5._p.addprevious(mk_break(grab_sect(doc, "1")))

    # 5.7
    h6 = find_para(doc, "6 Discussion and limitations", style="Heading 1")
    h6._p.addprevious(mk_par(S57[0][1], p_h2))
    for _, text in S57[1:]:
        h6._p.addprevious(mk_par(text, p_body))

    # 讨论补限制
    h7 = find_para(doc, "7 Conclusion", style="Heading 1")
    h7._p.addprevious(mk_par(DISC_ADD, p_body))

    # 结论补一句
    concl = find_para(doc, "This study develops target-preserving local learning-path reconstruction")
    append_red(concl, CONCL_ADD)

    # 03：表格集中放在文末
    if mode == "append":
        fig_h = find_para(doc, "Figure legends", style="Heading 1")
        tpl = next(t for t in doc.tables if len(t.columns) == 5)
        tbl_el = copy.deepcopy(tpl._tbl)
        fig_h._p.addprevious(mk_par(TBL_CAP, p_cap))
        fig_h._p.addprevious(tbl_el)
        fill_table(Table(tbl_el, doc._body))
        fig_h._p.addprevious(mk_par(TBL_NOTE, p_small))

    doc.save(str(dst))
    print("saved", dst)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "inline")
