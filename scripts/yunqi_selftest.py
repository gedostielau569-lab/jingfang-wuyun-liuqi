#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五运六气引擎金标准自测（纯本地，不触网）。

校验 yunqi.py 的客观干支运气推算，口径为中医运气学通行结论：
- 岁运：甲己化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火；阳干太过、阴干不及。
- 司天：子午少阴君火、丑未太阴湿土、寅申少阳相火、卯酉阳明燥金、
        辰戌太阳寒水、巳亥厥阴风木；在泉为其正对化。
- 客气六步：三之气=司天、终之气=在泉，按三阴三阳环序排列。
- 主气六步固定：厥阴风木→少阴君火→少阳相火→太阴湿土→阳明燥金→太阳寒水。
- 节气：2000 年大寒 1/20、立春 2/4。

用法：python3 yunqi_selftest.py   （退出码 0=全过，1=有失败）
"""
import json
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "yunqi.py")


def calc(date, calendar="gregorian", hour=None, gender=None):
    args = [sys.executable, CLI, "calc", "--date", date, "--calendar", calendar]
    if hour is not None:
        args += ["--hour", str(hour)]
    if gender:
        args += ["--gender", gender]
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout), r.returncode


# 公历生日：(日期, 年柱, 岁运五行, 太过/不及, 司天, 在泉)
GOLDEN = [
    ("1984-06-15", "甲子", "土", "太过", "少阴君火", "阳明燥金"),
    ("1990-06-15", "庚午", "金", "太过", "少阴君火", "阳明燥金"),
    ("2000-08-15", "庚辰", "金", "太过", "太阳寒水", "太阴湿土"),
    ("2019-06-15", "己亥", "土", "不及", "厥阴风木", "少阳相火"),
    ("2020-06-15", "庚子", "金", "太过", "少阴君火", "阳明燥金"),
    ("2024-06-15", "甲辰", "土", "太过", "太阳寒水", "太阴湿土"),
    ("1937-07-07", "丁丑", "木", "不及", "太阴湿土", "太阳寒水"),
    ("2000-01-01", "己卯", "土", "不及", "阳明燥金", "少阴君火"),
    ("1955-07-01", "乙未", "金", "不及", "太阴湿土", "太阳寒水"),
    ("1966-07-01", "丙午", "水", "太过", "少阴君火", "阳明燥金"),
]

# 客气六步金标准（司天在泉年两种代表）
KEQI_STEPS = [
    ("子", 0, ["太阳寒水", "厥阴风木", "少阴君火", "太阴湿土", "少阳相火", "阳明燥金"]),
    ("卯", 3, ["太阴湿土", "少阳相火", "阳明燥金", "太阳寒水", "厥阴风木", "少阴君火"]),
]

ZHUQI_FIXED = ["厥阴风木", "少阴君火", "少阳相火",
               "太阴湿土", "阳明燥金", "太阳寒水"]


def main():
    fails = []

    # 1. 岁运/司天/在泉金标准
    for date, gz, wx, tg, st, zq in GOLDEN:
        d, code = calc(date)
        yg = d["bazi"]["year"]["ganzhi"]
        sy, lq = d["suiyun"], d["liuqi"]
        raw = sy.get("raw_status", sy["status"])
        checks = {
            "年柱": (yg, gz),
            "岁运五行": (sy["wuxing"], wx),
            "太过不及": (raw, tg),
            "司天": (lq["sitian"], st),
            "在泉": (lq["zaiquan"], zq),
        }
        for k, (got, exp) in checks.items():
            if got != exp:
                fails.append(f"{date} {gz} {k}: 得{got} 期望{exp}")

    # 2. 客气六步
    import yunqi as Y
    for zhi_name, zhi_idx, exp_steps in KEQI_STEPS:
        st_idx = Y.SITIAN_IDX_BY_ZHI[zhi_idx]
        got = [Y.LIUQI[i]["name"] for i in Y.keqi_step_indices(st_idx)]
        if got != exp_steps:
            fails.append(f"{zhi_name}年客气六步: 得{got} 期望{exp_steps}")
        if got[2] != exp_steps[2] or got[5] != exp_steps[5]:
            fails.append(f"{zhi_name}年三之气/终之气未落在司天/在泉")

    # 3. 主气固定序
    got_zhu = [Y.zhuqi_for_step(i + 1)["name"] for i in range(6)]
    if got_zhu != ZHUQI_FIXED:
        fails.append(f"主气六步: 得{got_zhu} 期望{ZHUQI_FIXED}")

    # 4. 节气（天文近似，±1日内，取精确命中的代表年）
    if Y.jieqi_date(2000, 1) != (1, 20):
        fails.append(f"2000大寒: 得{Y.jieqi_date(2000,1)} 期望(1,20)")
    if Y.jieqi_date(2000, 2) != (2, 4):
        fails.append(f"2000立春: 得{Y.jieqi_date(2000,2)} 期望(2,4)")

    # 5. 农历换算：农历1990腊月十五 = 公历1991-01-30，年柱庚午
    d, code = calc("1990-12-15", calendar="lunar")
    if d["gregorian_date"] != "1991-01-30" or \
            d["lunar_date"]["year_ganzhi"] != "庚午":
        fails.append(f"农历1990-12-15: 得{d['gregorian_date']}/"
                     f"{d['lunar_date']['year_ganzhi']} 期望1991-01-30/庚午")

    # 6. 时柱：1990-06-15 14时（未时）
    d, code = calc("1990-06-15", hour=14)
    hg = (d.get("bazi", {}).get("hour") or {}).get("ganzhi")
    if hg != "乙未":
        fails.append(f"1990-06-15 14时 时柱: 得{hg} 期望乙未")

    # 7. 四柱八字（年柱立春分界、月柱五虎遁、日柱查表、时柱五鼠遁）
    BAZI_GOLDEN = [
        ("2000-01-01", ("己卯", "丁丑", "戊午")),
        ("2000-08-15", ("庚辰", "甲申", "乙巳")),
        ("2019-06-15", ("己亥", "庚午", "癸未")),
        ("2024-02-04", ("甲辰", "丙寅", "戊戌")),
        ("1990-06-15", ("庚午", "壬午", "辛亥")),
        ("1984-06-15", ("甲子", "庚午", "庚辰")),
    ]
    for ds, (ey, em, ed) in BAZI_GOLDEN:
        d, code = calc(ds)
        bz = d.get("bazi", {})
        gy = (bz.get("year") or {}).get("ganzhi")
        gm = (bz.get("month") or {}).get("ganzhi")
        gd = (bz.get("day") or {}).get("ganzhi")
        if (gy, gm, gd) != (ey, em, ed):
            fails.append(f"{ds} 四柱: 得{gy}/{gm}/{gd} 期望{ey}/{em}/{ed}")

    # 8. 非法参数不崩
    d, code = calc("abc")
    if "error" not in d:
        fails.append("非法日期未返回 error 结构")

    # 9. 运气同化格局：遍历六十甲子，逐类对金标准年表
    def _gz_idx(name):
        gi, zi = Y.GAN.index(name[0]), Y.ZHI.index(name[1])
        for i in range(60):
            if i % 10 == gi and i % 12 == zi:
                return i
        raise ValueError(name)
    GEJU_GOLD = {
        "tianfu": ["戊子", "戊午", "戊寅", "戊申", "丙辰", "丙戌", "丁巳", "丁亥",
                    "乙卯", "乙酉", "己丑", "己未"],
        "suihui": ["甲辰", "甲戌", "乙酉", "丙子", "丁卯", "戊午", "己丑", "己未"],
        "taiyi": ["戊午", "乙酉", "己丑", "己未"],
        "tong_tianfu": ["甲辰", "甲戌", "庚子", "庚午", "壬寅", "壬申"],
        "tong_suihui": ["辛丑", "辛未", "癸卯", "癸酉", "癸巳", "癸亥"],
    }
    GEJU_FLAG = {"tianfu": "tianfu", "suihui": "suihui", "taiyi": "taiyi_tianfu",
                 "tong_tianfu": "tong_tianfu", "tong_suihui": "tong_suihui"}
    geju_hits = {k: 0 for k in GEJU_GOLD}
    for idx in range(60):
        g = Y.yunqi_geju(idx % 10, idx % 12)
        nm = Y.ganzhi_of(idx)
        for k, years in GEJU_GOLD.items():
            hit = bool(g[GEJU_FLAG[k]])
            if hit:
                geju_hits[k] += 1
            if hit != (nm in years):
                fails.append(f"格局{k} {nm}: 得{hit} 期望{nm in years}")
    # 年数合计：天符12 岁会8 太乙4 同天符6 同岁会6
    for k, years in GEJU_GOLD.items():
        if geju_hits[k] != len(years):
            fails.append(f"格局{k} 命中年数: 得{geju_hits[k]} 期望{len(years)}")
    # 反例陷阱：壬寅/庚申/癸巳/辛亥 运与岁支五行虽合，不当四正之位，非岁会
    for trap in ["壬寅", "庚申", "癸巳", "辛亥"]:
        gi = _gz_idx(trap)
        if Y.yunqi_geju(gi % 10, gi % 12)["suihui"]:
            fails.append(f"四正位陷阱 {trap} 被误判为岁会")

    # 10. 岁气模式：气象年大寒分界、当下步位、格局随附
    sq = Y.suiqian("2026-01-19")
    if sq["qi_year"]["ganzhi"] != "乙巳":
        fails.append(f"岁气大寒前: 得{sq['qi_year']['ganzhi']} 期望乙巳")
    sq2 = Y.suiqian("2026-01-20")
    if sq2["qi_year"]["ganzhi"] != "丙午" or sq2["suiyun"]["wuxing"] != "水":
        fails.append(f"岁气大寒起: 得{sq2['qi_year']['ganzhi']}/{sq2['suiyun']['wuxing']} 期望丙午/水")
    sq3 = Y.suiqian("1978-07-01")  # 戊午太乙天符
    if "太乙天符" not in sq3["yunqi_geju"]["matched"]:
        fails.append(f"岁气戊午: 得{sq3['yunqi_geju']['matched']} 期望含太乙天符")
    # 出生模式 calc 也应挂接格局（乙酉为太乙）
    d, _ = calc("1945-08-15")
    if "太乙天符" not in d.get("yunqi_geju", {}).get("matched", []):
        fails.append("出生模式 1945乙酉 未挂接太乙天符")

    total = (len(GOLDEN) * 5 + len(KEQI_STEPS) + 3 + len(BAZI_GOLDEN) * 3
             + 1 + sum(len(v) * 2 for v in GEJU_GOLD.values()) + 4 + 4 + 1)
    if fails:
        print("❌ 运气自测失败 %d 项：" % len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("✅ 五运六气金标准自测全部通过（岁运/太过不及/司天在泉/客气六步/"
          "主气/节气/农历/时柱/容错/运气同化格局/岁气模式，共%d项断言）" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
