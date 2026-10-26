#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yunqi_pathomech.py —— 第三层：岁运病机离线库 + 结构化推理链

只做一件事：把"岁运五行 × 太过/不及"映射到**随技能冻结的《素问·五运行大论》
本地原文**所支撑的经典病机结构，供辨证流程在第④节五运六气参考中直接引用，
不临场背运气条文、不凭记忆编造。

边界（与 SKILL.md 一致）：
  - 本库仅覆盖岁运（五运太过/不及）10 格；六气司天在泉病候、病机十九条、运气
    治则因本地《素问》节选不全，未入本库，仍须 search 回《素问》原文接地。
  - 输出是"气化背景/易感倾向"，不是诊断、不处方、不定剂量；与四诊冲突时从四诊。
  - 每条 binghou/quote/locator 均来自 data/yunqi_pathomech.json（逐字核于本地原文）。
"""
import json
import os

_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "yunqi_pathomech.json")

_CACHE = None

# 岁运太过/不及 → 库 key 后缀
_KEY = {("木", "太过"): "wood_excess", ("木", "不及"): "wood_deficient",
        ("火", "太过"): "fire_excess", ("火", "不及"): "fire_deficient",
        ("土", "太过"): "earth_excess", ("土", "不及"): "earth_deficient",
        ("金", "太过"): "metal_excess", ("金", "不及"): "metal_deficient",
        ("水", "太过"): "water_excess", ("水", "不及"): "water_deficient"}

# 五行相克（用于解释受邪关系的客观标签，不新增医学结论）
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_ZANG = {"木": "肝", "火": "心", "土": "脾", "金": "肺", "水": "肾"}
_FU = {"木": "胆", "火": "小肠", "土": "胃", "金": "大肠", "水": "膀胱"}


def load_library():
    """加载并缓存病机库。文件缺失时返回 None（调用方降级为纯检索接地）。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    except (OSError, ValueError):
        _CACHE = None
    return _CACHE


def library_report():
    """供 books/自检：本地病机库的存在性与覆盖。"""
    lib = load_library()
    if not lib:
        return {"present": False, "item_count": 0, "file": "data/yunqi_pathomech.json"}
    return {"present": True, "item_count": len(lib.get("items", [])),
            "source_chapter": lib.get("source_chapter"),
            "file": "data/yunqi_pathomech.json"}


def _extract_sitian_tokens(shanglin_text):
    """从上临原文（如'上临少阴、少阳（子午、寅申司天）'）提取六气名，用于与实际司天比对。"""
    tokens = ["厥阴", "少阴", "太阴", "少阳", "阳明", "太阳"]
    # 优先取括号前的六气名（司天以六气言）
    head = shanglin_text.split("（")[0].split("(")[0]
    found = [t for t in tokens if t in head]
    return found or [t for t in tokens if t in shanglin_text]


def _infer_chain(item, shanglin_active=False):
    """根据该格的客观字段，组装一条结构化推理链；只转述原文关系，不新增结论。"""
    wx = item["yun_wx"]
    status = item["status"]
    if status == "太过":
        mechanism = ("岁运%s%s，%s；本气偏胜，乘其所胜之%s（%s受邪）"
                     % (wx, status, item["liuxing_qi"], _KE[wx], item["affected_zang"]))
        susceptible = ["%s（本气偏胜之脏）" % _ZANG[wx],
                       "%s（被乘受邪之脏）" % _ZANG[_KE[wx]]]
    else:
        cheng = {"木": "金", "火": "水", "土": "木", "金": "火", "水": "土"}[wx]
        mechanism = ("岁运%s%s，%s；本气不足，为其所不胜之%s气所乘"
                     % (wx, status, item["liuxing_qi"], cheng))
        susceptible = ["%s（本运不足之脏）" % _ZANG[wx]]
        if item.get("recovery"):
            # 复气：己所生者来复（子复母仇），客观五行关系
            fu = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}[wx]
            susceptible.append("见%s气来复之候（%s）" % (fu, item["stars"]))
    chain = [
        {"step": 1, "label": "岁运", "text": "%s运%s（%s年干）" % (wx, status, item["gan"])},
        {"step": 2, "label": "气化", "text": item["liuxing_qi"]},
        {"step": 3, "label": "病机", "text": mechanism},
        {"step": 4, "label": "受邪/所关脏腑", "text": "、".join(susceptible)},
        {"step": 5, "label": "经典病候", "text": item["binghou"]},
    ]
    if item.get("binghou_severe"):
        chain.append({"step": 6, "label": "甚则/复气病候", "text": item["binghou_severe"]})
    if item.get("shanglin"):
        if shanglin_active:
            chain.append({"step": 7, "label": "上临变局（本岁成立）",
                          "text": item["shanglin"]})
        else:
            chain.append({"step": 7, "label": "上临变局（本岁不成立）",
                          "text": "原文另载：" + item["shanglin"] + "——须对应司天之年方成立，本岁不符，不据以论病。"})
    chain.append({"step": 9, "label": "原文", "text": item["locator"]})
    return chain


def pathomech_for(yun_wx, raw_status, sitian_name=None):
    """主入口：岁运五行 + 太过/不及（平气返回 None，提示平气无偏胜病机可套）
    + 可选当年司天名（用于判断'上临'是否真的成立）。
    返回 dict（含 chain/quote/locator 与上临成立标记），或 None。
    """
    if raw_status not in ("太过", "不及"):
        return None
    lib = load_library()
    if not lib:
        return None
    key = _KEY.get((yun_wx, raw_status))
    if not key:
        return None
    item = next((x for x in lib["items"] if x["key"] == key), None)
    if not item:
        return None

    shanglin_active = False
    shanglin_note = None
    if item.get("shanglin"):
        # 原文"上临"绑定特定司天（括号内所列）。只有本次推算的司天命中原文所列，
        # 该变局本年才成立；否则明确标注不成立，不得据以论病。
        need_tokens = _extract_sitian_tokens(item["shanglin"])
        if sitian_name and any(tok in sitian_name for tok in need_tokens):
            shanglin_active = True
            shanglin_note = "本岁司天「%s」与原文所列相符，'上临'变局本年成立。" % sitian_name
        else:
            shanglin_note = ("原文另载'上临%s'之变局，但本岁司天为「%s」，与原文所列不符，"
                             "故本年不采此上临病候。"
                             % ("、".join(need_tokens), sitian_name or "未提供"))

    return {
        "yun_wx": yun_wx,
        "status": raw_status,
        "liuxing_qi": item["liuxing_qi"],
        "affected_zang": item["affected_zang"],
        "affected_relation": item["affected_relation"],
        "binghou": item["binghou"],
        "binghou_severe": item.get("binghou_severe"),
        "death_pulse": item.get("death_pulse"),
        "recovery": item.get("recovery"),
        "shanglin_text": item.get("shanglin"),
        "shanglin_active_this_year": shanglin_active,
        "shanglin_note": shanglin_note,
        "stars": item.get("stars"),
        "bingwei": item.get("bingwei"),
        "chain": _infer_chain(item, shanglin_active),
        "quote": item["quote"],
        "locator": item["locator"],
        "confidence": "high",
        "confidence_basis": "local_pian",
        "confidence_basis_cn": "本地冻结权威本·篇段原文（逐字核于《素问·五运行大论》本地索引）",
        "disclaimer": ("岁运病机为气化背景/易感倾向，非诊断、非处方；须与患者真实四诊及经方辨证"
                       "合参，冲突时以四诊为准。"),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="岁运病机离线库查询")
    ap.add_argument("--wx", required=True, choices=list(_ZANG), help="岁运五行 木火土金水")
    ap.add_argument("--status", required=True, choices=["太过", "不及"])
    a = ap.parse_args()
    r = pathomech_for(a.wx, a.status)
    print(json.dumps(r, ensure_ascii=False, indent=2))
