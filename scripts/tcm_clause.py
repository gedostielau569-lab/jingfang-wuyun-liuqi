#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经方临床辨证引擎 · 九部经典原文检索统一入口（只回显来源原文）

用法：
  python3 tcm_clause.py books
  python3 tcm_clause.py get  --book <id> --locator "<定位串>"
  python3 tcm_clause.py search --book <id|all> --query "<关键词>" [--limit 8]
  python3 tcm_clause.py clause --book shanghan --no 12

退出码：成功0 / 检索无结果2 / 抓取失败3 / 参数错误4
"""
import argparse
import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tcm_common
from tcm_common import (health_probe, normalize, now_cn, http_get)
import local_store
import sources_100md as s100
import sources_gxds as gxds
import sources_hdnj as hdnj
import sources_zybd as zybd
from sources_100md import _split_by_strong as _split_by_strong_pub
import sources_zhuhou_gxds as zhgx

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

LOCAL_BACKED = ("shanghan", "jinkui", "suwen", "lingshu", "bencaojing",
                "qianjin", "jufang", "jingfulvke", "yianan", "zhuhou")

BOOK_META = {
    "shanghan": {
        "title": "伤寒论",
        "edition": "通行整理本（宋·赵开美翻刻宋本398条体系）",
        "sources": [
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/shanghanlun/index.htm"},
            {"name": "国学大师 guoxuedashi.com", "probe": "https://www.guoxuedashi.com/a/21797zbpn/"},
        ]},
    "jinkui": {
        "title": "金匮要略方论",
        "edition": "通行整理本（邓珍本系统）",
        "sources": [
            {"name": "国学大师 guoxuedashi.com", "probe": gxds.JINKUI_URL},
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/jinkuiyaolvfanglun/index.htm"},
        ]},
    "suwen": {
        "title": "黄帝内经·素问",
        "edition": "通行整理本（唐·王冰注、宋·林亿校正系统）",
        "sources": [
            {"name": "黄帝内经专题站 huangdineijing.org", "probe": "https://huangdineijing.org/sitemap.xml"},
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/huangdisuwen/index.htm"},
        ]},
    "lingshu": {
        "title": "黄帝内经·灵枢",
        "edition": "通行整理本（宋·史崧校正本系统）",
        "sources": [
            {"name": "黄帝内经专题站 huangdineijing.org", "probe": "https://huangdineijing.org/sitemap.xml"},
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/huangdilingshu/index.htm"},
        ]},
    "bencaojing": {
        "title": "神农本草经",
        "edition": "通行整理本（清·孙星衍/孙冯翼辑本系统）",
        "sources": [
            {"name": "国学大师 guoxuedashi.com", "probe": gxds.BENCAO_INDEX},
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/shennongbencaojing/index.htm"},
        ]},
    "qianjin": {
        "title": "备急千金要方",
        "edition": "通行整理本（30卷本系统）",
        "sources": [
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/beijiqianjinyaofang/index.htm"},
            {"name": "国学大师 guoxuedashi.com", "probe": gxds.QIANJIN_INDEX},
        ]},
    "jufang": {
        "title": "太平惠民和剂局方",
        "edition": "通行整理本（十卷本，宋·陈师文等撰）",
        "sources": [
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/taipinghuiminhejijufang/index.htm"},
            {"name": "国学大师 guoxuedashi.com", "probe": gxds.JUFANG_INDEX},
        ]},
    "jingfulvke": {
        "title": "傅青主女科",
        "edition": "通行整理本（清·道光祁尔诚重刊本系统）",
        "sources": [
            {"name": "中医宝典 zhongyibaodian.com", "probe": zybd.TOC_URL},
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/fuqingzhunvke/index.htm"},
        ]},
    "yianan": {
        "title": "古今医案按",
        "edition": "通行整理本（清·乾隆犁春书屋刻本系统，卷内案序为内部序）",
        "sources": [
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/gujinyianan/index.htm"},
        ]},
    "zhuhou": {
        "title": "诸病源候论",
        "edition": "通行整理本（隋·巢元方等撰）",
        "sources": [
            {"name": "全民医药网 book.100md.com", "probe": "http://book.100md.com/tcm/zhubingyuanhoulun/index.htm"},
            {"name": "国学大师 guoxuedashi.com（安禾整理七十卷本，备源）",
             "probe": "https://www.guoxuedashi.com/a/22213r/"},
        ]},
}


# confidence 判定依据码（公开口径，便于使用者知道 high/medium/low 各凭什么）
#   anchor_clause  伤寒：398条首句锚点有序对齐 + 运行时指纹核验，逐字命中
#   variant_clause 伤寒：锚点可定位条号，但首句与权威基准存在通行版本异文
#   local_pian     本地冻结的权威通行整理本，按篇/卷/候/门/药/方定位原文
#   local_internal 本地原文，但采用内部段序/案序（金匮段、古今医案按），非通行权威编号
#   backup_source  主源未命中，使用备源站点
#   online_fresh   本地索引缺失/显式刷新，实时抓回的通行整理本
#   unverified     条号未通过核验或多源不一致，序号待人工复核
CONF_BASIS_CN = {
    "anchor_clause": "伤寒398条首句锚点逐字核验（高）",
    "variant_clause": "条号锚点可定位，首句存通行版本异文（中）",
    "local_pian": "本地冻结的权威通行整理本原文（高）",
    "local_internal": "本地原文，内部段序/案序非通行权威编号（中）",
    "backup_source": "主源未命中，采用备源整理本（中）",
    "online_fresh": "实时抓回的通行整理本原文，未经本地锚点核验（中）",
    "unverified": "条号未通过核验，须人工复核原文（低）",
}
# 未显式给依据码时，按 confidence 兜底
CONF_BASIS_DEFAULT = {
    "high": "local_pian",
    "medium": "online_fresh",
    "low": "unverified",
}


def _out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


def _local_source_name(book):
    """本地冻结索引对应的主源名称（用于区分命中的是主源还是备源）。"""
    return {
        "jinkui": gxds.SOURCE_NAME,
        "suwen": hdnj.SOURCE_NAME,
        "lingshu": hdnj.SOURCE_NAME,
        "bencaojing": gxds.SOURCE_NAME,
        "jingfulvke": zybd.SOURCE_NAME,
    }.get(book, s100.SOURCE_NAME)


def _envelope(book, source_name, source_url, seg=None, confidence="high",
              note=None, error=None, ok=True, basis=None):
    meta = BOOK_META.get(book)
    if seg is None:
        seg = {}
    locator_parts = [p for p in [seg.get("volume"), seg.get("chapter"),
                                 seg.get("section")] if p]
    locator = "·".join(locator_parts)
    if seg.get("item_no"):
        locator += "·第%s" % seg["item_no"]
    return {
        "ok": ok, "book": book,
        "book_title": (meta or {}).get("title"),
        "edition": (meta or {}).get("edition"),
        "volume": seg.get("volume"), "chapter": seg.get("chapter"),
        "section": seg.get("section"), "item_no": seg.get("item_no"),
        "locator": locator or None,
        "title": seg.get("title"), "text": seg.get("text"),
        "source_name": source_name if ok else None,
        "source_url": source_url if ok else None,
        "fetched_at": now_cn(),
        "confidence": confidence,
        "confidence_basis": basis or CONF_BASIS_DEFAULT.get(confidence),
        "confidence_basis_cn": CONF_BASIS_CN.get(
            basis or CONF_BASIS_DEFAULT.get(confidence)),
        "note": note, "error": error,
    }


# ---------------- 本地索引（优先路径） ----------------

def _seg_from_item(it):
    """本地索引 item -> seg（_envelope 需要的形态）。"""
    return {"volume": it.get("volume"), "chapter": it.get("chapter"),
            "section": it.get("section"), "item_no": it.get("item_no"),
            "title": it.get("title"), "text": it.get("text"),
            "url": it.get("source_url"),
            "_source_name": it.get("source_name")}


def local_get(book, locator):
    """本地索引按定位串取段，返回 (seg, source_name) 或 None。"""
    data = local_store.load(book)
    if not data:
        return None
    qn = normalize(locator)
    best = None
    best_sc = 0
    for it in data["items"]:
        fields = [it.get("title"), it.get("chapter"), it.get("section"),
                  it.get("locator")]
        sc = 0
        for f in fields:
            if not f:
                continue
            fn = normalize(f)
            if fn and fn == qn:
                sc = max(sc, 100)
            elif fn and (qn in fn or fn in qn):
                sc = max(sc, 40 + min(len(qn), len(fn)))
        if sc > best_sc:
            best_sc, best = sc, it
    if best and best_sc >= 40:
        return _seg_from_item(best), best["source_name"]
    return None


def local_search_items(book, query, limit):
    """本地索引全文检索，返回 [(score, seg, source_name)]。"""
    data = local_store.load(book)
    if not data:
        return None
    toks = _query_tokens(query)
    scored = []
    for it in data["items"]:
        seg = _seg_from_item(it)
        sc = _score(seg.get("text", ""), toks)
        sc += _score(seg.get("title") or "", toks) * 3
        if sc > 0:
            scored.append((sc, seg, it["source_name"]))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


# ---------------- 条级检索库（search 一跳取条，免去再跑 clause） ----------------

# 构建期离线落盘的条级库：book -> 文件名
_CLAUSE_ITEM_FILE = {
    "shanghan": "shanghan_clauses.json",
    "jinkui": "jinkui_clauses.json",
}
_clause_item_cache = {}


def load_clause_items(book):
    """加载构建期切好的条级库 {book,item_count,items}；不存在返回 None。

    伤寒 items: {clause, pian, text, confidence(high/medium), variant, url}
    金匮 items: {internal_no, pian, text, url}（internal_no 为内部段序，非通行条号）
    """
    if book in _clause_item_cache:
        return _clause_item_cache[book]
    fn = _CLAUSE_ITEM_FILE.get(book)
    if not fn:
        return None
    p = os.path.join(DATA_DIR, fn)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get("items"):
        return None
    _clause_item_cache[book] = d
    return d


def clause_item_search(book, query, limit):
    """在条级库上按条/段打分，返回 [(score, seg, source_name)]。

    相比篇级 local_search_items：命中粒度从"整章/整篇"细化到"单条/单段"，
    直接带定位（伤寒=398条号，金匮=篇·内部段序），一跳到位，无需再跑 clause。
    """
    d = load_clause_items(book)
    if not d:
        return None
    toks = _query_tokens(query)
    is_jinkui = d.get("item_no_kind") == "internal"
    src_name = (gxds.SOURCE_NAME if is_jinkui else s100.SOURCE_NAME)
    scored = []
    for it in d["items"]:
        text = it.get("text", "")
        sc = _score(text, toks)
        sc += _score(it.get("first_line") or "", toks) * 2
        if sc <= 0:
            continue
        if is_jinkui:
            seg = {
                "volume": None, "chapter": it["pian"], "section": None,
                "title": it["pian"], "text": text, "url": it.get("url"),
                "item_no": "内%d" % it["internal_no"],
                "_conf": "medium", "_internal": True,
                "_basis": "local_internal",
            }
        else:
            seg = {
                "volume": None, "chapter": it["pian"], "section": None,
                "title": it["pian"], "text": text, "url": it.get("url"),
                "item_no": it["clause"],
                "_conf": it.get("confidence", "high"),
                "_variant": bool(it.get("variant")),
                "_basis": "variant_clause" if it.get("variant")
                else "anchor_clause",
            }
        scored.append((sc, seg, src_name))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


# ---------------- get ----------------

def cmd_get(book, locator, refresh=False):
    if book not in BOOK_META:
        # 参数错误（未知 book id）按契约返回退出码 4
        return _envelope(book if book in ("", None) else book, None, None,
                         error="未知 book id: %s（可用：%s）"
                         % (book, "、".join(BOOK_META)), ok=False), 4

    # 本地索引优先（refresh 时跳过本地直接联网）
    if not refresh:
        local = local_get(book, locator)
        if local:
            seg, src = local
            note = None
            conf = "high"
            basis = "local_pian"
            if book == "yianan":
                note = "卷内医案无权威编号，序号为内部序"
                conf = "medium"
                basis = "local_internal"
            if book == "zhuhou" and src != s100.SOURCE_NAME:
                note = "主源100md未收录该候，使用国学大师安禾整理本"
                conf = "medium"
                basis = "backup_source"
            return _envelope(book, src, seg["url"], seg,
                             confidence=conf, note=note, basis=basis), 0

    # 内经：huangdineijing.org 主源
    if book in ("suwen", "lingshu"):
        segs, err = hdnj.fetch_pian(book, locator, refresh=refresh)
        if segs:
            return _envelope(book, hdnj.SOURCE_NAME, segs[0]["url"], segs[0],
                             confidence="medium", basis="online_fresh"), 0
        # 备源 100md（按篇页）
        segs2, err2 = s100.fetch_segments(book, chapter_title=locator, refresh=refresh)
        if segs2:
            return _envelope(book, s100.SOURCE_NAME, segs2[0]["url"], segs2[0],
                             confidence="medium", basis="backup_source",
                             note="主源未命中，使用备源 100md（%s）" % (err or "")), 0
        return _envelope(book, None, None, error=err or err2, ok=False), 3

    # 金匮：国学大师单页
    if book == "jinkui":
        segs, err = gxds.jinkui_pian(locator, refresh=refresh)
        if segs:
            return _envelope(book, gxds.SOURCE_NAME, segs[0]["url"], segs[0],
                             confidence="medium", basis="online_fresh"), 0
        segs2, err2 = s100.fetch_segments(book, chapter_title=locator, refresh=refresh)
        if segs2:
            return _envelope(book, s100.SOURCE_NAME, segs2[0]["url"], segs2[0],
                             confidence="medium", basis="backup_source",
                             note="主源未命中，使用备源100md"), 0
        return _envelope(book, None, None, error=err or err2, ok=False), 3

    # 本经：药名定位
    if book == "bencaojing":
        segs, err = gxds.bencaojing_drug(locator, refresh=refresh)
        if segs:
            return _envelope(book, gxds.SOURCE_NAME, segs[0]["url"], segs[0],
                             confidence="medium", basis="online_fresh"), 0
        # 备源 100md：子目索引
        subs, e2 = s100.sub_index(book, refresh=refresh)
        if subs:
            hit = [s for s in subs if normalize(locator) in normalize(s["title"])]
            if hit:
                seg3, e3 = _seg_from_sub(book, hit[0], refresh)
                if seg3:
                    return _envelope(book, s100.SOURCE_NAME, seg3["url"], seg3,
                                     confidence="medium", basis="backup_source",
                                     note="主源未命中，使用备源100md"), 0
        return _envelope(book, None, None, error=err, ok=False), 3

    # 女科：中医宝典
    if book == "jingfulvke":
        res = zybd.find(locator, refresh=refresh)
        if isinstance(res, tuple):
            segs, err = res
        else:
            segs, err = res, None
        if segs:
            s = segs[0]
            return _envelope(book, zybd.SOURCE_NAME, s["url"], s,
                             confidence="medium", basis="online_fresh"), 0
        segs2, err2 = _get_100md_by_locator(book, locator, refresh)
        if segs2:
            return _envelope(book, s100.SOURCE_NAME, segs2[0]["url"], segs2[0],
                             confidence="medium", basis="backup_source",
                             note="主源未命中，使用备源100md"), 0
        return _envelope(book, None, None, error=err or err2, ok=False), 3

    # 诸病源候论：100md 主源，国学大师安禾本备源（候名更全，如风癔候）
    if book == "zhuhou":
        segs, err = _get_100md_by_locator(book, locator, refresh)
        if segs:
            return _envelope(book, s100.SOURCE_NAME, segs[0]["url"], segs[0],
                             confidence="medium", basis="online_fresh"), 0
        r = zhgx.fetch_hou(locator, refresh=refresh)
        if r:
            seg = {k: v for k, v in r.items()
                   if k not in ("source_name", "url", "edition")}
            return _envelope(book, r["source_name"], r["url"], seg,
                             confidence="medium", basis="backup_source",
                             note="主源100md未命中该候，使用国学大师安禾整理本"), 0
        return _envelope(book, None, None, error=err or "主备源均未找到该候",
                         ok=False), 3

    # 其余 100md 系（伤寒/千金/局方/医案按）
    segs, err = _get_100md_by_locator(book, locator, refresh)
    if segs:
        note = None
        if book == "yianan":
            note = "卷内医案无权威编号，序号为内部序"
        return _envelope(book, s100.SOURCE_NAME, segs[0]["url"], segs[0],
                         confidence="medium" if book == "yianan" else "high",
                         note=note), 0
    return _envelope(book, None, None, error=err, ok=False), 3


def _seg_from_sub(book, sub, refresh):
    """按子目（药/方/候/症）定位，返回单个 segment。"""
    blocks, url, err = s100.fetch_page_blocks(book, sub["href"], refresh=refresh)
    if err:
        return None
    mode = s100.BOOKS[book]["split"]
    from sources_100md import _split_by_strong
    if mode in ("drug", "hou"):
        for s in _split_by_strong(blocks):
            if s["title"] and (normalize(sub["title"]) in normalize(s["title"])
                               or normalize(s["title"]) in normalize(sub["title"])):
                return {"volume": sub.get("volume"), "chapter": sub.get("chapter"),
                        "section": s["title"], "title": s["title"],
                        "text": "\n".join(s["paras"]), "url": url, "item_no": None}
    return None


def _get_100md_by_locator(book, locator, refresh, whole_page=True):
    """100md 通用定位：先子目（方/药/候/症），再篇/卷标题。"""
    mode = s100.BOOKS[book]["split"]
    loc = locator.strip()
    if mode in ("drug", "hou"):
        subs, err = s100.sub_index(book, refresh=refresh)
        if err:
            return None, err
        # 精确/包含匹配子目名；支持"卷·门·症"或"门·症"
        toks = [normalize(t) for t in re.split(r"[·\s]", loc) if t]
        best = None
        for s in subs:
            n = normalize(s["title"])
            if n in normalize(loc) or normalize(loc) in n:
                best = s
                break
        if not best:
            for s in subs:
                n = normalize(s["title"])
                if all(t and (t in n or t in normalize(s["chapter"] or "")) for t in toks):
                    best = s
                    break
        if best:
            seg = _seg_from_sub(book, best, refresh)
            if seg:
                return [seg], None
        # locator 可能是门/篇名（如"带下""治诸风"）
        segs, e = s100.fetch_segments(book, chapter_title=loc,
                                      refresh=refresh, whole_page=whole_page)
        return segs, e
    # 伤寒/千金/金匮/医案按：按篇/卷标题
    return s100.fetch_segments(book, chapter_title=loc, refresh=refresh,
                               whole_page=whole_page)


# ---------------- search ----------------

SYNONYMS = {
    "怕冷": "恶寒", "怕冷发热": "恶寒发热", "无汗": "无汗",
    "高烧": "发热", "发烧": "发热", "出汗": "汗出",
    "睡不着": "不得眠", "失眠": "不得眠",
}


def _query_tokens(query):
    q = query.strip()
    toks = [q]
    for k, v in SYNONYMS.items():
        if k in q:
            toks.append(v)
    # 多关键词拆分（2字以上）
    for sep in ["，", ",", " ", "、"]:
        if sep in q:
            toks += [t for t in q.split(sep) if len(t) >= 2]
    # 去重保序
    out = []
    for t in toks:
        t = t.strip()
        if t and normalize(t) not in [normalize(x) for x in out]:
            out.append(t)
    return out


def _score(text, toks):
    n = normalize(text)
    score = 0
    # 完整查询串（保持词序）权重最高
    full = normalize(toks[0])
    if len(full) >= 3 and full in n:
        score += 30
    # 有序邻近：把长查询按2字词窗拆，要求按序出现
    if len(full) >= 4:
        ordered = 0
        pos = -1
        for i in range(0, len(full) - 1, 2):
            pair = full[i:i + 2]
            j = n.find(pair, pos + 1)
            if j >= 0:
                ordered += 1
                pos = j
        score += ordered * 5
    hit_all = True
    for t in toks[1:] or toks:
        tn = normalize(t)
        c = n.count(tn)
        if c == 0:
            hit_all = False
        score += min(c, 5) * (4 if len(tn) >= 3 else 2)
    if hit_all and len(toks) > 1:
        score += 10
    return score


_SENT_ENDS = "。；;！!？?\n"


def _context_window(text, toks, radius=120):
    """取命中点周边文本，并把左右边界收紧/延展到最近句读，避免返回半句。"""
    ntext = text
    pos = -1
    for t in toks:
        i = ntext.find(t)
        if i >= 0:
            pos = i
            break
    if pos < 0:
        return _sent_clip(ntext[:240])
    a = max(0, pos - radius)
    b = min(len(ntext), pos + radius)
    # 左边界：从 a 向右找最近句读，从句读之后开始（不切在半句中间）
    if a > 0:
        nxt = next((k for k in range(a, min(b, a + 40))
                    if ntext[k] in _SENT_ENDS), None)
        if nxt is not None:
            a = nxt + 1
    # 右边界：从 b 向右补到最近句读，让结尾完整（最多多走 40 字）
    if b < len(ntext):
        nxt = next((k for k in range(b, min(len(ntext), b + 40))
                    if ntext[k] in _SENT_ENDS), None)
        if nxt is not None:
            b = nxt + 1
    pre = "…" if a > 0 else ""
    suf = "…" if b < len(ntext) else ""
    return pre + ntext[a:b].strip() + suf


def _sent_clip(s, limit=240):
    """无命中点时的兜底裁剪：截到 limit 内最后一个句读，保证不切半句。"""
    if len(s) <= limit:
        return s.strip()
    head = s[:limit]
    cut = max(head.rfind(c) for c in _SENT_ENDS)
    return (head[:cut + 1] if cut >= 20 else head).strip() + "…"


def _book_search(book, query, refresh):
    toks = _query_tokens(query)
    candidates = []  # (seg, source_name)

    # 本地索引优先（秒回）；--refresh 或无索引时走联网兜底
    if not refresh:
        local = local_search_items(book, query, limit=200)
        if local is not None:
            return [(sc, seg, src) for sc, seg, src in local], None

    if book in ("suwen", "lingshu"):
        pages, err = hdnj.fetch_pian(book, None, refresh=refresh)
        if pages:
            for p in pages:
                seg, e = hdnj.fetch_pian(book, p["title"], refresh=refresh)
                if seg:
                    candidates.append((seg[0], hdnj.SOURCE_NAME))
    elif book == "jinkui":
        segs, err = gxds.jinkui_pian(None, refresh=refresh)
        if segs:
            for s in segs:
                candidates.append((s, gxds.SOURCE_NAME))
    elif book == "bencaojing":
        items, err = gxds.bencaojing_index(refresh=refresh)
        if items:
            # 只在药名与已缓存药页中匹配；为控请求数，先按药名筛
            names = [it for it in items if
                     any(normalize(t) in normalize(it["name"]) for t in toks)]
            for it in names[:12]:
                seg, e = gxds.bencaojing_drug(it["name"], refresh=refresh)
                if seg:
                    candidates.append((seg[0], gxds.SOURCE_NAME))
            # 正文关键词检索走 100md 部类页（少请求）：匹配药名兜底
    elif book == "jingfulvke":
        items, err = zybd.fetch_toc(refresh=refresh)
        if items:
            # 标题先筛，减少请求
            want = [it for it in items if any(
                normalize(t) in normalize(it["zheng"]) for t in toks)]
            pages = {}
            for it in (want or [])[:14]:
                pages.setdefault(it["page_url"], []).append(it)
            for url, its in pages.items():
                html_text, enc, fetched, e = http_get(url, refresh=refresh)
                if e:
                    continue
                for it in its:
                    parsed = zybd._parse_zheng_page(html_text, it["anchor"])
                    if parsed:
                        title, text = parsed
                        candidates.append(({
                            "volume": it["volume"],
                            "chapter": "女科·%s" % (it["men"] or ""),
                            "section": it["men"], "title": title, "text": text,
                            "url": "%s#%s" % (url, it["anchor"]), "item_no": None},
                            zybd.SOURCE_NAME))
    elif book == "zhuhou":
        # 主源 100md
        mode = s100.BOOKS[book]["split"]
        pages, err = s100.chapter_pages(book, refresh=refresh)
        if pages:
            for p in pages:
                blocks, url, e = s100.fetch_page_blocks(book, p["href"], refresh=refresh)
                if e:
                    continue
                for ss in _split_by_strong_pub(blocks):
                    if not ss["title"]:
                        continue
                    candidates.append(({
                        "volume": p["volume"], "chapter": p["text"],
                        "section": ss["title"], "title": ss["title"],
                        "text": "\n".join(ss["paras"]), "url": url,
                        "item_no": None}, s100.SOURCE_NAME))
        # 备源国学大师安禾本（全文候检索，串行低频）
        for sg in zhgx.search(query, limit=12, refresh=refresh):
            candidates.append(({
                "volume": sg["volume"], "chapter": sg["chapter"],
                "section": sg["chapter"], "title": sg["title"],
                "text": sg["text"], "url": sg["url"], "item_no": None},
                sg["source_name"]))
    elif True:
        # 100md 系
        mode = s100.BOOKS[book]["split"]
        pages, err = s100.chapter_pages(book, refresh=refresh)
        if not pages:
            return None, err
        for p in pages:
            blocks, url, e = s100.fetch_page_blocks(book, p["href"], refresh=refresh)
            if e:
                continue
            if mode == "clause":
                from shanghan_logic import build_candidate_clauses
                for c in build_candidate_clauses(blocks):
                    candidates.append(({
                        "volume": p["volume"], "chapter": p["text"],
                        "section": None, "title": p["text"], "text": c["text"],
                        "url": url, "item_no": None}, s100.SOURCE_NAME))
            elif mode == "case":
                segs, _ = s100.fetch_segments(book, href=p["href"], refresh=False)
                if segs:
                    for sg in segs:
                        candidates.append((sg, s100.SOURCE_NAME))
            elif mode in ("drug", "hou"):
                from sources_100md import _split_by_strong
                for ss in _split_by_strong(blocks):
                    if not ss["title"]:
                        continue
                    candidates.append(({
                        "volume": p["volume"], "chapter": p["text"],
                        "section": ss["title"], "title": ss["title"],
                        "text": "\n".join(ss["paras"]), "url": url,
                        "item_no": None}, s100.SOURCE_NAME))
            else:  # chapter
                txt = "\n".join(t for t, _ in blocks)
                candidates.append(({
                    "volume": p["volume"], "chapter": p["text"], "section": None,
                    "title": p["text"], "text": txt, "url": url,
                    "item_no": None}, s100.SOURCE_NAME))

    # 打分排序
    scored = []
    for seg, src in candidates:
        sc = _score(seg.get("text", ""), toks)
        title_sc = _score(seg.get("title", ""), toks) * 3
        if sc + title_sc > 0:
            scored.append((sc + title_sc, seg, src))
    scored.sort(key=lambda x: -x[0])
    return scored, None


def _brief_preview(text, limit=36):
    """brief 模式的紧凑预览：去换行、截到句读，约 30–40 字。"""
    s = re.sub(r"\s+", "", text or "")
    if len(s) <= limit:
        return s
    head = s[:limit]
    cut = max(head.rfind(c) for c in "。；！？")
    return (head[:cut + 1] if cut >= 12 else head) + "…"


def cmd_search(book, query, limit, refresh=False, brief=False):
    books = list(BOOK_META.keys()) if book == "all" else [book]
    if book != "all" and book not in BOOK_META:
        _out({"ok": False, "error": "未知 book id: %s" % book}, 4)
    results = []
    errors = {}
    per_book = limit if book != "all" else 3
    # --refresh 但离线闸未放行（发布版默认纯本地）：明确告知，而不是静默空结果
    if refresh and not tcm_common.network_allowed():
        _out({
            "ok": False,
            "offline": True,
            "error": ("当前为离线模式：默认只读随技能冻结的本地索引，不发起网络请求；"
                      "去掉 --refresh 即检索本地库。仅开发者更新底本时可设环境变量 "
                      "TCM_ALLOW_NETWORK=1 并加 --refresh 联网。"),
            "results": [],
        }, 0)
    for b in books:
        try:
            scored = None
            # ① 条级库优先（不联网）：伤寒=398条号、金匮=篇·内部段序，一跳到位
            if not refresh:
                scored = clause_item_search(b, query, per_book)
            # ② 回退：篇/章本地索引（金匮段级无命中时回退到篇，保证召不漏）
            if not scored and not refresh:
                scored = local_search_items(b, query, per_book)
            # ③ 仍无：联网兜底（仅 --refresh 或本地索引缺失）
            if not scored:
                scored, err = _book_search(b, query, refresh)
                if err:
                    errors[b] = err
            if scored:
                for sc, seg, src in scored[:per_book]:
                    is_internal = seg.pop("_internal", False)
                    variant = seg.pop("_variant", False)
                    # confidence：条级库自带 _conf；篇级本地库按书定；联网兜底从严
                    conf = seg.pop("_conf", None)
                    basis = seg.pop("_basis", None)
                    if conf is None:
                        if b == "yianan" or is_internal:
                            conf, basis = "medium", "local_internal"
                        elif src != _local_source_name(b):
                            conf, basis = "medium", "backup_source"
                        else:
                            conf, basis = "high", "local_pian"
                    no = seg.get("item_no")
                    ch = seg.get("chapter") or ""
                    if is_internal:
                        locator = "%s·%s" % (ch, no) if no else (ch or b)
                    elif no:
                        locator = "%s·第%s条" % (ch, no)
                    else:
                        locator = ch or b
                    if brief:
                        # 极简定位卡：只给"去哪取 + 短预览"，命中后再用 clause/get 取全文
                        env = {
                            "book": b, "item_no": no, "locator": locator,
                            "confidence": conf,
                            "confidence_basis": basis,
                            "preview": _brief_preview(seg.get("text", "")),
                        }
                        if is_internal:
                            env["item_no_kind"] = "internal"
                    else:
                        env = _envelope(b, src, seg.get("url"), seg,
                                        confidence=conf, basis=basis)
                        env["locator"] = locator or env.get("locator")
                        if is_internal:
                            env["item_no_kind"] = "internal"
                            env["note"] = "内部段序/案序（非通行权威条号），按篇目定位"
                        if variant:
                            env["variant"] = True
                            env["note"] = ("有序定位、条号可定；首句与权威基准存在"
                                           "通行版本异文，引用时建议核对原文")
                        env["text"] = _context_window(
                            seg["text"], _query_tokens(query))
                    env["_score"] = sc
                    results.append((sc, env))
        except Exception as e:
            errors[b] = "检索异常: %s" % e
    results.sort(key=lambda x: -x[0])
    results = [r[1] for r in results[:limit]]
    for r in results:
        r.pop("_score", None)
    if not results:
        return {"ok": True, "book": book, "results": [],
                "note": "未检索到含该关键词的原文片段", "errors": errors or None}, 2
    return {"ok": True, "book": book, "brief": bool(brief),
            "results": results, "errors": errors or None}, 0


# ---------------- clause（伤寒398本地索引） ----------------

def _load_shanghan_pages(refresh=False):
    """返回 (pages_dict: href->[(text,is_strong)], urls: href->url)。
    优先本地 shanghan_pages.json（build_index 落盘），缺失才走缓存/联网。
    """
    from shanghan_logic import PIAN_PAGES as _PP
    p = os.path.join(DATA_DIR, "shanghan_pages.json")
    if not refresh and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return ({h: [(t, bool(s)) for t, s in blocks]
                 for h, blocks in d["blocks"].items()}, d["urls"])
    pages, urls = {}, {}
    for pian, hp in _PP:
        blocks, url, err = s100.fetch_page_blocks("shanghan", hp,
                                                  refresh=refresh)
        if err:
            continue
        pages[hp] = blocks
        urls[hp] = url
    return pages, urls


def cmd_clause(no, refresh=False):
    from shanghan_logic import (build_candidate_clauses, align_pian_398,
                                anchors_for_pian,
                                PIAN_PAGES as _PP, PIAN_398_RANGE, ANCHORS)
    idx_path = os.path.join(DATA_DIR, "shanghan_398.json")
    if not os.path.exists(idx_path):
        _out({"ok": False, "book": "shanghan",
              "error": "本地伤寒398条索引不存在，请先运行 build_index.py"}, 3)
    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)
    rec = next((r for r in idx if r["clause"] == no), None)
    if not rec:
        _out({"ok": False, "book": "shanghan",
              "error": "索引中无第%d条（398条范围1-398）" % no}, 2)
    pian, href = rec["pian"], rec["href"]

    pages, urls = _load_shanghan_pages(refresh=refresh)
    blocks = pages.get(href)
    url = urls.get(href) or s100.page_url("shanghan", href)
    if blocks is None:
        blocks, url, err = s100.fetch_page_blocks("shanghan", href,
                                                  refresh=refresh)
        if err:
            _out({"ok": False, "book": "shanghan", "error": err}, 3)

    cands = build_candidate_clauses(blocks)
    lo, hi = PIAN_398_RANGE[pian]
    anchors = anchors_for_pian(lo, hi)
    bounds, anchor_pos, _ = align_pian_398(cands, lo, hi, anchors)
    exact_nos = {n for n, _p, _p0, ex in anchor_pos if ex}
    fuzzy_nos = {n for n, _p, _p0, ex in anchor_pos if not ex}
    is_high = no in exact_nos
    is_medium = no in fuzzy_nos

    seg_text = None
    if no in bounds:
        st, en = bounds[no]["start"], bounds[no]["end"]
        seg_text = "\n".join(c["text"] for c in cands[st:en]).strip()

    # high 运行时指纹动态校验：索引 first_line 必须在当前抓回正文里出现，
    # 防止本地文本变动造成的假高置信；不一致则降级（不直接给条号）。
    if is_high and rec.get("first_line"):
        got_fp = None
        if no in bounds:
            got_fp = normalize(seg_text.split("\n")[0]) if seg_text else None
        fp = normalize(rec["first_line"])
        if not got_fp or (fp[:12] not in got_fp and got_fp[:12] not in fp):
            is_high, is_medium = False, False  # 指纹不一致 → 严格降为 low

    import re as _re

    def _is_clause_head(s):
        h = s.strip()
        if not h:
            return False
        if _re.match(r"^(若|加减法|后加减法|去[^，]{1,8}[，,]加|疑非仲景|疑非)", h):
            return False
        return True

    # high：条号可靠、正文逐字核实
    if is_high:
        seg = {"volume": None, "chapter": pian, "section": None, "title": pian,
               "text": seg_text, "url": url, "item_no": no}
        return _envelope("shanghan", s100.SOURCE_NAME, url, seg,
                         confidence="high", note=None,
                         basis="anchor_clause"), 0

    # medium：有序对齐、条号可定，仅通行版本异文（跌/趺、硬/鞕、以后/已后…）
    if is_medium and seg_text:
        seg = {"volume": None, "chapter": pian, "section": None, "title": pian,
               "text": seg_text, "url": url, "item_no": no}
        note = ("有序定位、条号可定；首句与权威基准存在通行版本异文，"
                "正文以本地宋本为准，引用时建议核对原文")
        env = _envelope("shanghan", s100.SOURCE_NAME, url, seg,
                        confidence="medium", note=note,
                        basis="variant_clause")
        env["item_no"] = no
        env["variant"] = True
        return env, 0

    # low：本地源缺失或多短条被并入他段，无法单独可靠定位 → 序号待核实，不猜号
    cands_out = []
    below = [p for p in anchor_pos if p[0] < no]
    above = [p for p in anchor_pos if p[0] > no]
    a = below[-1][1] + 1 if below else 0
    b = above[0][1] if above else len(cands)
    for c in cands[a:b]:
        head = c["text"].split("\n")[0][:60]
        if _is_clause_head(head):
            cands_out.append(head)
    # 权威基准该条首句（仅作核对线索，非本地原文，不可直接引用为本地源正文）
    ref_head = None
    try:
        from shanghan_logic import load_ref_398
        ref_head = load_ref_398().get(no, "")[:60]
    except Exception:
        pass
    seg = {"volume": None, "chapter": pian, "section": None,
           "title": pian, "text": None, "url": url, "item_no": None}
    note = ("条文序号待核实：本地源该条缺失或多条被并入同段，未能单独可靠定位；"
            "已给同篇相邻候选首句，引用前须核对原文，不臆测条号")
    env = _envelope("shanghan", s100.SOURCE_NAME, url, seg,
                    confidence="low", note=note, basis="unverified")
    env["item_no"] = None
    env["candidate_clause_no"] = no
    env["candidates"] = cands_out[:6] or None
    if ref_head:
        env["ref_first_line"] = ref_head
        env["ref_source"] = "杏林昔拾 tcmxs 398编号全文（核对线索，非本地宋本正文）"
    return env, 0


# ---------------- books ----------------

def cmd_books(refresh=False):
    """默认离线：报告随技能冻结的本地索引完整性；不探测任何源站。
    仅 --refresh 且 TCM_ALLOW_NETWORK=1（开发者更新底本）时才探测源站可达性。
    """
    online = bool(refresh) and tcm_common.network_allowed()
    report = local_store.local_index_report()
    built_map = {b: v.get("built_at") for b, v in report["books"].items()}
    count_map = {b: v.get("item_count") for b, v in report["books"].items()}

    out = []
    for bid, meta in BOOK_META.items():
        entry = {
            "book": bid, "title": meta["title"], "edition": meta["edition"],
            "local_index": {
                "present": report["books"].get(bid, {}).get("present", False),
                "item_count": count_map.get(bid, 0),
                "built_at": built_map.get(bid),
            },
        }
        if bid in report["clause_index"]:
            entry["clause_index"] = report["clause_index"][bid]
        if online:
            srcs = []
            for s in meta["sources"]:
                healthy, latency = health_probe(s["probe"])
                srcs.append({"name": s["name"], "healthy": healthy,
                             "latency_ms": latency})
            entry["sources"] = srcs
        out.append(entry)
    return {
        "ok": report["ok"],
        "mode": "online" if online else "offline",
        "note": ("纯本地模式：检索只读随技能冻结的索引，不发起网络请求；"
                 "源站可达性仅开发者 --refresh 时检测") if not online else None,
        "books": out,
        "fetched_at": now_cn(),
    }, 0


def main():
    ap = argparse.ArgumentParser(description="九部中医经典原文检索")
    sub = ap.add_subparsers(dest="cmd")
    bp = sub.add_parser("books")
    bp.add_argument("--refresh", action="store_true")
    g = sub.add_parser("get")
    g.add_argument("--book", required=True)
    g.add_argument("--locator", required=True)
    g.add_argument("--refresh", action="store_true")
    s = sub.add_parser("search")
    s.add_argument("--book", required=True)
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--brief", action="store_true",
                   help="精简模式：只回定位/条号/可信度+短预览，命中后用 clause/get 取全文，省 token")
    s.add_argument("--refresh", action="store_true")
    c = sub.add_parser("clause")
    c.add_argument("--book", default="shanghan")
    c.add_argument("--no", type=int, required=True)
    c.add_argument("--refresh", action="store_true")

    try:
        args = ap.parse_args()
    except SystemExit as e:
        # argparse 参数错误默认退出码 2，契约统一为 4
        code = e.code if isinstance(e.code, int) else 2
        sys.exit(4 if code == 2 else code)
    if not args.cmd:
        ap.print_help()
        sys.exit(4)
    try:
        if args.cmd == "books":
            obj, code = cmd_books(args.refresh)
        elif args.cmd == "get":
            obj, code = cmd_get(args.book, args.locator, args.refresh)
        elif args.cmd == "search":
            obj, code = cmd_search(args.book, args.query, args.limit,
                                   args.refresh, args.brief)
        elif args.cmd == "clause":
            if args.book != "shanghan":
                _out({"ok": False, "error": "clause 目前仅支持 shanghan"}, 4)
            obj, code = cmd_clause(args.no, args.refresh)
        else:
            obj, code = {"ok": False, "error": "unknown"}, 4
    except SystemExit:
        raise
    except Exception as e:
        obj, code = {"ok": False, "error": "内部错误: %s" % e}, 3
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.exit(code)


if __name__ == "__main__":
    main()
