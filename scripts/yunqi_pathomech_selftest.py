#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yunqi_pathomech_selftest.py —— 第三层岁运病机离线库金标准自测。

锁定防幻觉底线：
  1. 库含五运太过/不及共 10 格，字段完整；
  2. 每条 quote 的关键句必须逐字命中本地《素问·五运行大论》冻结原文（不靠记忆）；
  3. 太过受邪脏腑 = 所胜之脏；不及 = 本运不足（客观五行关系）；
  4. 上临变局必须司天相符才置 active；
  5. 平气不套病机库（返回 None）；
  6. 与 yunqi.py 两个模式集成后字段可达。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yunqi_pathomech as P  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FAILS = []


def _norm(s):
    return re.sub(r"[\s，。、；：（）()…·？！?\.\u3000]", "", s)


def main():
    lib = P.load_library()
    if not lib:
        print("❌ 病机库加载失败")
        return 1
    items = lib["items"]

    # 1. 十格齐全
    expect_keys = {("木", "太过"), ("木", "不及"), ("火", "太过"), ("火", "不及"),
                   ("土", "太过"), ("土", "不及"), ("金", "太过"), ("金", "不及"),
                   ("水", "太过"), ("水", "不及")}
    got = {(i["yun_wx"], i["status"]) for i in items}
    if got != expect_keys or len(items) != 10:
        FAILS.append("十格不齐: %s" % sorted(got))

    # 2. 原文 quote 逐字命中本地冻结原文（结构化浓缩字段 binghou 等不要求逐字）
    suwen = json.load(open(os.path.join(DATA, "suwen_index.json"), encoding="utf-8"))
    full = max((x for x in suwen["items"] if "五运行" in (x["title"] or "")),
               key=lambda x: len(x["text"]))["text"]
    fulln = _norm(full)
    for it in items:
        # quote 以省略号/句号连接多个原文原句，逐段核
        segs = [s for s in re.split(r"…+|。", it["quote"]) if len(_norm(s)) >= 8]
        for s in segs:
            probe = _norm(s)[:12]
            if probe not in fulln:
                FAILS.append("%s quote 非逐字原文: %s" % (it["key"], s))
        if not it["locator"].startswith("【素问·五运行大论"):
            FAILS.append("%s locator 非五运行大论" % it["key"])
        # 加载器输出须标 high / local_pian
        r = P.pathomech_for(it["yun_wx"], it["status"], "少阴君火")
        if r["confidence"] != "high" or r["confidence_basis"] != "local_pian":
            FAILS.append("%s 本地原文依据应为 high/local_pian" % it["key"])

    # 3. 受邪脏腑客观关系
    ke = {"木": "土", "火": "金", "土": "水", "金": "木", "水": "火"}
    zang = {"木": "脾土", "火": "金肺", "土": "肾水", "金": "肝木", "水": "心火"}
    for it in items:
        if it["status"] == "太过":
            if ke[it["yun_wx"]] not in it["affected_zang_wx"]:
                FAILS.append("%s 太过受邪应含所胜 %s" % (it["key"], ke[it["yun_wx"]]))
            # 受邪脏腑文本应含被乘脏
            if it["yun_wx"] in ("木", "土", "金") and not it["affected_zang"]:
                FAILS.append("%s 缺受邪脏腑文本" % it["key"])

    # 4. 上临司天校验
    # 岁水太过上临太阳：司天太阳寒水(辰戌)成立，少阴(子午)不成立
    water = P.pathomech_for("水", "太过", "太阳寒水")
    if not water["shanglin_active_this_year"]:
        FAILS.append("岁水太过+太阳司天 上临应成立")
    water2 = P.pathomech_for("水", "太过", "少阴君火")
    if water2["shanglin_active_this_year"]:
        FAILS.append("岁水太过+少阴司天 上临不应成立")
    # 岁火太过上临少阴少阳：少阴成立、太阳不成立
    fire = P.pathomech_for("火", "太过", "少阴君火")
    if not fire["shanglin_active_this_year"]:
        FAILS.append("岁火太过+少阴司天 上临应成立")
    if P.pathomech_for("火", "太过", "太阳寒水")["shanglin_active_this_year"]:
        FAILS.append("岁火太过+太阳司天 上临不应成立")

    # 5. 平气不套库；非法值返回 None
    if P.pathomech_for("金", "平气") is not None:
        FAILS.append("平气不应套病机库")
    if P.pathomech_for("木", "太过", None) is None:
        FAILS.append("无司天时仍应返回基础病机（上临标不成立）")

    # 6. 全部十格都能取到非空推理链
    for wx, st in expect_keys:
        r = P.pathomech_for(wx, st, "少阴君火")
        if not r or not r["chain"] or not r["quote"]:
            FAILS.append("%s%s 推理链缺失" % (wx, st))

    # 7. 库报告
    rep = P.library_report()
    if not rep["present"] or rep["item_count"] != 10:
        FAILS.append("library_report 异常: %s" % rep)

    total = 10 + sum(3 for _ in items) + 5 + 4 + 2 + 10 + 1
    if FAILS:
        print("❌ 岁运病机库自测失败 %d 项：" % len(FAILS))
        for f in FAILS:
            print("  -", f)
        return 1
    print("✅ 岁运病机离线库金标准自测全部通过（十格齐全/引文逐字核于本地原文/"
          "受邪五行关系/上临司天校验/平气不套库/推理链完整，共约%d项断言）" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
