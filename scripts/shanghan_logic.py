# -*- coding: utf-8 -*-
"""伤寒论条文切分逻辑（不硬编码正文）。

输入 100md 篇页的段块 [(text,is_strong_title), ...]：
- is_strong 段 = 方名（如"桂枝汤方"），其后的药物组成、煎服法段均附于该方，
  整个方块附在上一条条文之后（100md 体例：方紧跟在主治条之后）。
- 连续的【问曰】【师曰】【答曰】段落合并为同一条（如第29/30条所在问答组）。
- 其余每个自然段为一条（宋本正文连排，一段即一条）。
"""
import json
import os
import re
import difflib

DRUG_LINE = re.compile(
    r"(右[一二三四五六七八九十百\d]+味|水煎服|以水[一二三四五六七八九十\d]"
    r"|煮取|去滓|温服|去沫|内诸药|微火煮)")
QA = re.compile(r"^【(问曰|师曰|答曰)】")


def _is_drug_para(txt):
    lines = [l for l in txt.split("\n") if l]
    if not lines:
        return False
    head = lines[0]
    # 组成/煎服法段，或整段含多个"右X味"等煎服语
    if DRUG_LINE.search(head):
        return True
    if len(lines) >= 2 and any(DRUG_LINE.search(l) for l in lines):
        # 长段中以"右X味/煮取"为主，排除条文（条文一般不含这些炮制词开头）
        return True
    return False


def split_clauses(blocks, start_no=None):
    """返回 [{text, kind, clause_no?}]。start_no 给定时给 clause 顺序编号。"""
    out = []
    no = start_no or 0
    in_formula = False  # 当前是否处于方名之后的组成段
    for txt, is_strong in blocks:
        if is_strong:
            out.append({"text": txt, "kind": "fang_title"})
            in_formula = True
            continue
        if in_formula:
            if _is_drug_para(txt):
                out.append({"text": txt, "kind": "fang_body"})
                continue
            in_formula = False  # 下一条条文开始
        # 普通条文
        if QA.match(txt.split("\n")[0]) and out and out[-1]["kind"] == "clause":
            prev = out[-1]["text"]
            # 同组问答延续：上一条以【问曰】/【师曰】开头但无收束，或本条是【答曰】
            if QA.match(prev.split("\n")[0]):
                out[-1]["text"] = prev + "\n" + txt
                continue
        no += 1
        item = {"text": txt, "kind": "clause"}
        if start_no is not None:
            item["clause_no"] = no
        out.append(item)

    # 合并 fang_* 到前一条 clause（保留原文，方名前加换行）
    merged = []
    for item in out:
        if item["kind"].startswith("fang") and merged and merged[-1]["kind"] == "clause":
            merged[-1]["text"] = merged[-1]["text"].rstrip() + "\n" + item["text"]
        elif item["kind"] == "clause":
            merged.append(item)
    return merged


# 第5–14篇在 100md 目录中的页文件（结构定位，不是正文）
PIAN_PAGES = [
    ("辨太阳病脉证并治法上第五", "04_03.htm"),
    ("辨太阳病脉证并治中第六", "05_01.htm"),
    ("辨太阳病脉证并治下第七", "06_01.htm"),
    ("辨阳明病脉证并治法第八", "07_01.htm"),
    ("辨少阳病脉证并治第九", "07_02.htm"),
    ("辨太阴病脉证并治第十", "08_01.htm"),
    ("辨少阴病脉证并治第十一", "08_02.htm"),
    ("辨厥阴病脉证并治第十二", "08_03.htm"),
    ("辨霍乱病脉证并治第十三", "09_01.htm"),
    ("辨阴阳易瘥后劳复病脉证并治第十四", "09_02.htm"),
]


# 煎服法/组成段特征（100md 宋本体例）
DRUG_BODY = re.compile(
    r"(右[一二三四五六七八九十百\d]+[味]?[，,]?\s*[（(]?口父[)）]?咀|"
    r"水煎服|以水[一二三四五六七八九十\d]+|煮取|去滓|温服|去[上]?沫|"
    r"内诸药|微火煮|去节|去皮|味[辛苦甘酸咸].{0,3}(温|寒|热|平)|"
    r"为末|为散|蜜和|杵为|绵裹|分温|日三服|再服|顿服|先煮)")
# 明显是新条文的开头（用于判断方剂段何时结束）
CLAUSE_START = re.compile(
    r"^(太阳病|阳明病|少阳病|太阴病|少阴病|厥阴病|伤寒|中风|热病|湿病|"
    r"病人|病者|夫|凡|若|问曰|师曰|答曰|【|发汗|吐利|霍乱|本|二阳|三阳|"
    r"脉|下之后|太阳|大病|大下|大承气|结胸|脏结|痞|淋家|疮家|汗家|"
    r"衄家|亡血|咽喉|诸|微数|形作|未持|得|本发汗|下利|自利)")


def _is_drug_body(txt):
    head = txt.split("\n")[0]
    if DRUG_BODY.search(head):
        return True
    # 药味罗列段：含多个"两/枚/个/升/铢"且无句读语气
    if len(re.findall(r"[一二三四五六七八九十半\d]+(两|铢|升|枚|个|合|斤|分)",
                      head)) >= 2 and "。" not in head[:20]:
        return True
    # 加减法段
    if head.startswith(("若", "去", "加")) and re.search(
            r"(去|加)[^，,]{1,6}(两|枚|升|合)", head):
        return True
    return False


def build_candidate_clauses(blocks):
    """把篇页段块整理成候选条文列表 [{text}]。
    方名 <strong> 段及其后的组成/煎服法/加减法段全部并入紧邻的上一条条文，
    直到遇到明显的新条文开头为止。
    """
    cands = []
    in_formula = False

    def attach(t):
        if cands:
            cands[-1]["text"] += "\n" + t
        else:
            cands.append({"text": t})

    for txt, is_strong in blocks:
        if is_strong:  # 方名
            attach(txt)
            in_formula = True
            continue
        if in_formula:
            if _is_drug_body(txt):
                attach(txt)
                continue
            # 非药物段 → 新条文
            in_formula = False
        cands.append({"text": txt})
    return cands


# 权威398基准（杏林昔拾 tcmxs，文内标注"条文数：398"，编号连续1-398）。
# 由 data/ref/tcmxs_398.json 数据驱动生成全量条首锚点，不再手写维护。
_REF_CACHE = None


def ref_398_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "ref", "tcmxs_398.json")


def load_ref_398():
    """返回 {no: 权威全文}。缺文件时抛 FileNotFoundError（构建前必须先备好基准）。"""
    global _REF_CACHE
    if _REF_CACHE is None:
        with open(ref_398_path(), encoding="utf-8") as f:
            _REF_CACHE = {int(r["no"]): r["text"] for r in json.load(f)}
    return _REF_CACHE


def anchors_for_pian(lo, hi, ref=None, prefix=18):
    """从权威基准生成 [lo,hi] 各条的条首指纹锚点。"""
    ref = ref or load_ref_398()
    from tcm_common import normalize as _norm
    return sorted((n, _norm(ref[n])[:prefix]) for n in range(lo, hi + 1))


def _head_variant_match(anchor, head):
    """单段首行的异文模糊匹配（条号仍可靠，仅版本用字不同，如 跌/趺、硬/鞕、
    而/，、以后/已后）。返回 (kind, ratio)；不匹配返回 None。
    kind='exact' 逐字前缀一致；'fuzzy' 高度相似但存在通行异文。"""
    if not head or len(head) < 6:
        return None
    if head.startswith(anchor):
        return ("exact", 1.0)
    if head[:8] == anchor[:8]:
        r = difflib.SequenceMatcher(
            None, anchor, head[:max(len(anchor), 12)]).ratio()
        if r >= 0.78:
            return ("fuzzy", r)
    k = min(14, len(head))
    r = difflib.SequenceMatcher(None, anchor[:k], head[:k]).ratio()
    if r >= 0.80:
        return ("fuzzy", r)
    r2 = difflib.SequenceMatcher(None, anchor[:10], head[:10]).ratio()
    if r2 >= 0.85:
        return ("fuzzy", r2)
    return None


def align_pian_398(cands, lo, hi, anchors_in_pian):
    """在候选段落流上，用权威398条首锚点做有序对齐（条号严格单调，杜绝错号）。

    每条锚点两阶段定位：
      1) 跨段拼接：条首可能跨在多段/方药段之间，回溯窗口14段，把[p0,p]各段首行
         有序拼接，若以锚点开头 → exact（条首逐字核实）；前8字相同再比相似度 → fuzzy。
      2) 单段异文：对单段首行做异文模糊（通行版本用字差异）→ fuzzy。
    未定位的条不进入结果（调用方据此降级 low）。

    返回:
      bounds: {no: {"start","end","verified"=exact?}}
      anchor_pos: [(no, p, p0, exact)]   exact=True 逐字 / False 异文 fuzzy
      problems: [(no, reason)]
    """
    from tcm_common import normalize as _norm
    n = len(cands)
    normed = [_norm(c["text"].split("\n")[0]) for c in cands]
    WINDOW = 14

    def locate_span(anchor, scan_from):
        # 阶段1：跨段拼接
        best_fuzzy = None
        for p in range(scan_from, n):
            hit_exact = False
            for p0 in range(max(0, p - WINDOW), p + 1):
                merged = "".join(q for q in normed[p0:p + 1] if len(q) >= 2)
                if len(merged) < 8:
                    continue
                if merged.startswith(anchor):
                    return p, p0, True
                if merged[:8] == anchor[:8]:
                    r = difflib.SequenceMatcher(
                        None, anchor,
                        merged[:max(len(anchor), 12)]).ratio()
                    if r >= 0.78 and (not best_fuzzy or r > best_fuzzy[2]):
                        best_fuzzy = (p, p0, r)
            if hit_exact:
                break
        if best_fuzzy:
            return best_fuzzy[0], best_fuzzy[1], False
        # 阶段2：单段异文模糊
        best = None
        for p in range(scan_from, n):
            m = _head_variant_match(anchor, normed[p])
            if m and (not best or m[1] > best[2]):
                best = (p, p, m[1])
        if best:
            return best[0], best[1], False
        return -1, -1, False

    anchor_pos = []
    scan = 0
    problems = []
    for no, fp in anchors_in_pian:
        p, p0, exact = locate_span(fp, scan)
        if p < 0:
            problems.append((no, "锚点未定位"))
            continue
        anchor_pos.append((no, p, p0, exact))
        scan = p + 1

    bounds = {}
    head = [(lo - 1, -1, 0, True)] if anchor_pos else []
    tail = [(hi + 1, n, n, True)] if anchor_pos else []
    seq = head + anchor_pos + tail
    p0_map = {x[0]: x[2] for x in anchor_pos}
    exact_map = {x[0]: x[3] for x in anchor_pos}
    for (na, _pa, _st, _ex), (nb, _pb, p0b, _ex2) in zip(seq, seq[1:]):
        if na >= lo and na in p0_map:
            bounds.setdefault(na, [p0_map[na], None])
            bounds[na][1] = p0b if nb <= hi + 1 else n
    out = {}
    for no, (st, en) in bounds.items():
        out[no] = {"start": st, "end": en,
                   "verified": exact_map.get(no, False)}
    return out, anchor_pos, problems


# 22 篇标准顺序（宋本赵开美系统），用于构建与对齐
PIAN_ORDER = [
    "辨脉法第一", "平脉法第二", "伤寒例第三", "辨痉湿暍脉证第四",
    "辨太阳病脉证并治法上第五", "辨太阳病脉证并治中第六",
    "辨太阳病脉证并治下第七", "辨阳明病脉证并治法第八",
    "辨少阳病脉证并治第九", "辨太阴病脉证并治第十",
    "辨少阴病脉证并治第十一", "辨厥阴病脉证并治第十二",
    "辨霍乱病脉证并治第十三", "辨阴阳易瘥后劳复病脉证并治第十四",
    "辨不可发汗病脉证并治第十五", "辨可发汗病脉证并治第十六",
    "辨发汗后病脉证并治第十七", "辨不可吐第十八", "辨可吐第十九",
    "辨不可下病脉证并治第二十", "辨可下病脉证并治第二十一",
    "辨发汗吐下后病脉证并治第二十二",
]

# 398 条编号覆盖第5–14篇。通行分布（依宋本系统）：
PIAN_398_RANGE = {
    "辨太阳病脉证并治法上第五": (1, 30),
    "辨太阳病脉证并治中第六": (31, 127),
    "辨太阳病脉证并治下第七": (128, 178),
    "辨阳明病脉证并治法第八": (179, 262),
    "辨少阳病脉证并治第九": (263, 272),
    "辨太阴病脉证并治第十": (273, 280),
    "辨少阴病脉证并治第十一": (281, 325),
    "辨厥阴病脉证并治第十二": (326, 381),
    "辨霍乱病脉证并治第十三": (382, 391),
    "辨阴阳易瘥后劳复病脉证并治第十四": (392, 398),
}

# 权威锚点（全量398，数据驱动）
# ---------------------------
# 条号 -> 条首句指纹（去标点前缀18字），来源 data/ref/tcmxs_398.json（杏林昔拾398
# 编号全文，与本地100md宋本双源对齐）。首次访问惰性加载；构建期/运行期都用同一份，
# 避免建索引与 clause 命令锚点不一致。
#
# 三态语义（对齐器保证条号严格单调，不会错号）：
#   high   条首跨段逐字命中（条号可靠、正文一致）
#   medium 有序定位且首行高度相似，仅通行版本异文（跌/趺、硬/鞕、以后/已后等），
#          条号可定、正文以本地源为准并标注"版本异文"
#   low    本地源缺失或多短条被并入他段、无法单独可靠定位 → 序号待核实，绝不猜号

_ANCHORS_CACHE = {}


def _build_anchors():
    from tcm_common import normalize as _norm
    ref = load_ref_398()
    return {n: _norm(ref[n])[:18] for n in range(1, 399)}


def get_anchors():
    global _ANCHORS_CACHE
    if not _ANCHORS_CACHE:
        _ANCHORS_CACHE = _build_anchors()
    return _ANCHORS_CACHE


class _AnchorsView(dict):
    """只读全量锚点视图：按需从权威基准惰性生成，兼容历史 `ANCHORS` 引用。"""
    def _loaded(self):
        return dict.__len__(self)

    def _ensure(self):
        if not dict.__len__(self):
            dict.update(self, get_anchors())

    def __getitem__(self, k):
        self._ensure()
        return dict.__getitem__(self, k)

    def get(self, k, d=None):
        self._ensure()
        return dict.get(self, k, d)

    def items(self):
        self._ensure()
        return dict.items(self)

    def __iter__(self):
        self._ensure()
        return dict.__iter__(self)

    def __len__(self):
        self._ensure()
        return dict.__len__(self)

    def __contains__(self, k):
        self._ensure()
        return dict.__contains__(self, k)


ANCHORS = _AnchorsView()
