# -*- coding: utf-8 -*-
"""黄帝内经专题站 huangdineijing.org 适配器（UTF-8 静态）

sitemap.xml 建 素问81 + 灵枢81 索引；正文在 <article class="markdown book-article">
内，<h1> 为篇名，<p> 为段。
"""
import re
from tcm_common import http_get, strip_tags, clean_text, normalize

SOURCE_NAME = "黄帝内经专题站(huangdineijing.org)"
SITEMAP = "https://huangdineijing.org/sitemap.xml"

_suwen_titles = [
    "上古天真论篇第一", "四气调神大论篇第二", "生气通天论篇第三",
    "金匮真言论篇第四", "阴阳应象大论篇第五", "阴阳离合论篇第六",
    "阴阳别论篇第七", "灵兰秘典论篇第八", "六节藏象论篇第九",
    "五藏生成篇第十", "五藏别论篇第十一", "异法方宜论篇第十二",
    "移精变气论篇第十三", "汤液醪醴论篇第十四", "玉版论要篇第十五",
    "诊要经终论篇第十六", "脉要精微论篇第十七", "平人气象论篇第十八",
    "玉机真藏论篇第十九", "三部九候论篇第二十", "经脉别论篇第二十一",
    "藏气法时论篇第二十二", "宣明五气篇第二十三", "血气形志篇第二十四",
    "宝命全角论篇第二十五", "八正神明论篇第二十六", "离合真邪论篇第二十七",
    "通评虚实论篇第二十八", "太阴阳明论篇第二十九", "阳明脉解篇第三十",
    "热论篇第三十一", "刺热篇第三十二", "评热病论篇第三十三",
    "逆调论篇第三十四", "疟论篇第三十五", "刺疟篇第三十六",
    "气厥论篇第三十七", "咳论篇第三十八", "举痛论篇第三十九",
    "腹中论篇第四十", "刺腰痛篇第四十一", "风论篇第四十二",
    "痹论篇第四十三", "痿论篇第四十四", "厥论篇第四十五",
    "病能论篇第四十六", "奇病论篇第四十七", "大奇论篇第四十八",
    "脉解篇第四十九", "刺要论篇第五十", "刺齐论篇第五十一",
    "刺禁论篇第五十二", "刺志论篇第五十三", "针解篇第五十四",
    "长刺节论篇第五十五", "皮部论篇第五十六", "经络论篇第五十七",
    "气穴论篇第五十八", "气府论篇第五十九", "骨空论篇第六十",
    "水热穴论篇第六十一", "调经论篇第六十二", "缪刺论篇第六十三",
    "四时刺逆从论篇第六十四", "标本病传论篇第六十五", "天元纪大论篇第六十六",
    "五运行大论篇第六十七", "六微旨大论篇第六十八", "气交变大论篇第六十九",
    "五常政大论篇第七十", "六元正纪大论篇第七十一", "刺法论篇第七十二",
    "本病论篇第七十三", "至真要大论篇第七十四", "著至教论篇第七十五",
    "示从容论篇第七十六", "疏五过论篇第七十七", "征四失论篇第七十八",
    "阴阳类论篇第七十九", "方盛衰论篇第八十", "解精微论篇第八十一",
]

_lingshu_titles = [
    "九针十二原第一", "本输第二", "小针解第三", "邪气藏府病形第四",
    "根结第五", "寿夭刚柔第六", "官针第七", "本神第八",
    "终始第九", "经脉第十", "经别第十一", "经水第十二",
    "经筋第十三", "骨度第十四", "五十营第十五", "营气第十六",
    "脉度第十七", "营卫生会第十八", "四时气第十九", "五邪第二十",
    "寒热病第二十一", "癫狂第二十二", "热病第二十三", "厥病第二十四",
    "病本第二十五", "杂病第二十六", "周痹第二十七", "口问第二十八",
    "师传第二十九", "决气第三十", "肠胃第三十一", "平人绝谷第三十二",
    "海论第三十三", "五乱第三十四", "胀论第三十五", "五癃津液别第三十六",
    "五阅五使第三十七", "逆顺肥瘦第三十八", "血络论第三十九", "阴阳清浊第四十",
    "阴阳系日月第四十一", "病传第四十二", "淫邪发梦第四十三", "顺气一日分为四时第四十四",
    "外揣第四十五", "五变第四十六", "本藏第四十七", "禁服第四十八",
    "五色第四十九", "论勇第五十", "背腧第五十一", "卫气第五十二",
    "论痛第五十三", "天年第五十四", "逆顺第五十五", "五味第五十六",
    "水胀第五十七", "贼风第五十八", "卫气失常第五十九", "玉版第六十",
    "五禁第六十一", "动输第六十二", "五味论第六十三", "阴阳二十五人第六十四",
    "五音五味第六十五", "百病始生第六十六", "行针第六十七", "上膈第六十八",
    "忧恚无言第六十九", "寒热第七十", "邪客第七十一", "通天第七十二",
    "官能第七十三", "论疾诊尺第七十四", "刺节真邪第七十五", "卫气行第七十六",
    "九宫八风第七十七", "九针论第七十八", "岁露论第七十九", "大惑论第八十",
    "痈疽第八十一",
]


def sitemap_index(refresh=False):
    """{suwen:[{title,url}], lingshu:[...]}（优先 sitemap，失败用固定篇名顺序配slug）"""
    xml, enc, fetched, err = http_get(SITEMAP, refresh=refresh)
    urls = re.findall(r"<loc>([^<]+)</loc>", xml or "")
    sw = [u for u in urls if "/docs/su_wen/" in u
          and not u.rstrip("/").split("/")[-1].endswith("-xu")]
    ls = [u for u in urls if "/docs/ling_shu/" in u
          and not u.rstrip("/").split("/")[-1].endswith("-xu")]
    if len(sw) < 81 or len(ls) < 81:
        return None, "sitemap 篇数不足（suwen=%d, lingshu=%d）" % (len(sw), len(ls))
    return {"suwen": [{"title": t, "url": u} for t, u in zip(_suwen_titles, sw)],
            "lingshu": [{"title": t, "url": u} for t, u in zip(_lingshu_titles, ls)]}, None


def fetch_pian(book, locator=None, refresh=False):
    """book: suwen/lingshu；locator 为篇名关键词。返回 list[dict] 或全文。"""
    idx, err = sitemap_index(refresh=refresh)
    if err:
        return None, err
    pages = idx[book]
    target = None
    if locator:
        q = normalize(locator.replace("篇第", "第"))
        for p in pages:
            tnorm = normalize(p["title"])
            if q in tnorm or normalize(locator) in tnorm:
                target = p
                break
        if target is None:
            return None, "未找到篇: %s" % locator
    else:
        return pages, None
    html_text, enc, fetched, err2 = http_get(target["url"], refresh=refresh)
    if err2:
        return None, err2
    m = re.search(r'(?is)<article[^>]*class="markdown book-article"[^>]*>(.*?)</article>',
                  html_text)
    frag = m.group(1) if m else html_text
    # 部分篇页在原文后附"白话参考译文/注释"，不属于典籍原文：整体截断
    cut = re.search(r"(?is)<h[12][^>]*>[^<]*(白话参考译文|白话译文|参考译文|语译)",
                    frag)
    if cut:
        frag = frag[:cut.start()]
    h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", frag)
    title = clean_text(strip_tags(h1.group(1))) if h1 else target["title"]
    paras = []
    for pm in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", frag):
        t = clean_text(strip_tags(pm.group(1)))
        if not t:
            continue
        # 站点结构标记，非原文
        if t.strip() in ("###【原文】", "【原文】", "###【译文】", "【译文】"):
            # 译文段及其后是白话翻译，不属于典籍原文，停止收集
            if "译文" in t:
                break
            continue
        if t.strip().startswith("###"):
            t = t.replace("#", "").strip()
            if not t:
                continue
        paras.append(t)
    return [{
        "volume": None, "chapter": title, "section": None, "title": title,
        "text": "\n".join(paras), "url": target["url"], "item_no": None,
    }], None
