"""诸病源候论 备源：国学大师 guoxuedashi.com/a/22213r/（书友"安禾"整理七十卷电子本）。
该版本将原五十卷重编为七十卷，每卷一页，候标题形如「二、风癔候」，正文完整。
100md 主源个别候名/文字与该本不同（如"风癔候"100md 缺），故作为备源与补充。
"""
import re
import html as html_mod
from tcm_common import (http_get, clean_text, strip_tags, normalize,
                        now_cn)
try:
    from tcm_common import _polite as sleep_polite
except Exception:
    def sleep_polite():
        import time
        time.sleep(0.6)

BOOK_URL = "https://www.guoxuedashi.com/a/22213r/"
SOURCE_NAME = "国学大师·诸病源候论（安禾整理七十卷本）"
EDITION = "通行整理本（隋·巢元方；国学大师安禾整理七十卷电子本）"

_toc = None


def toc(refresh=False):
    """返回 [{volume, chapter, url}]，chapter 形如『风病诸候』。"""
    global _toc
    if _toc is not None and not refresh:
        return _toc, None
    html_text, _, _, err = http_get(BOOK_URL, refresh=refresh)
    if err:
        return None, err
    out = []
    for u, t in re.findall(r'href="(/a/22213r/\d+[a-z]\.html)"[^>]*>([^<]+)</a>',
                           html_text):
        t = clean_text(t)
        m = re.match(r"第(\d+)卷\s*(.+)$", t)
        if not m:
            continue
        out.append({"volume": "第%s卷" % m.group(1), "chapter": m.group(2),
                    "url": "https://www.guoxuedashi.com" + u})
    if not out:
        return None, "未解析到诸病源候论卷目"
    _toc = out
    return out, None


def _page_hou(url, refresh=False):
    """取一页，按「序号、XX候」切候。返回 [{title, text}]。"""
    html_text, _, _, err = http_get(url, refresh=refresh)
    if err:
        return None, err
    i = html_text.find("infozj_txt")
    if i < 0:
        return None, "未找到 infozj_txt 正文"
    seg = html_text[i:html_text.find("</div", i)]
    seg = re.sub(r"(?is)<script.*?</script>", "", seg)
    seg = re.sub(r"(?is)<style.*?</style>", "", seg)
    seg = re.sub(r"(?i)<br\s*/?>", "\n", seg)
    seg = strip_tags(seg)
    seg = html_mod.unescape(seg)
    lines = [re.sub(r"^[\s　]+", "", l).rstrip()
             for l in seg.split("\n")]
    lines = [l for l in lines if l.strip()]
    # 找候标题行：一、风候 / 二、风癔候
    heads = []
    for idx, l in enumerate(lines):
        if re.match(r"^[一二三四五六七八九十百〇零]+、\s*\S+候\s*$", l.strip()):
            heads.append((idx, l.strip()))
    out = []
    for k, (idx, title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = "\n".join(lines[idx + 1:end]).strip()
        out.append({"title": re.sub(r"^[一二三四五六七八九十百〇零]+、\s*",
                                    "", title),
                    "seq_title": title, "text": body})
    return out, None


def fetch_hou(locator, refresh=False):
    """按候名（如 风癔候 / 风癔）定位。返回 schema dict（不带通用外壳）或 None。"""
    want = normalize(locator.replace("候", ""))
    toc_list, err = toc(refresh)
    if err:
        return None
    first = None
    for v in toc_list:
        hous, e = _page_hou(v["url"], refresh=refresh)
        sleep_polite()
        if not hous:
            continue
        for h in hous:
            if want in normalize(h["title"]):
                return {"volume": v["volume"], "chapter": v["chapter"],
                        "section": h["title"], "title": h["seq_title"],
                        "text": h["text"], "url": v["url"],
                        "source_name": SOURCE_NAME, "edition": EDITION}
        if first is None and (want in normalize(v["chapter"])):
            first = v
    if first:
        hous, _ = _page_hou(first["url"], refresh=refresh)
        return {"volume": first["volume"], "chapter": first["chapter"],
                "section": None, "title": "第" + first["volume"] + first["chapter"],
                "text": "\n\n".join(h["seq_title"] + "\n" + h["text"]
                                    for h in (hous or [])),
                "url": first["url"], "source_name": SOURCE_NAME,
                "edition": EDITION}
    return None


def search(query, limit=8, refresh=False, max_pages=None):
    """跨卷检索，串行低频。返回段列表。"""
    kws = [k for k in re.split(r"\s+", query.strip()) if k]
    if not kws:
        return []
    toc_list, err = toc(refresh)
    if err:
        return []
    segs = []
    pages = toc_list if max_pages is None else toc_list[:max_pages]
    for v in pages:
        hous, e = _page_hou(v["url"], refresh=refresh)
        sleep_polite()
        if not hous:
            continue
        for h in hous:
            segs.append({"chapter": h["title"], "volume": v["volume"],
                         "text": h["text"], "url": v["url"],
                         "source_name": SOURCE_NAME,
                         "edition": EDITION, "title": h["seq_title"]})
    def _sc(text, toks):
        s = 0
        for t in toks:
            s += text.count(t)
        return s
    for sg in segs:
        sg["_sc"] = _sc(sg["text"], kws) + 3 * _sc(sg.get("title", ""), kws)
    hits = [sg for sg in segs if sg["_sc"] > 0]
    hits.sort(key=lambda x: x["_sc"], reverse=True)
    return hits[:limit]
