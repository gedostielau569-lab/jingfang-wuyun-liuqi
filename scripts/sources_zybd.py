# -*- coding: utf-8 -*-
"""中医宝典 zhongyibaodian.com 适配器（UTF-8 静态）

傅青主女科主源：/fuqingzhunvke5190/
目录：165-{门序号}-{?}.html，正文页锚点 <a name="m{症序}-0"></a>，
其后 <h2>症名（序号）</h2>，正文在 <div class="rd-content">。
"""
import re
from tcm_common import http_get, strip_tags, clean_text, normalize

SOURCE_NAME = "中医宝典(zhongyibaodian.com)"
TOC_URL = "http://zhongyibaodian.com/fuqingzhunvke5190/"

# 门页面（从目录动态解析）；卷归属：04_*=卷上/卷下由目录分组决定
TOC_CACHE = None


def fetch_toc(refresh=False):
    """返回 [{volume, men, page_url, anchor, zheng, order}]。"""
    global TOC_CACHE
    if TOC_CACHE and not refresh:
        return TOC_CACHE, None
    html_text, enc, fetched, err = http_get(TOC_URL, refresh=refresh)
    if err:
        return None, err
    items = []
    cur_volume = None
    cur_men = None
    # 卷标记与门链接、症锚点按出现顺序扫描
    for m in re.finditer(
            r"(卷[上下])|/fuqingzhunvke5190/(165-\d+-\d+\.html)(#(m\d+-\d+))?[^>]*>([^<]+)</a>",
            html_text):
        if m.group(1):
            cur_volume = m.group(1)
            continue
        page, anchor, label = m.group(2), m.group(4), clean_text(m.group(5))
        if anchor:  # 症
            items.append({"volume": cur_volume, "men": cur_men,
                          "page_url": "http://zhongyibaodian.com/fuqingzhunvke5190/" + page,
                          "anchor": anchor, "zheng": label})
        else:  # 门页链接（带下/血崩/调经…）
            cur_men = label
    # 目录页通常先列卷上全部再卷下；按门页 URL 中的门序号无法直接得卷，
    # 用 100md 目录顺序兜底分组：前若干门为卷上
    TOC_CACHE = items
    return items, None


def _parse_zheng_page(html_text, anchor):
    """切出某锚点到下一锚点之间的正文。"""
    i = html_text.find('name="%s"' % anchor)
    if i < 0:
        return None
    # 回退到所在标签的起点（<a name=...>），避免残留 name="..." 文本
    lt = html_text.rfind("<", 0, i)
    if lt >= 0 and i - lt < 20:
        i = lt
    j = html_text.find('name="m', i + 10)
    frag = html_text[i:j if j > 0 else len(html_text)]
    frag = re.sub(r"(?is)<script.*?</script>", "", frag)
    frag = re.sub(r"(?is)<style.*?</style>", "", frag)
    # 去掉站内症状链接标签但留文字
    frag = re.sub(r"(?is)<a [^>]*>", "", frag)
    frag = frag.replace("</a>", "")
    frag = re.sub(r"(?i)<br\s*/?>", "\n", frag)
    h2 = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", frag)
    title = clean_text(strip_tags(h2.group(1))) if h2 else anchor
    txt = clean_text(strip_tags(frag))
    # 去掉开头的锚点名残留与标题重复行
    lines = [l for l in txt.split("\n") if l.strip()]
    if lines and normalize(lines[0]) == normalize(title):
        lines = lines[1:]
    return title, "\n".join(lines).strip()


def find(locator, refresh=False):
    """按"卷上·带下"或"带下"或"白带下"定位。"""
    items, err = fetch_toc(refresh)
    if err:
        return None, err
    q = locator.replace("·", "")
    hits = []
    for it in items:
        blob = normalize((it["volume"] or "") + (it["men"] or "") + it["zheng"])
        if normalize(q) in blob:
            hits.append(it)
    if not hits:
        # 宽松：任一 token
        for tok in re.split(r"[·\s]+", locator):
            if len(tok) < 2:
                continue
            hits = [it for it in items if normalize(tok) in
                    normalize((it["men"] or "") + it["zheng"])]
            if hits:
                break
    if not hits:
        return None, "未找到定位: %s" % locator

    results = []
    seen_pages = {}
    for it in hits:
        if it["page_url"] not in seen_pages:
            html_text, enc, fetched, e = http_get(it["page_url"], refresh=refresh)
            seen_pages[it["page_url"]] = None if e else html_text
        html_text = seen_pages[it["page_url"]]
        if html_text is None:
            continue
        parsed = _parse_zheng_page(html_text, it["anchor"])
        if not parsed:
            continue
        title, text = parsed
        results.append({
            "volume": it["volume"], "chapter": "女科·%s" % (it["men"] or ""),
            "section": it["men"], "title": title, "text": text,
            "url": "%s#%s" % (it["page_url"], it["anchor"]), "item_no": None,
        })
    return results or (None, "定位到目录但正文解析失败: %s" % locator), None if results else None
