# -*- coding: utf-8 -*-
"""全民医药网古籍库 book.100md.com/tcm/* 适配器（GB18030 静态页）

统一结构：index.htm 目录；正文在 <!--DuYiHuaAdd BeginContent-->...EndContent 之间。
覆盖：shanghan/jinkui/bencaojing/qianjin/jufang/jingfulvke/yianan/zhuhou
     suwen/lingshu（作备源）
"""
import re
import urllib.parse
from tcm_common import (http_get, extract_begin_content, split_br_paragraphs,
                        clean_text, strip_tags, normalize)

BASE = "http://book.100md.com/tcm"
SOURCE_NAME = "全民医药网古籍库(book.100md.com)"

BOOKS = {
    "shanghan":   {"dir": "shanghanlun",             "split": "clause"},
    "jinkui":     {"dir": "jinkuiyaolvfanglun",      "split": "chapter"},
    "bencaojing": {"dir": "shennongbencaojing",      "split": "drug"},
    "qianjin":    {"dir": "beijiqianjinyaofang",     "split": "chapter"},
    "jufang":     {"dir": "taipinghuiminhejijufang", "split": "drug"},
    "jingfulvke": {"dir": "fuqingzhunvke",           "split": "drug"},
    "yianan":     {"dir": "gujinyianan",             "split": "case"},
    "zhuhou":     {"dir": "zhubingyuanhoulun",       "split": "hou"},
    "suwen":      {"dir": "huangdisuwen",            "split": "chapter"},
    "lingshu":    {"dir": "huangdilingshu",          "split": "chapter"},
}

CN_NUM = "一二三四五六七八九十百零〇两"


def index_url(book):
    return "%s/%s/index.htm" % (BASE, BOOKS[book]["dir"])


def page_url(book, href):
    return "%s/%s/%s" % (BASE, BOOKS[book]["dir"], href)


def fetch_toc(book, refresh=False):
    """返回 list: {kind:'volume'|'chapter'|'sub', text, href, volume}
    volume: 最近的卷标题；chapter: sj2 篇页；sub: sj3 子目（方/药/候/症）。
    """
    html_text, enc, fetched, err = http_get(index_url(book), refresh=refresh,
                                            force_encoding="gb18030")
    if err:
        return None, err
    items = []
    volume = None
    # 逐条扫描 sj1/sj2/sj2-mulu/sj3 段落
    pat = re.compile(
        r'<p class="(sj1|sj2-mulu|sj2|sj3)"[^>]*>'
        r'(?:<a href="([^"]+)">([^<]*)</a>)?'
        r'(?:(?!</p>).)*', re.S)
    for m in re.finditer(
            r'<p class="(sj1|sj2-mulu|sj2|sj3)"[^>]*>(.*?)</p>', html_text, re.S):
        cls, body = m.group(1), m.group(2)
        am = re.search(r'<a href="([^"]+)">([^<]+)</a>', body)
        txt = clean_text(strip_tags(body))
        if not txt:
            continue
        if cls == "sj1":
            if re.match(r"^卷[之上中下第\d%s]+" % CN_NUM, txt) or re.match(
                    r"^卷[一二三四五六七八九十百\d]+", txt):
                volume = txt
                items.append({"kind": "volume", "text": txt, "href": None,
                              "volume": volume})
            # sj1 里也有"序"等链接，忽略
        elif cls in ("sj2", "sj2-mulu"):
            if am:
                items.append({"kind": "chapter", "text": am.group(2).strip(),
                              "href": am.group(1), "volume": volume})
        elif cls == "sj3":
            if am:
                items.append({"kind": "sub", "text": am.group(2).strip(),
                              "href": am.group(1), "volume": volume})
    return items, None


def chapter_pages(book, refresh=False):
    """去重后的篇页有序列表 [{text,href,volume}]。"""
    toc, err = fetch_toc(book, refresh)
    if err:
        return None, err
    seen = set()
    pages = []
    for it in toc:
        if it["kind"] == "chapter" and it["href"] not in seen:
            seen.add(it["href"])
            pages.append(it)
    return pages, None


def sub_index(book, refresh=False):
    """子目索引（药/方/候/症）：[{title, href, chapter, volume}]，保持 TOC 顺序。"""
    toc, err = fetch_toc(book, refresh)
    if err:
        return None, err
    cur_chapter = None
    out = []
    for it in toc:
        if it["kind"] == "chapter":
            cur_chapter = it["text"]
        elif it["kind"] == "sub":
            out.append({"title": it["text"], "href": it["href"],
                        "chapter": cur_chapter, "volume": it["volume"]})
    return out, None


def fetch_page_blocks(book, href, refresh=False):
    """取篇页正文，返回段块列表 [(text,is_strong_title)]。"""
    url = page_url(book, href)
    html_text, enc, fetched, err = http_get(url, refresh=refresh,
                                            force_encoding="gb18030")
    if err:
        return None, url, err
    frag = extract_begin_content(html_text)
    if frag is None:
        return None, url, "未找到 BeginContent 正文标记"
    return split_br_paragraphs(frag), url, None


def _split_by_strong(blocks):
    """按 <strong> 小标题切段，返回 [{title, paras:[...] }]。"""
    sections = []
    cur = None
    for txt, is_strong in blocks:
        if is_strong:
            cur = {"title": txt, "paras": []}
            sections.append(cur)
        else:
            if cur is None:
                cur = {"title": None, "paras": []}
                sections.append(cur)
            cur["paras"].append(txt)
    return sections


def fetch_segments(book, href=None, chapter_title=None, refresh=False,
                   whole_page=False):
    """通用：取某书某篇页并按该书粒度切段。
    whole_page=True 时整篇作为一个片段（get 按篇定位用）。
    返回 list[dict(volume,chapter,section,title,text,url,item_no)]。
    """
    pages, err = chapter_pages(book, refresh)
    if err:
        return None, err
    target = None

    def _core(t):
        # 去掉"第X/法"等，保留辨XX病脉证并治的核心
        t = normalize(t)
        t = re.sub(r"第[%s]+$" % CN_NUM, "", t)
        t = t.replace("法", "")
        return t

    if href:
        target = next((p for p in pages if p["href"] == href), None)
    elif chapter_title:
        qn = normalize(chapter_title)
        qc = _core(chapter_title)
        for p in pages:
            pn = normalize(p["text"])
            if qn in pn or pn in qn or (qc and qc in _core(p["text"])):
                target = p
                break
    if target is None:
        return None, "未找到篇目: %s" % (href or chapter_title)

    blocks, url, err = fetch_page_blocks(book, target["href"], refresh)
    if err:
        return None, err
    mode = BOOKS[book]["split"]
    segs = []

    if mode == "chapter":
        # 整篇为一片，段以换行保留（素问/灵枢/千金/金匮）
        # 去掉页首可能的篇名重复行
        paras = [t for t, s in blocks]
        text = "\n".join(paras)
        segs.append({"volume": target["volume"], "chapter": target["text"],
                     "section": None, "title": target["text"], "text": text,
                     "url": url, "item_no": None})

    elif mode in ("drug", "hou"):
        ss = _split_by_strong(blocks)
        for i, s in enumerate(ss, 1):
            if not s["title"]:
                continue
            segs.append({"volume": target["volume"], "chapter": target["text"],
                         "section": s["title"], "title": s["title"],
                         "text": "\n".join(s["paras"]), "url": url,
                         "item_no": i if mode == "hou" else None})

    elif mode == "case":
        # 医案：页内无原生案号。按段落组案：
        # 以"XX治/XX云/一XX"等开头的段落作为新案起点，震按/又按归入前案。
        case_start = re.compile(
            r"^(丹溪|东垣|罗谦甫|虞恒德|薛立斋|汪石山|滑伯仁|张戴人|王海藏|刘宗厚|"
            r"李士材|张景岳|孙一奎|江瓘|江应宿|钱仲阳|许叔微|庞安时|戴人)")
        cur = None
        idx = 0
        for txt, is_strong in blocks:
            if is_strong:
                continue
            first = txt.split("\n")[0][:30]
            if cur is None or case_start.search(txt) or re.match(
                    r"^[一二三四五六七八九十]+[人妇男子老]|^一[人妇老翁]", txt) or re.match(
                    r"^.{2,6}治[一一-龥]{0,6}[，,。.]", txt[:12]):
                idx += 1
                cur = {"volume": target["volume"], "chapter": target["text"],
                       "section": "医案第%d案（内部序）" % idx,
                       "title": "%s·医案第%d案（内部序）" % (target["text"], idx),
                       "paras": [txt], "url": url, "item_no": idx}
                segs.append(cur)
            else:
                cur["paras"].append(txt)
        for s in segs:
            s["text"] = "\n".join(s.pop("paras"))

    elif mode == "clause":
        if whole_page:
            segs.append({"volume": target["volume"], "chapter": target["text"],
                         "section": None, "title": target["text"],
                         "text": "\n".join(t for t, _ in blocks),
                         "url": url, "item_no": None})
        else:
            from shanghan_logic import build_candidate_clauses
            for c in build_candidate_clauses(blocks):
                segs.append({"volume": target["volume"],
                             "chapter": target["text"],
                             "section": None, "title": target["text"],
                             "text": c["text"], "url": url, "item_no": None})
    return segs, None
