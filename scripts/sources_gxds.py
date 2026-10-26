# -*- coding: utf-8 -*-
"""国学大师 guoxuedashi.com 适配器（UTF-8 静态页）

- 金匮要略：/a/9382x/ 单页含 25 篇全部正文，按篇标题切片
- 神农本草经：/zhongyi/305ec/ 目录（品→部类→药），每药一页
- 备急千金要方：/zhongyi/9hk/
- 太平惠民和剂局方：/zhongyi/344up/
- 伤寒论：/a/21797zbpn/（10卷，备源）
"""
import re
from tcm_common import http_get, strip_tags, clean_text, normalize

SOURCE_NAME = "国学大师(guoxuedashi.com)"

JINKUI_URL = "https://www.guoxuedashi.com/a/9382x/84764f.html"
BENCAO_INDEX = "https://www.guoxuedashi.com/zhongyi/305ec/"
QIANJIN_INDEX = "https://www.guoxuedashi.com/zhongyi/9hk/"
JUFANG_INDEX = "https://www.guoxuedashi.com/zhongyi/344up/"
SHL_INDEX = "https://www.guoxuedashi.com/a/21797zbpn/"

JINKUI_PIANS = [
    "脏腑经络先后病脉证第一", "痉湿暍病脉证第二", "百合狐惑阴阳毒病证治第三",
    "疟病脉证并治第四", "中风历节病脉证并治第五", "血痹虚劳病脉证并治第六",
    "肺痿肺痈咳嗽上气病脉证治第七", "奔豚气病脉证治第八",
    "胸痹心痛短气病脉证治第九", "腹满寒疝宿食病脉证治第十",
    "五藏风寒积聚病脉证并治第十一", "痰饮咳嗽病脉证并治第十二",
    "消渴小便不利淋病脉证并治第十三", "水气病脉证并治第十四",
    "黄疸病脉证并治第十五", "惊悸吐血下血胸满瘀血病脉证治第十六",
    "呕吐哕下利病脉证治第十七", "疮痈肠痈浸淫病脉证并治第十八",
    "趺蹶手指臂肿转筋阴狐疝蛔虫病脉证治第十九", "妇人妊娠病脉证并治第二十",
    "妇人产后病脉证治第二十一", "妇人杂病脉证并治第二十二",
    "杂疗方第二十三", "禽兽鱼虫禁忌并治第二十四", "果实菜谷禁忌并治第二十五",
]


def _infozj_text(html_text):
    m = re.search(r'id="infozj_txt"[^>]*>(.*?)(?:<div class="(?:fy|page|art_foot)|'
                  r'<div id="footer|<!-- 正文结束|id="ArtFoot)', html_text, re.S)
    if not m:
        m = re.search(r'id="infozj_txt"[^>]*>(.*?)(?:</body>|</html>)',
                      html_text, re.S)
    frag = m.group(1) if m else html_text
    frag = re.sub(r"(?is)<script.*?</script>", "", frag)
    frag = re.sub(r"(?i)<br\s*/?>", "\n", frag)
    frag = re.sub(r"(?is)</p\s*>", "\n", frag)
    txt = strip_tags(frag)
    return clean_text(txt)


def jinkui_pian(title=None, refresh=False):
    """金匮：取全篇；title 给定时返回匹配篇。返回 list[dict]。"""
    html_text, enc, fetched, err = http_get(JINKUI_URL, refresh=refresh)
    if err:
        return None, err
    txt = _infozj_text(html_text)
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    # 定位每篇标题行：以"第X"结尾的短行，按序号映射
    cn = "一二三四五六七八九十"
    ord_map = {c: i + 1 for i, c in enumerate(cn)}
    idxs = []
    title_re = re.compile(r"(第[%s]+)\s*$" % cn)
    for i, l in enumerate(lines):
        m = title_re.search(l.replace("　", "").strip())
        if not m:
            continue
        ord_str = m.group(1)[1:]
        no = 0
        for ch in ord_str:
            if ch == "十":
                no = no * 10 if no else 10
            else:
                no += ord_map[ch]
        if 1 <= no <= 25 and len(l) <= 30:
            idxs.append((i, JINKUI_PIANS[no - 1]))
    # 去重（同篇取首次）
    seen = set()
    uniq = []
    for i, p in idxs:
        if p not in seen:
            seen.add(p)
            uniq.append((i, p))
    idxs = sorted(uniq)
    segs = []
    for k, (i, p) in enumerate(idxs):
        end = idxs[k + 1][0] if k + 1 < len(idxs) else len(lines)
        body = "\n".join(lines[i + 1:end]).strip()
        # 内部条文序号（按"○"或自然段）
        item_paras = [x for x in body.split("\n") if x]
        segs.append({
            "volume": None, "chapter": p, "section": None, "title": p,
            "text": body, "url": JINKUI_URL, "item_no": None,
            "internal_paras": len(item_paras)})
    if title:
        hit = [s for s in segs if normalize(title) in normalize(s["chapter"])
               or normalize(s["chapter"]) in normalize(title)]
        if not hit:
            return None, "未找到篇: %s" % title
        return hit, None
    return segs, None


def bencaojing_index(refresh=False):
    """本经目录：返回药列表 [{pin:'上经/中经/下经', category, name, url}]。"""
    html_text, enc, fetched, err = http_get(BENCAO_INDEX, refresh=refresh)
    if err:
        return None, err
    # ul/li 嵌套；按出现顺序，记录层级最近的"品"与"部类"
    pin = None
    category = None
    items = []
    # 用扁平正则扫描所有 <li><a href=...>name</a>
    for m in re.finditer(r"<li><a href=\"([^\"]+)\"[^>]*>([^<]+)</a>", html_text):
        href, name = m.group(1), m.group(2).strip()
        if re.search(r"上经|上品", name):
            pin = "上经"
            category = None
            continue
        if re.search(r"中经|中品", name):
            pin = "中经"
            category = None
            continue
        if re.search(r"下经|下品", name):
            pin = "下经"
            category = None
            continue
        if re.search(r"(序|简介)", name):
            continue
        # 部类：玉石/草/木/人/兽/禽/虫鱼/果/米谷/菜
        if re.fullmatch(r"(玉石|草|木|人|兽|禽|虫鱼|果|米谷|菜|米)", name):
            category = name
            continue
        if pin and href.endswith(".html"):
            items.append({"pin": pin, "category": category, "name": name,
                          "url": BENCAO_INDEX + href})
    return items, None


def bencaojing_drug(name, refresh=False):
    items, err = bencaojing_index(refresh=refresh)
    if err:
        return None, err
    hit = None
    for it in items:
        if normalize(name) == normalize(it["name"]) or normalize(name) in normalize(it["name"]):
            hit = it
            break
    if not hit:
        return None, "未找到药味: %s" % name
    html_text, enc, fetched, err2 = http_get(hit["url"], refresh=refresh)
    if err2:
        return None, err2
    txt = _infozj_text(html_text)
    return [{
        "volume": hit["pin"], "chapter": ("神农本草经·%s·%s" % (hit["pin"], hit["category"])),
        "section": hit["name"], "title": hit["name"], "text": txt,
        "url": hit["url"], "item_no": None,
        "pin": hit["pin"], "category": hit["category"],
    }], None
