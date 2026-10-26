#!/usr/bin/env python3
"""
五运六气推算模块 (yunqi.py)

独立 CLI，输入出生日期，输出中医运气学客观干支参数（JSON）。
仅使用 Python 3.13 标准库。

用法：
  python3 yunqi.py calc --date 1990-06-15 [--calendar gregorian|lunar]
                        [--hour 14] [--gender 男|女] [--place "山东济南"]

口径：
  - 年柱：以立春分界（主流八字口径）
  - 岁运/六气/主客气：以"大寒"交司为起算口径
  - 平气：只采用可确定性判定的"干德符"（出生日干=岁运年干）；齐化等需交司时刻、流派分歧大，不程序化
  - 运气同化格局：天符/岁会/太乙天符/同天符/同岁会（calc 与 suiqi 均输出 yunqi_geju）
  - 两个模式：calc（出生禀赋）/ suiqi（发病或就诊当年当下岁气背景，不依赖生日）
  - 农历/节气数据：1900–2100 内嵌；节气使用寿星天文历近似公式（±1 天）

结果仅供经典研习与编程引用，不构成任何诊断/处方/医学结论。
"""

from __future__ import annotations
import argparse
import json
import math
import sys
from datetime import datetime, date

# ============================================================
# 第三层：岁运病机离线库（延迟导入，缺失时静默降级为纯检索接地）
# ============================================================
def _suiyun_pathomech(wuxing, raw_status, sitian_name):
    try:
        import yunqi_pathomech as _YP
        return _YP.pathomech_for(wuxing, raw_status, sitian_name)
    except Exception:
        return None


# ============================================================
# 常量表
# ============================================================

GAN = list("甲乙丙丁戊己庚辛壬癸")
ZHI = list("子丑寅卯辰巳午未申酉戌亥")
WUXING = list("木火土金水")
YINYANG_GAN = {
    "甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
    "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴",
}
YINYANG_ZHI = {
    "子": "阳", "丑": "阴", "寅": "阳", "卯": "阴", "辰": "阳", "巳": "阴",
    "午": "阳", "未": "阴", "申": "阳", "酉": "阴", "戌": "阳", "亥": "阴",
}
GAN_WX = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
ZHI_WX = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
LUNAR_DAY_NAMES = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]
LUNAR_MONTH_NAMES = [
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "冬月", "腊月",
]

# 天干五合化运：甲己→土 乙庚→金 丙辛→水 丁壬→木 戊癸→火
# 甲己化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火（WUXING=[木,火,土,金,水]）
SUIYUN_WX_BY_GAN_IDX = [2, 3, 4, 0, 1]  # 甲|己→土(2) 乙|庚→金(3) 丙|辛→水(4) 丁|壬→木(0) 戊|癸→火(1)
WUYIN_NAME = ["宫", "商", "角", "徵", "羽"]  # 土宫 金商 木角 火徵 水羽
WX_TO_WUYIN = {"土": "宫", "金": "商", "木": "角", "火": "徵", "水": "羽"}

# 24 节气（index 0..23，从冬季开始：小寒/大寒/立春/雨水/惊蛰/春分/…/冬至）
# 其中偶数位(0,2,4,...) 为"节"(月始)，奇数位(1,3,5,...) 为"中气"
# 节气计算：基于太阳黄经（Meeus《Astronomical Algorithms》简化算法）
# 太阳黄经每 15° 一个节气：0=春分, 15=清明, ..., 285=小寒, 300=大寒, 315=立春, ...
# 索引 0 对应小寒(285°)，1 大寒(300°)，...，23 冬至(270°)
JIEQI_NAMES = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]
JIEQI_LONGITUDES = [
    285, 300, 315, 330, 345, 0,
    15,  30,  45,  60,  75,  90,
    105, 120, 135, 150, 165, 180,
    195, 210, 225, 240, 255, 270,
]

# 八字月支表：月1(寅)=0, ..., 月12(丑)=11
BAZI_MONTH_ZHI_IDX = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0, 1]
BAZI_MONTH_NAME = [
    "寅月", "卯月", "辰月", "巳月", "午月", "未月",
    "申月", "酉月", "戌月", "亥月", "子月", "丑月",
]

def _solar_longitude(jd: float) -> float:
    """太阳视黄经（度），近似精度 ±0.01°（约 1 小时内）。"""
    T = (jd - 2451545.0) / 36525.0
    # 太阳平黄经
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    # 太阳平近点角
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    Mr = math.radians(M)
    # 中心方程（Meeus 公式）
    C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(Mr) \
        + (0.019993 - 0.000101 * T) * math.sin(2 * Mr) \
        + 0.000289 * math.sin(3 * Mr)
    sun_lon = L0 + C
    # 简化章动修正
    omega = math.radians(125.04 - 1934.136 * T)
    return (sun_lon - 0.00569 - 0.00478 * math.sin(omega)) % 360


def _gregorian_from_jd(jd: float) -> tuple:
    """儒略日（整数 JD）→ (年, 月, 日)"""
    z = int(math.floor(jd + 0.5))
    a = z + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, int(month), int(day)


def _find_jd_for_longitude(target_lon: float, jd_start: float) -> float:
    """牛顿迭代求太阳黄经 = target_lon 的 JD"""
    jd = jd_start
    for _ in range(30):
        lon = _solar_longitude(jd)
        diff = (target_lon - lon + 180) % 360 - 180  # [-180, 180)
        if abs(diff) < 0.001:
            return jd
        jd += diff * 365.2422 / 360.0
    return jd


def jieqi_date(year: int, jq_index: int) -> tuple:
    """返回节气对应 (月, 日)，误差 0 日（公历近似算法精度 ±1h 内）"""
    target_lon = JIEQI_LONGITUDES[jq_index]
    # 起点：取该节气的大致公历日期附近
    # 小寒≈1-5, 大寒≈1-20, 立春≈2-4, ... 粗略按 (month=1+(jq_index//2), day=5+(jq_index%2)*15)
    # 更准确：基于太阳黄经 285°(小寒) 约在 1 月 5-6 日
    if jq_index in (0, 1):  # 小寒、大寒：本年 1 月
        jd_start = jdn(year, 1, 1) + 3.5
    elif jq_index in (22, 23):  # 大雪、冬至：上年 12 月
        jd_start = jdn(year, 12, 1) + 5.5
    else:
        # 其它节气：大致 month = (jq_index // 2) + 1，day ≈ 5/20
        approx_month = (jq_index // 2) + 1
        if approx_month > 12:
            approx_month -= 12
        jd_start = jdn(year, approx_month, 1) + 3.5
    jd_hit = _find_jd_for_longitude(target_lon, jd_start)
    _, m, d = _gregorian_from_jd(jd_hit)
    return m, d

# 纳音六十甲子（每 2 个干支共享一个纳音），共 30 项
NAYIN_TABLE = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]
# 五行部分
NAYIN_WX_TABLE = ["金", "火", "木", "土", "金", "火", "水", "土", "金", "木",
                  "水", "土", "火", "木", "水", "金", "火", "木", "土", "金",
                  "火", "水", "土", "金", "木", "水", "土", "火", "木", "水"]

# 五行生克
WX_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 我生
WX_SHENG_BY = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}  # 生我
WX_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}  # 我克(所胜)
WX_KE_BY = {"木": "金", "火": "水", "土": "木", "金": "火", "水": "土"}  # 克我(所不胜)

# 六气表
LIUQI = [
    {"name": "厥阴风木",   "wx": "木", "si": "厥阴", "attr": "风木"},
    {"name": "少阴君火",   "wx": "火", "si": "少阴", "attr": "君火"},
    {"name": "少阳相火",   "wx": "火", "si": "少阳", "attr": "相火"},
    {"name": "太阴湿土",   "wx": "土", "si": "太阴", "attr": "湿土"},
    {"name": "阳明燥金",   "wx": "金", "si": "阳明", "attr": "燥金"},
    {"name": "太阳寒水",   "wx": "水", "si": "太阳", "attr": "寒水"},
]

# 年支→司天 index（子=0,...,亥=11），index 取 LIUQI 数组下标
# 子午→少阴君火(1); 丑未→太阴湿土(3); 寅申→少阳相火(2);
# 卯酉→阳明燥金(4); 辰戌→太阳寒水(5); 巳亥→厥阴风木(0)
SITIAN_IDX_BY_ZHI = {
    0: 1, 1: 3, 2: 2, 3: 4, 4: 5, 5: 0,
    6: 1, 7: 3, 8: 2, 9: 4, 10: 5, 11: 0,
}

# 客气环序（三阴三阳）：厥阴(一阴)→少阴(二阴)→太阴(三阴)
#                          →少阳(一阳)→阳明(二阳)→太阳(三阳)，首尾循环。
# 用 LIUQI 数组下标表示此环序。
KEQI_RING = [0, 1, 3, 2, 4, 5]          # 环序位置 → LIUQI 下标
_RING_POS = {li: i for i, li in enumerate(KEQI_RING)}  # LIUQI 下标 → 环序位置


def zaiquan_idx_of(sitian_li_idx: int) -> int:
    """在泉与司天相对（三阴三阳正对化），环序上相隔 3 位。"""
    return KEQI_RING[(_RING_POS[sitian_li_idx] + 3) % 6]


def keqi_step_indices(sitian_li_idx: int) -> list:
    """客气六步（初之气→终之气），三之气为司天、终之气为在泉。
    初之气 = 司天在环序上前两位，依次环行。返回每步的 LIUQI 下标。"""
    st_ring = _RING_POS[sitian_li_idx]
    # 三之气(index2)=司天，故初之气(index0)=司天-2
    return [KEQI_RING[(st_ring - 2 + i) % 6] for i in range(6)]

# 脏腑标签（五行→所系脏腑），纯标签不给诊断
WX_ZANGFU = {
    "木": {"脏": "肝", "腑": "胆", "体": "筋", "窍": "目"},
    "火": {"脏": "心", "腑": "小肠", "体": "脉", "窍": "舌"},
    "土": {"脏": "脾", "腑": "胃", "体": "肉", "窍": "口"},
    "金": {"脏": "肺", "腑": "大肠", "体": "皮", "窍": "鼻"},
    "水": {"脏": "肾", "腑": "膀胱", "体": "骨", "窍": "耳"},
}
# 君火/相火细分
HUO_ZANGFU = {
    "君火": {"脏": "心", "腑": "小肠", "体": "脉", "窍": "舌"},
    "相火": {"脏": "心包", "腑": "三焦", "体": "脉", "窍": "舌"},
}

# 农历数据表 1900–2100（寿星万年历 / lunardate 通用格式，1900–2099 已用 lunardate 验证）
# 每元素 yearInfo 编码：
#   bits  0-3  : 闰月月份（0 表示该年不闰）
#   bit   4    : 闰月长度标志（0 → 闰月 29 天；1 → 闰月 30 天）
#   bits 5-16  : 12 个农历月大小月位图，bit16 = 正月，bit15 = 二月，...，bit5 = 腊月
#                （位值 1 → 30 天；0 → 29 天）
#   bits 17-   : 未使用
# 正月起点对应的公历起日：1900-01-31 = 农历 1900 年正月初一
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,  # 1900-1909
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,  # 1910-1919
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,  # 1920-1929
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,  # 1930-1939
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,  # 1940-1949
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5d0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,  # 1950-1959
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,  # 1960-1969
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b5a0, 0x195a6,  # 1970-1979
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,  # 1980-1989
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,  # 1990-1999
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,  # 2000-2009
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,  # 2010-2019
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,  # 2020-2029
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,  # 2030-2039
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,  # 2040-2049
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06aa0, 0x1a6c4, 0x0aae0,  # 2050-2059
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,  # 2060-2069
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,  # 2070-2079
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,  # 2080-2089
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,  # 2090-2099
    0x0b6a0,  # 2100（据 HKO/万年历对照：2100 庚申年无闰，正月大，各月大小：30,30,29,30,29,30,30,29,30,29,30,30；腊月大）
]

# ============================================================
# 基础工具
# ============================================================

def err(msg: str, code: int = 4) -> dict:
    return {"error": msg, "exit_code": code}


def ganzhi_of(idx: int) -> str:
    """六十甲子序号 → 干支字符串（0=甲子 … 59=癸亥）"""
    return GAN[idx % 10] + ZHI[idx % 12]


def gan_of(idx: int) -> str:
    return GAN[idx % 10]


def zhi_of(idx: int) -> str:
    return ZHI[idx % 12]


def ganzhi_idx(gan_i: int, zhi_i: int) -> int:
    """天干序号 + 地支序号 → 六十甲子序号（需保证同阴阳）"""
    return (gan_i % 10, zhi_i % 12)  # placeholder; we use a different approach below


def nayin(gz_idx: int) -> tuple:
    """六十甲子序号 → (纳音名, 纳音五行)"""
    pair = gz_idx // 2  # 0..29
    return NAYIN_TABLE[pair], NAYIN_WX_TABLE[pair]


def jdn(y: int, m: int, d: int) -> int:
    """公历 → 儒略日编号（适用于 1582-10-15 之后，满足 1900–2100 使用）"""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def day_ganzhi_idx(y: int, m: int, d: int) -> int:
    """日柱六十甲子序号；公式已按已知甲子日（2000-01-07）校准：idx=0 → 甲子"""
    j = jdn(y, m, d)
    return (j + 49) % 60


# ============================================================
# 节气 / 历法
# ============================================================

def all_jieqi_dates(year: int) -> list:
    """返回某年 24 节气对应的 date 对象列表（index 0..23）；个别边界可能 ±1 日"""
    result = []
    for i in range(24):
        m, d = jieqi_date(year, i)
        try:
            result.append(date(year, m, d))
        except ValueError:
            # 若超出该月日数，退到该月最后一天
            if m == 12:
                result.append(date(year, m, 31))
            else:
                result.append(date(year, m + 1, 1) - __import__('datetime').timedelta(days=1))
    return result


# ----- 农历转换 -----

def lunar_year_info(year: int) -> int:
    if year < 1900 or year > 2100:
        raise ValueError("year out of range")
    return LUNAR_INFO[year - 1900]


def lunar_leap_month(lunar_year: int) -> int:
    """返回该年闰月月份（1–12）；0 表示不闰"""
    return lunar_year_info(lunar_year) & 0xF


def lunar_leap_days(lunar_year: int) -> int:
    """该年闰月的天数；若非闰年返回 0"""
    info = lunar_year_info(lunar_year)
    if not (info & 0xF):
        return 0
    return 30 if (info >> 16) & 1 else 29


def lunar_month_days(lunar_year: int, month: int) -> int:
    """非闰月天数；month 1..12"""
    info = lunar_year_info(lunar_year)
    # bit16=正月, bit15=二月, ..., bit5=腊月
    bit = 16 - month
    return 30 if (info >> bit) & 1 else 29


def lunar_year_days(lunar_year: int) -> int:
    """某农历年的总天数"""
    base = 0
    for m in range(1, 13):
        base += lunar_month_days(lunar_year, m)
    base += lunar_leap_days(lunar_year)
    return base


def lunar_to_solar(lunar_year: int, lunar_month: int, lunar_day: int, is_leap: bool = False) -> date:
    """农历 → 公历 date；支持 1900–2100"""
    if lunar_year < 1900 or lunar_year > 2100:
        raise ValueError("农历年的超出 1900–2100 范围")
    # 1900-01-31 = 农历 1900 年正月初一
    base_date = date(1900, 1, 31)
    offset = 0
    for y in range(1900, lunar_year):
        offset += lunar_year_days(y)
    leap_m = lunar_leap_month(lunar_year)
    # 累加完整月
    for m in range(1, lunar_month):
        offset += lunar_month_days(lunar_year, m)
        if m == leap_m:
            offset += lunar_leap_days(lunar_year)
    # 当前月定位
    if is_leap:
        if lunar_month != leap_m:
            raise ValueError(f"农历 {lunar_year} 年无闰{ lunar_month} 月")
        offset += lunar_month_days(lunar_year, lunar_month)  # 先过正常月
    else:
        pass
    offset += lunar_day - 1
    return base_date + __import__('datetime').timedelta(days=offset)


def jdn_to_date(j: int) -> date:
    """JDN → 公历 date"""
    # 使用 Fliegel & Van Flandern (1968) 反推
    L = j + 68569
    N = 4 * L // 146097
    L = L - (146097 * N + 3) // 4
    I = 4000 * (L + 1) // 1461001
    L = L - 1461 * I // 4 + 31
    J = 80 * L // 2447
    d = L - 2447 * J // 80
    L = J // 11
    m = J + 2 - 12 * L
    y = 100 * (N - 49) + I + L
    return date(y, m, d)


def solar_to_lunar(solar: date) -> dict:
    """公历 date → 农历 {year, month, day, is_leap, month_name, day_name, year_shengxiao}"""
    if solar < date(1900, 1, 31) or solar > date(2100, 12, 31):
        raise ValueError("公历日期超出 1900–2100 范围")
    base_jdn = jdn(1900, 1, 31)
    offset = (solar - date(1900, 1, 31)).days
    ly = 1900
    while ly <= 2100:
        yd = lunar_year_days(ly)
        if offset < yd:
            break
        offset -= yd
        ly += 1
    # 在 ly 年内定位月/日（含闰月）
    leap_m = lunar_leap_month(ly)
    lm = 1
    is_leap = False
    while True:
        # 当前主月
        md = lunar_month_days(ly, lm)
        if offset < md:
            is_leap = False
            break
        offset -= md
        # 若该月后紧跟闰月，先尝试闰月
        if leap_m == lm:
            md2 = lunar_leap_days(ly)
            if offset < md2:
                is_leap = True
                break
            offset -= md2
        # 若已是腊月，退出（不应发生：全年总天数已扣除）
        if lm == 12:
            is_leap = False
            break
        lm += 1
    ld = offset + 1
    month_name = ("闰" if is_leap else "") + LUNAR_MONTH_NAMES[lm - 1]
    day_name = LUNAR_DAY_NAMES[ld - 1]
    # 生肖以年支（以立春分界近似取农历年对应的地支）
    year_gz_idx = (ly - 4) % 60
    shengxiao = SHENGXIAO[ZHI_IDX(year_gz_idx)]
    return {
        "year": ly,
        "month": lm,
        "day": ld,
        "is_leap": is_leap,
        "month_name": month_name,
        "day_name": day_name,
        "year_ganzhi": ganzhi_of(year_gz_idx),
        "shengxiao": shengxiao,
    }


def ZHI_IDX(idx: int) -> int:
    return idx % 12


# ============================================================
# 八字四柱
# ============================================================

def bazi_year_ganzhi(solar: date) -> int:
    """年柱六十甲子序号（以立春分界）"""
    # 计算该年立春日期
    year = solar.year
    lichun = jieqi_date(year, 2)  # index 2 = 立春
    lichun_d = date(year, lichun[0], lichun[1])
    effective_year = year if solar >= lichun_d else year - 1
    return (effective_year - 4) % 60


def bazi_month_info(solar: date) -> dict:
    """返回月柱信息（以 12 个"节"分界）；含月份（1..12）、起止节、月干支序号、月支索引"""
    year = solar.year
    # 12 节在 24 节气中的索引：偶数位 = 节，奇数位 = 中气
    # 月1立春=2, 月2惊蛰=4, ..., 月11大雪=22, 月12小寒(次年)=0
    jie_indices = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
    jie_dates = []
    for ji in jie_indices:
        m, d = jieqi_date(year, ji)
        jie_dates.append(date(year, m, d))
    # 次年小寒（月 12 起点）
    m12_m, m12_d = jieqi_date(year + 1, 0)
    jie_dates.append(date(year + 1, m12_m, m12_d))

    bazi_month = None
    # 先处理跨年：立春前 → 上一年 12 月
    lichun = jie_dates[0]
    xiaohan_next = jie_dates[11]
    if solar < lichun:
        prev_year = year - 1
        pm, pd = jieqi_date(prev_year, 22)  # 上年大雪
        dahan_prev = date(prev_year, pm, pd)
        nm, nd = jieqi_date(prev_year + 1, 0)  # 当年小寒
        nxiaohan = date(nm, nd) if nm == prev_year + 1 else date(prev_year + 1, nm, nd)
        if dahan_prev <= solar < nxiaohan:
            bazi_month = 12
        else:
            # 用上一年的节再细分（简化：归为上一年的某月）
            prev_jie = []
            for ji in jie_indices:
                mm, dd = jieqi_date(prev_year, ji)
                prev_jie.append(date(prev_year, mm, dd))
            # 找到 solar 所在区间
            for k in range(10, -1, -1):
                if solar >= prev_jie[k]:
                    bazi_month = k + 1
                    break
            if bazi_month is None:
                bazi_month = 12  # 大雪前 → 腊月
    else:
        # 当年：从月 1 到月 11 逐段查找
        for k in range(11):
            if jie_dates[k] <= solar < jie_dates[k + 1]:
                bazi_month = k + 1
                break
        # 大雪后：月 12
        if bazi_month is None and solar >= jie_dates[10]:
            bazi_month = 12
        # 极端兜底（不应发生）
        if bazi_month is None:
            bazi_month = 1

    # 确定起止节名称
    if bazi_month <= 10:
        start_jie = JIEQI_NAMES[jie_indices[bazi_month - 1]]
        next_jie = JIEQI_NAMES[jie_indices[bazi_month]]
    elif bazi_month == 11:
        # 月11：立冬(节,index20)起，下一"节"为大雪(index22)
        start_jie = JIEQI_NAMES[20]  # 立冬
        next_jie = JIEQI_NAMES[22]   # 大雪
    else:  # 12 月
        start_jie = JIEQI_NAMES[22]  # 大雪
        next_jie = JIEQI_NAMES[0]   # 小寒

    zhi_idx = BAZI_MONTH_ZHI_IDX[bazi_month - 1]
    return {
        "month": bazi_month,
        "month_zhi_idx": zhi_idx,
        "month_zhi": ZHI[zhi_idx],
        "start_jie": start_jie,
        "next_jie": next_jie,
    }


def bazi_year_stem(solar: date) -> int:
    return bazi_year_ganzhi(solar) % 10


def bazi_month_ganzhi(solar: date) -> int:
    """月柱六十甲子序号"""
    ys = bazi_year_stem(solar)  # 年干 index
    mi = bazi_month_info(solar)
    # 五虎遁：寅月（正月）起干 = 年干组*2+2（甲己丙寅、乙庚戊寅、丙辛庚寅、
    # 丁壬壬寅、戊癸甲寅），其后逐月顺推。mi["month"] 以寅=1。
    month_stem = (ys % 5 * 2 + 2 + (mi["month"] - 1)) % 10
    month_zhi = mi["month_zhi_idx"]
    # 找该组合的六十甲子序号
    # 六十甲子序号 = 某数 idx 使得 idx%10=month_stem, idx%12=month_zhi
    # 因月干月支必须同阴阳（八字月份天然满足），有唯一解
    for idx in range(60):
        if idx % 10 == month_stem and idx % 12 == month_zhi:
            return idx
    # fallback
    return (month_stem * 6 - month_zhi * 5) % 60


def bazi_hour_ganzhi(day_gan_idx: int, hour: int) -> int:
    """时柱六十甲子序号"""
    if hour < 0 or hour > 23:
        raise ValueError("小时超出 0–23")
    if hour == 23:
        zhi_idx = 0  # 子时
    else:
        zhi_idx = (hour + 1) // 2
    # 时干 = (日干 index %5)*2 + 时支 index) %10
    hour_gan = (day_gan_idx % 5 * 2 + zhi_idx) % 10
    for idx in range(60):
        if idx % 10 == hour_gan and idx % 12 == zhi_idx:
            return idx
    return 0


# ============================================================
# 五运六气
# ============================================================

def suiyun(year_gan_idx: int) -> dict:
    """岁运（中运 / 大运）"""
    wx_idx = SUIYUN_WX_BY_GAN_IDX[year_gan_idx % 5]
    wx = WUXING[wx_idx]
    yinyang = YINYANG_GAN[GAN[year_gan_idx]]
    if yinyang == "阳":
        status = "太过"
    else:
        status = "不及"
    wuyin = WX_TO_WUYIN[wx]
    return {
        "wuxing": wx,
        "wuxing_idx": wx_idx,
        "status": status,
        "wuyin": wuyin,
        "year_gan_yinyang": yinyang,
    }


def pingqi_check(year_gan_idx: int, year_zhi_idx: int = None, day_gz_idx: int = None) -> dict:
    """平气判定（只采用可确定性判定的通行规则）：
    - 干德符：日干 = 岁运年干（甲己合土、乙庚合金……同日干与年干同字）→ 不及之运得干德相佐而平。
      需出生日干支；岁气模式无具体出生日则不判。
    - 不做"岁运不及得司天/在泉生助（齐化）"的程序化判定：齐化须看交司时刻，仅凭出生月份/
      年支粗估会误判，且流派分歧大；如需须由执业医师结合精确交节另行判断。
    返回 {"pingqi":bool,"reasons":[...],"type":"干德符"|None}。
    """
    reasons = []
    pq_type = None
    if day_gz_idx is not None and (day_gz_idx % 10) == year_gan_idx:
        reasons.append("干德符（日干与岁运年干相同）")
        pq_type = "干德符"
    return {"pingqi": bool(reasons), "reasons": reasons, "type": pq_type}


def sitian_zaiquan(year_zhi_idx: int) -> dict:
    """年支 → 司天 / 在泉 / 左右间气"""
    st_idx = SITIAN_IDX_BY_ZHI[year_zhi_idx]
    zq_idx = zaiquan_idx_of(st_idx)
    # 客气六步按三阴三阳环序排列（非 LIUQI 数组自然序），三之气=司天、终之气=在泉
    steps = keqi_step_indices(st_idx)
    return {
        "sitian_idx": st_idx,
        "sitian": LIUQI[st_idx]["name"],
        "sitian_wx": LIUQI[st_idx]["wx"],
        "zaiquan_idx": zq_idx,
        "zaiquan": LIUQI[zq_idx]["name"],
        "zaiquan_wx": LIUQI[zq_idx]["wx"],
        "keqi_steps": [LIUQI[i]["name"] for i in steps],
        "keqi_steps_wx": [LIUQI[i]["wx"] for i in steps],
    }


def qibu_of_date(solar: date, month_hack: int = None) -> tuple:
    """确定出生日处于六气第几步（1..6，从大寒起）；返回 (步号, 起点节气, 终点节气)
    注意：若传 month_hack 则仅作平气判定的简化回调用
    """
    if month_hack is not None:
        # 简化：按 bazi 月份粗估 → 仅供平气内部调用，不影响主流程
        if month_hack in (12, 1, 2):
            return 1
        if month_hack in (3, 4):
            return 2
        if month_hack in (5, 6):
            return 3
        if month_hack in (7, 8):
            return 4
        if month_hack in (9, 10):
            return 5
        return 6  # 11月
    year = solar.year
    # 六个步位分界为 4 个节气（大寒/春分/小暑/寒露? 不对）
    # 六步分界：大寒(1), 春分(2), 小满(3), 大暑(4), 秋分(5), 小雪(6)? 需确认
    # 经典：每步 = 4 个节气，起于大寒
    # 初之气：大寒–立春–雨水–惊蛰（≈1.20–3.20）
    # 二之气：春分–清明–谷雨–立夏（≈3.21–5.20）
    # 三之气：小满–芒种–夏至–小暑（≈5.21–7.22）
    # 四之气：大暑–立秋–处暑–白露（≈7.23–9.22）
    # 五之气：秋分–寒露–霜降–立冬（≈9.23–11.21）
    # 终之气：小雪–大雪–冬至–小寒（≈11.22–1.19）
    # 分界节气 index：大寒=1, 春分=5, 小满=9, 大暑=13, 秋分=17, 小雪=21
    step_bounds = [
        (1, "大寒", "春分前"),
        (5, "春分", "小满前"),
        (9, "小满", "大暑前"),
        (13, "大暑", "秋分前"),
        (17, "秋分", "小雪前"),
        (21, "小雪", "大寒前"),
    ]
    # 计算各分界点日期
    bounds = []
    for ji, name, _ in step_bounds:
        m, d = jieqi_date(year, ji)
        try:
            bounds.append((date(year, m, d), name))
        except ValueError:
            bounds.append((date(year, m, max(1, d)), name))
    # 终之气的结束点 = 次年大寒
    nm, nd = jieqi_date(year + 1, 1)
    try:
        next_dahan = date(year + 1, nm, nd)
    except ValueError:
        next_dahan = date(year + 1, nm, max(1, nd))
    # 定位步号
    for i in range(5):
        if bounds[i][0] <= solar < bounds[i + 1][0]:
            return i + 1, bounds[i][1], step_bounds[i + 1][1]
    # 终之气
    if solar >= bounds[5][0]:
        return 6, "小雪", "次年大寒前"
    # 年初到大寒前 → 上年终之气
    return 6, "上年小雪", "大寒前"


def keqi_for_step(sitz: dict, step: int) -> dict:
    """第 step 步客气（1..6）"""
    idx = sitz["keqi_steps"][step - 1]
    wx = sitz["keqi_steps_wx"][step - 1]
    return {"name": idx, "wuxing": wx}


def zhuqi_for_step(step: int) -> dict:
    """第 step 步主气（固定序：厥阴风木, 少阴君火, 少阳相火, 太阴湿土, 阳明燥金, 太阳寒水）"""
    idx = step - 1
    return {"name": LIUQI[idx]["name"], "wuxing": LIUQI[idx]["wx"]}


def kezhu_jialin(ke_wx: str, zhu_wx: str) -> dict:
    """客主加临：主生客=顺；客生主=逆；主克客=不相得；客克主=天刑；同=相得
    口径依据：《素问·六微旨大论》"""
    if ke_wx == zhu_wx:
        return {"relation": "相得", "detail": "客主同气"}
    if WX_SHENG.get(zhu_wx) == ke_wx:
        return {"relation": "顺", "detail": f"主{zhu_wx}生客{ke_wx}"}
    if WX_SHENG.get(ke_wx) == zhu_wx:
        return {"relation": "逆", "detail": f"客{ke_wx}生主{zhu_wx}"}
    if WX_KE.get(zhu_wx) == ke_wx:
        return {"relation": "不相得", "detail": f"主{zhu_wx}克客{ke_wx}"}
    if WX_KE.get(ke_wx) == zhu_wx:
        return {"relation": "天刑", "detail": f"客{ke_wx}克主{zhu_wx}"}
    return {"relation": "未知", "detail": ""}


def zhukeyun_steps(suiyun_wx_idx: int) -> list:
    """主运/客运 五步（大寒起）
    主运：固定 木→火→土→金→水（每年相同）
    客运：以岁运为初运，按五行相生序排五步
    """
    # 主运固定序
    zhu = [{"step": i + 1, "wuxing": WUXING[i], "name": f"第{i+1}运({WUXING[i]})"} for i in range(5)]
    # 客运：从 suiyun_wx_idx 开始按相生序
    sheng_order = [0, 2, 4, 1, 3]  # 木(0)→火(1)→土(2)→金(3)→水(4) → 按五行 idx: 木0,火1,土2,金3,水4
    # 相生序：木→火→土→金→水 → wx_idx 0,1,2,3,4 即按数字序
    ke_steps = []
    start = suiyun_wx_idx
    for i in range(5):
        wx = WUXING[(start + i) % 5]
        ke_steps.append({"step": i + 1, "wuxing": wx, "name": f"第{i+1}运({wx})"})
    return zhu, ke_steps


def zangfu_tags_for_wuxing(wx: str, status: str = None) -> list:
    """基于五行给出脏腑倾向标签；仅给参数化倾向，不给诊断"""
    if wx in ("君火", "相火"):
        info = HUO_ZANGFU[wx]
    else:
        info = WX_ZANGFU.get(wx, {})
    tags = []
    if info:
        tags.append(f"{info['脏']}系（{wx}）")
        tags.append(f"{info['腑']}腑")
    return tags


# ============================================================
# 运气同化格局（第二层）：天符 / 岁会 / 太乙天符 / 同天符 / 同岁会
# 依据《素问·六微旨大论》《六元正纪大论》；金标准年例经多源核对
# （《类经·天符岁会图说》、任应秋《运气学说六讲》）。
# ============================================================

# 岁会只认"五方正位"之支：子水(北) 午火(南) 卯木(东) 酉金(西)，
# 土寄旺四季 辰戌丑未。寅申巳亥虽五行或与运相合，因不当四正之位，
# 《类经》明言"不为岁会"，故不可用普通 ZHI_WX 表判定。
SUIHUI_ORTHO_ZHI_WX = {
    0: "水",   # 子
    6: "火",   # 午
    3: "木",   # 卯
    9: "金",   # 酉
    4: "土", 10: "土", 1: "土", 7: "土",  # 辰 戌 丑 未
}

# 金标准年例（六十甲子干支序号 idx = ganzhi_idx；以下用干支名存证）
_GEJU_GOLD = {
    "tianfu": ["戊子", "戊午", "戊寅", "戊申", "丙辰", "丙戌",
               "丁巳", "丁亥", "乙卯", "乙酉", "己丑", "己未"],
    "suihui": ["甲辰", "甲戌", "乙酉", "丙子", "丁卯", "戊午", "己丑", "己未"],
    "taiyi": ["戊午", "乙酉", "己丑", "己未"],
    "tong_tianfu": ["甲辰", "甲戌", "庚子", "庚午", "壬寅", "壬申"],
    "tong_suihui": ["辛丑", "辛未", "癸卯", "癸酉", "癸巳", "癸亥"],
}


def yunqi_geju(year_gan_idx: int, year_zhi_idx: int) -> dict:
    """按年干支判定运气同化格局。

    - 天符：岁运五行 = 司天五行（中运与司天同化，《六微旨大论》"应天为天符"）。
    - 岁会：岁运五行临五方正位之支（子水午火卯木酉金、土临辰戌丑未），
      寅申巳亥不当四正之位，纵五行相合亦非岁会。
    - 太乙天符：既天符又岁会（司天、中运、岁支三气会合，"三合为治"）。
    - 同天符：阳干太过之运，五行 = 在泉五行。
    - 同岁会：阴干不及之运，五行 = 在泉五行。
    君火/相火在五行同化上皆作"火"，LIUQI[*].wx 已统一为 火。
    返回各布尔标记、命中的格局名（按严重度排序）与逐条依据；只做客观判定，
    不直接给病候或治法（"中执法/行令/贵人"等临床轻重仅作经典提示列出）。
    """
    sy = suiyun(year_gan_idx)
    yun_wx = sy["wuxing"]
    is_yang = YINYANG_GAN[GAN[year_gan_idx]] == "阳"

    st_idx = SITIAN_IDX_BY_ZHI[year_zhi_idx]
    st_wx = LIUQI[st_idx]["wx"]
    zq_idx = zaiquan_idx_of(st_idx)
    zq_wx = LIUQI[zq_idx]["wx"]

    tianfu = (yun_wx == st_wx)
    suihui = SUIHUI_ORTHO_ZHI_WX.get(year_zhi_idx) == yun_wx
    taiyi = tianfu and suihui
    tong_match = (yun_wx == zq_wx)
    tong_tianfu = tong_match and is_yang
    tong_suihui = tong_match and (not is_yang)

    evidence = []
    if tianfu:
        evidence.append(f"天符：岁运{yun_wx}与司天{LIUQI[st_idx]['name']}同气（应天为天符）")
    if suihui:
        zhi_ortho = {0: "子(北方水位)", 6: "午(南方火位)", 3: "卯(东方木位)",
                     9: "酉(西方金位)", 4: "辰(四季土)", 10: "戌(四季土)",
                     1: "丑(四季土)", 7: "未(四季土)"}.get(year_zhi_idx, ZHI[year_zhi_idx])
        evidence.append(f"岁会：岁运{yun_wx}临岁支{zhi_ortho}（承岁为岁直，气之平也）")
    if taiyi:
        evidence.append("太乙天符：天符与岁会并见，司天、中运、岁支三合为治")
    if tong_tianfu:
        evidence.append(f"同天符：阳干太过之{yun_wx}运，与在泉{LIUQI[zq_idx]['name']}同气（太过而加）")
    if tong_suihui:
        evidence.append(f"同岁会：阴干不及之{yun_wx}运，与在泉{LIUQI[zq_idx]['name']}同气（不及而加）")

    names = []
    # 输出排序：太乙最尊，天符次之，岁会/同天符/同岁会并列；同年可多标
    if taiyi:
        names.append("太乙天符")
    if tianfu:
        names.append("天符")
    if suihui:
        names.append("岁会")
    if tong_tianfu:
        names.append("同天符")
    if tong_suihui:
        names.append("同岁会")

    severity_note = None
    if taiyi:
        severity_note = ("《素问·六微旨大论》：天符为执法、岁会为行令、太乙天符为贵人；"
                         "中执法者其病速而危，中行令者其病徐而持，中贵人者其病暴而死。"
                         "此言受邪轻重之经典譬况，须以四诊为准，不可据此径断吉凶。")
    elif tianfu or tong_tianfu:
        severity_note = ("同化纯一，须防其气亢而为害；运气仅为合参背景，"
                         "发病与轻重仍以四诊辨证为准。")

    return {
        "tianfu": tianfu,
        "suihui": suihui,
        "taiyi_tianfu": taiyi,
        "tong_tianfu": tong_tianfu,
        "tong_suihui": tong_suihui,
        "matched": names,
        "evidence": evidence,
        "severity_note": severity_note,
        "rule_ref": "素问·六微旨大论 / 素问·六元正纪大论",
    }


def qi_year_ganzhi_idx(solar: date) -> tuple:
    """运气"气象年"干支（以大寒交运为界）：大寒前属上一年岁。
    返回 (六十甲子idx, 气象公历年)。与 bazi_year_ganzhi（立春界）相区别。"""
    year = solar.year
    m, d = jieqi_date(year, 1)  # 大寒
    try:
        dahan = date(year, m, d)
    except ValueError:
        dahan = date(year, m, max(1, d))
    eff_year = year if solar >= dahan else year - 1
    gz = (eff_year - 4) % 60
    return gz, eff_year


def year_yunqi_core(qi_year: int) -> dict:
    """给定气象公历年，计算全年层面的运气结构（与具体日期无关部分）：
    岁运、平气（年级，不含日干支干德符）、司天在泉、客气六步、运气格局。"""
    gz_idx = (qi_year - 4) % 60
    yg, yz = gz_idx % 10, gz_idx % 12
    sy = suiyun(yg)
    # 年级层面不做平气判定：干德符需具体出生日干，齐化需交司时刻，仅凭气象年无法确定。
    # 平气只在 calc 出生模式（有出生日干支）由 pingqi_check 判干德符。
    pingqi = False
    pq_reasons = []
    sitz = sitian_zaiquan(yz)
    geju = yunqi_geju(yg, yz)
    zhu_yun_list, ke_yun_list = zhukeyun_steps(sy["wuxing_idx"])
    return {
        "qi_year": qi_year,
        "year_ganzhi_idx": gz_idx,
        "year_ganzhi": ganzhi_of(gz_idx),
        "year_gan_idx": yg,
        "year_zhi_idx": yz,
        "suiyun": sy,
        "sitian_zaiquan": sitz,
        "geju": geju,
        "pingqi": pingqi,
        "pingqi_reasons": pq_reasons,
        "zhuyun_steps": zhu_yun_list,
        "keyun_steps": ke_yun_list,
    }


def suiqian(args_date: str = None, calendar: str = "gregorian") -> dict:
    """岁气模式（第一层）：输入就诊/发病日期（缺省=今天），输出当年当下的
    岁气背景——气象年干支、岁运太过/不及、司天在泉、运气同化格局、所处六气
    步位与客主加临、所处主客运。不依赖出生信息，供每次辨证合参。
    只做客观干支运气推算，病候/病机须回《素问》七篇检索，由执业医师判断。"""
    # 1. 解析日期
    if not args_date:
        solar = date.today()
        date_input = solar.isoformat() + "（默认今天）"
        cal_used = "gregorian"
    else:
        date_input = args_date
        try:
            normalized = args_date.replace("--", "-NEG")
            parts = []
            for p in normalized.split("-"):
                if p.startswith("NEG"):
                    parts.append(-int(p[3:]))
                else:
                    parts.append(int(p))
            if len(parts) != 3:
                return err("日期格式错误，应为 YYYY-M-D（闰月：YYYY--M-D）")
            y, mth, dd = parts
        except ValueError:
            return err("日期含非数字字符")
        if calendar == "gregorian":
            try:
                solar = date(y, mth, dd)
            except ValueError as e:
                return err(f"公历日期不合法：{e}")
            cal_used = "gregorian"
        elif calendar == "lunar":
            try:
                solar = lunar_to_solar(y, abs(mth), dd, is_leap=(mth < 0))
            except ValueError as e:
                return err(f"农历日期不合法：{e}")
            cal_used = "lunar"
        else:
            return err("--calendar 仅支持 gregorian | lunar")
    if solar < date(1900, 1, 31) or solar > date(2100, 12, 31):
        return err("公历日期超出 1900-01-31 至 2100-12-31 范围")

    # 2. 气象年（大寒界）与全年运气结构
    gz_idx, qi_year = qi_year_ganzhi_idx(solar)
    core = year_yunqi_core(qi_year)
    sy = core["suiyun"]
    sitz = core["sitian_zaiquan"]
    geju = core["geju"]

    # 3. 当下所处六气步位与客主加临
    step, step_start, step_end = qibu_of_date(solar)
    zhu_qi = zhuqi_for_step(step)
    ke_qi = keqi_for_step(sitz, step)
    jialin = kezhu_jialin(ke_qi["wuxing"], zhu_qi["wuxing"])

    # 4. 当下所处主客运（大寒起，按 73 日均分段的现有口径）
    dm, dd_ = jieqi_date(qi_year, 1)
    try:
        dahan_d = date(qi_year, dm, dd_)
    except ValueError:
        dahan_d = date(qi_year, dm, max(1, dd_))
    yun_step = min(5, max(1, (solar - dahan_d).days // 73 + 1))
    if solar < dahan_d:
        pdm, pdd = jieqi_date(qi_year - 1, 1)
        try:
            prev_dahan = date(qi_year - 1, pdm, pdd)
        except ValueError:
            prev_dahan = date(qi_year - 1, pdm, max(1, pdd))
        yun_step = min(5, max(1, (solar - prev_dahan).days // 73 + 1))
    zhu_yun_cur = core["zhuyun_steps"][yun_step - 1]
    ke_yun_cur = core["keyun_steps"][yun_step - 1]

    # 5. 紧邻节气
    jq_dates = all_jieqi_dates(solar.year)
    prev_name = next_name = None
    prev_jq = next_jq = None
    for i, jqd in enumerate(jq_dates):
        if jqd <= solar:
            prev_jq, prev_name = jqd, JIEQI_NAMES[i]
        if jqd > solar and next_jq is None:
            next_jq, next_name = jqd, JIEQI_NAMES[i]
    if prev_jq is None:
        prev_jq = all_jieqi_dates(solar.year - 1)[-1]
        prev_name = JIEQI_NAMES[-1]
    if next_jq is None:
        next_jq = all_jieqi_dates(solar.year + 1)[0]
        next_name = JIEQI_NAMES[0]

    notes = (
        "本结果按「大寒交运」定气象年与运气步位；岁气模式用于患者就诊/发病当年的"
        "运气背景合参，不需出生信息。岁运、司天在泉、客主加临与运气同化格局均为客观"
        "干支推算；'某运某气偏胜→何脏腑受邪→病候治法'的链条必须回《素问》七篇大论"
        "原文接地，由执业医师判断，不得据此径断疾病或处方。运气与四诊辨证冲突时，"
        "一律以四诊合参为准。"
        " 节气用天文近似公式，交节当日±1日须结合精确时刻复核。"
    )

    return {
        "mode": "suiqian",
        "input": {"date_input": date_input, "calendar": cal_used},
        "gregorian_date": solar.isoformat(),
        "qi_year": {
            "ganzhi": core["year_ganzhi"],
            "gongli_year": qi_year,
            "boundary": "大寒交运",
            "note": f"该日{'已入' if gz_idx == ((solar.year - 4) % 60) else '尚未入'}本年大寒，属{core['year_ganzhi']}气象年",
        },
        "suiyun": {
            "wuxing": sy["wuxing"],
            "wuyin": sy["wuyin"],
            "status": "平气" if core["pingqi"] else sy["status"],
            "raw_status": sy["status"],
            "pingqi": core["pingqi"],
            "pingqi_reasons": core["pingqi_reasons"],
        },
        "liuqi": {
            "sitian": sitz["sitian"], "sitian_wuxing": sitz["sitian_wx"],
            "zaiquan": sitz["zaiquan"], "zaiquan_wuxing": sitz["zaiquan_wx"],
            "keqi_steps": sitz["keqi_steps"],
        },
        "yunqi_geju": geju,
        "suiyun_pathomech": _suiyun_pathomech(sy["wuxing"], sy["status"], sitz["sitian"]),
        "current_period": {
            "liucqi_step": step,
            "liucqi_step_range_jieqi": [step_start, step_end],
            "zhuqi": zhu_qi["name"], "zhuqi_wuxing": zhu_qi["wuxing"],
            "keqi": ke_qi["name"], "keqi_wuxing": ke_qi["wuxing"],
            "kezhu_jialin": jialin["relation"],
            "kezhu_jialin_detail": jialin["detail"],
            "wuyun_step": yun_step,
            "zhuyun_wuxing": zhu_yun_cur["wuxing"],
            "keyun_wuxing": ke_yun_cur["wuxing"],
        },
        "solar_term": {
            "prev_jieqi": prev_name, "prev_jieqi_date": prev_jq.isoformat(),
            "next_jieqi": next_name, "next_jieqi_date": next_jq.isoformat(),
            "days_since_prev": (solar - prev_jq).days,
            "days_to_next": (next_jq - solar).days,
        },
        "rule_refs": ["素问·六微旨大论", "素问·六元正纪大论", "素问·气交变大论",
                      "素问·五常政大论", "素问·至真要大论"],
        "notes": notes,
    }


# ============================================================
# 主流程
# ============================================================

def compute(args_date: str, calendar: str, hour: int, gender: str, place: str) -> dict:
    # 1. 解析日期（公历或农历；农历支持月为负=闰月，如 1993--3-15）
    try:
        # 将 "--" 视为负号分隔，便于表示负月
        normalized = args_date.replace("--", "-NEG")
        parts = []
        for p in normalized.split("-"):
            if p.startswith("NEG"):
                parts.append(int(p[3:]))
                parts[-1] = -parts[-1]
            else:
                parts.append(int(p))
        if len(parts) != 3:
            return err("日期格式错误，应为 YYYY-M-D（闰月：YYYY--M-D）")
        y, m, d = parts
    except ValueError:
        return err("日期含非数字字符")
    # 2. 转公历
    if calendar == "gregorian":
        try:
            solar = date(y, m, d)
        except ValueError as e:
            return err(f"公历日期不合法：{e}")
    elif calendar == "lunar":
        # 月可负=闰月
        is_leap = m < 0
        lm = abs(m)
        try:
            solar = lunar_to_solar(y, lm, d, is_leap=is_leap)
        except ValueError as e:
            return err(f"农历日期不合法：{e}")
    else:
        return err("--calendar 仅支持 gregorian | lunar")
    if solar < date(1900, 1, 31) or solar > date(2100, 12, 31):
        return err("公历日期超出 1900-01-31 至 2100-12-31 范围")
    # 3. 农历信息
    try:
        lunar = solar_to_lunar(solar)
    except ValueError as e:
        return err(str(e))
    # 4. 四柱
    year_gz_idx = bazi_year_ganzhi(solar)
    year_gan_idx = year_gz_idx % 10
    year_zhi_idx = year_gz_idx % 12
    mi = bazi_month_info(solar)
    month_gz_idx = bazi_month_ganzhi(solar)
    month_gan_idx = month_gz_idx % 10
    month_zhi_idx = month_gz_idx % 12
    day_gz_idx = day_ganzhi_idx(solar.year, solar.month, solar.day)
    day_gan_idx = day_gz_idx % 10
    day_zhi_idx = day_gz_idx % 12
    if hour is not None:
        hour_gz_idx = bazi_hour_ganzhi(day_gan_idx, hour)
        hour_gan_idx = hour_gz_idx % 10
        hour_zhi_idx = hour_gz_idx % 12
    else:
        hour_gz_idx = None
        hour_gan_idx = None
        hour_zhi_idx = None

    def pillar_dict(gz_idx, gan_idx, zhi_idx):
        ny, ny_wx = nayin(gz_idx)
        return {
            "ganzhi": ganzhi_of(gz_idx),
            "gan": GAN[gan_idx], "gan_wuxing": GAN_WX[GAN[gan_idx]], "gan_yinyang": YINYANG_GAN[GAN[gan_idx]],
            "zhi": ZHI[zhi_idx], "zhi_wuxing": ZHI_WX[ZHI[zhi_idx]], "zhi_yinyang": YINYANG_ZHI[ZHI[zhi_idx]],
            "nayin": ny, "nayin_wuxing": ny_wx,
        }

    bazi_dict = {
        "year": pillar_dict(year_gz_idx, year_gan_idx, year_zhi_idx),
        "month": pillar_dict(month_gz_idx, month_gan_idx, month_zhi_idx),
        "day": pillar_dict(day_gz_idx, day_gan_idx, day_zhi_idx),
        "hour": pillar_dict(hour_gz_idx, hour_gan_idx, hour_zhi_idx) if hour is not None else None,
    }
    # 5. 节气信息
    # 定位最近的上/下节气
    year = solar.year
    jq_dates = all_jieqi_dates(year)
    # 找上/下节气
    prev_jq = None
    next_jq = None
    prev_name = None
    next_name = None
    for i, jq_d in enumerate(jq_dates):
        if jq_d <= solar:
            prev_jq = jq_d
            prev_name = JIEQI_NAMES[i]
        if jq_d > solar and next_jq is None:
            next_jq = jq_d
            next_name = JIEQI_NAMES[i]
    if prev_jq is None:
        # 取上一年最后一个节气
        prev_y_jq = all_jieqi_dates(year - 1)
        prev_jq = prev_y_jq[-1]
        prev_name = JIEQI_NAMES[-1]
    if next_jq is None:
        nxt_y_jq = all_jieqi_dates(year + 1)
        next_jq = nxt_y_jq[0]
        next_name = JIEQI_NAMES[0]
    # 大寒交运参考
    dahan = jieqi_date(year, 1)
    try:
        dahan_d = date(year, dahan[0], dahan[1])
    except ValueError:
        dahan_d = date(year, dahan[0], max(1, dahan[1]))
    lichun = jieqi_date(year, 2)
    try:
        lichun_d = date(year, lichun[0], lichun[1])
    except ValueError:
        lichun_d = date(year, lichun[0], max(1, lichun[1]))
    days_to_dahan = (dahan_d - solar).days
    # 6. 岁运
    sy = suiyun(year_gan_idx)
    # 7. 平气
    pq = pingqi_check(year_gan_idx, year_zhi_idx, day_gz_idx)
    # 7b. 运气同化格局（天符/岁会/太乙天符/同天符/同岁会）
    geju = yunqi_geju(year_gan_idx, year_zhi_idx)
    # 8. 六气：司天在泉
    sitz = sitian_zaiquan(year_zhi_idx)
    # 9. 主气/客气
    step, step_start, step_end = qibu_of_date(solar)
    zhu_qi = zhuqi_for_step(step)
    ke_qi = keqi_for_step(sitz, step)
    jialin = kezhu_jialin(ke_qi["wuxing"], zhu_qi["wuxing"])
    # 10. 主运/客运
    zhu_yun_list, ke_yun_list = zhukeyun_steps(sy["wuxing_idx"])
    # 主运步位：每年均从大寒起 木→火→土→金→水；按步号定位
    # 主运五步对应六气的步号映射：
    # 初运(木)=初之气~二之气之间；但简化口径：六步每步≈60日，五运每运≈73日，二者并非严格对应
    # 此处采用"按日期在五个均分段"口径：大寒起每 73 日一运
    yun_step = min(5, max(1, (solar - dahan_d).days // 73 + 1))
    if solar < dahan_d:
        # 上一年终运
        prev_dahan = jieqi_date(year - 1, 1)
        try:
            prev_dahan_d = date(year - 1, prev_dahan[0], prev_dahan[1])
        except ValueError:
            prev_dahan_d = date(year - 1, prev_dahan[0], max(1, prev_dahan[1]))
        yun_step = min(5, max(1, (solar - prev_dahan_d).days // 73 + 1))
        if yun_step > 5:
            yun_step = 5
    zhu_yun_cur = zhu_yun_list[yun_step - 1]
    ke_yun_cur = ke_yun_list[yun_step - 1]
    # 11. 综合参数
    obj = {
        "suiyun_wuxing": sy["wuxing"],
        "suiyun_status": "平气" if pq["pingqi"] else sy["status"],
        "suiyun_tai_guo_bu_ji": sy["status"],
        "suiyun_pingqi": pq["pingqi"],
        "sitian": sitz["sitian"],
        "sitian_wuxing": sitz["sitian_wx"],
        "zaiquan": sitz["zaiquan"],
        "zaiquan_wuxing": sitz["zaiquan_wx"],
        "zhuqi": zhu_qi["name"],
        "zhuqi_wuxing": zhu_qi["wuxing"],
        "keqi": ke_qi["name"],
        "keqi_wuxing": ke_qi["wuxing"],
        "kezhu_jialin": jialin["relation"],
        "kezhu_jialin_detail": jialin["detail"],
        "zhuyun_step": yun_step,
        "zhuyun_wuxing": zhu_yun_cur["wuxing"],
        "keyun_step": yun_step,
        "keyun_wuxing": ke_yun_cur["wuxing"],
    }
    # 12. 脏腑倾向标签（参数化，不给诊断）
    zangfu_tags = []
    # 岁运
    zangfu_tags.append({
        "source": "岁运", "wuxing": sy["wuxing"], "status": sy["status"],
        "tags": zangfu_tags_for_wuxing(sy["wuxing"]),
        "tendency": "本气易盛" if sy["status"] == "太过" else "本气易弱",
    })
    # 主气
    zangfu_tags.append({
        "source": "主气", "wuxing": zhu_qi["wuxing"],
        "tags": zangfu_tags_for_wuxing(zhu_qi["wuxing"]),
    })
    # 客气
    zangfu_tags.append({
        "source": "客气", "wuxing": ke_qi["wuxing"],
        "tags": zangfu_tags_for_wuxing(ke_qi["wuxing"]),
    })
    # 13. 经典出处
    rule_refs = [
        "素问·天元纪大论",
        "素问·五运行大论",
        "素问·六微旨大论",
        "素问·气交变大论",
        "素问·五常政大论",
        "素问·至真要大论",
        "素问·六元正纪大论",
    ]
    # 14. notes
    notes = (
        "本结果采用「大寒交运」起算六气与五运步位，年柱以「立春」分界（主流八字口径）。"
        "平气仅采用可确定性判定的「干德符（出生日干与岁运年干相同）」；齐化等需交司时刻、流派分歧大，未程序化。不同流派平气口径存在差异。"
        "节气使用寿星天文历近似公式，误差约 ±1 天，在节气当日附近出生者需结合精确天文时刻复核。"
    )
    if hour is None:
        notes += " 未提供出生小时，时柱为 null，子时与日柱交界处的判定可能略有差异。"
    notes += " 结果为客观干支运气推算，体质解读须结合经典原文与执业医师判断。"
    if place:
        notes += f" 注：真太阳时时差修正未做（出生地「{place}」仅作记录）。"
    # 15. 组装 JSON
    output = {
        "input": {
            "date_input": args_date,
            "calendar": calendar,
            "hour": hour,
            "gender": gender,
            "place": place,
        },
        "gregorian_date": solar.isoformat(),
        "lunar_date": {
            "year": lunar["year"],
            "month": lunar["month"],
            "day": lunar["day"],
            "is_leap": lunar["is_leap"],
            "month_name": lunar["month_name"],
            "day_name": lunar["day_name"],
            "year_ganzhi": lunar["year_ganzhi"],
            "shengxiao": lunar["shengxiao"],
        },
        "bazi": bazi_dict,
        "shengxiao": SHENGXIAO[year_zhi_idx],
        "solar_term": {
            "prev_jieqi": prev_name,
            "prev_jieqi_date": prev_jq.isoformat(),
            "next_jieqi": next_name,
            "next_jieqi_date": next_jq.isoformat(),
            "days_since_prev": (solar - prev_jq).days,
            "days_to_next": (next_jq - solar).days,
            "dahan_date": dahan_d.isoformat(),
            "days_to_dahan": days_to_dahan,
            "liucq_step": step,
            "liucq_step_start_jieqi": step_start,
            "liucq_step_end_jieqi": step_end,
        },
        "suiyun": {
            "wuxing": sy["wuxing"],
            "wuyin": sy["wuyin"],
            "status": "平气" if pq["pingqi"] else sy["status"],
            "raw_status": sy["status"],
            "pingqi": pq["pingqi"],
            "pingqi_type": pq.get("type"),
            "pingqi_reasons": pq["reasons"],
        },
        "liuqi": {
            "sitian": sitz["sitian"],
            "sitian_wuxing": sitz["sitian_wx"],
            "zaiquan": sitz["zaiquan"],
            "zaiquan_wuxing": sitz["zaiquan_wx"],
            "keqi_steps": sitz["keqi_steps"],
            "current_step": step,
            "zhuqi": zhu_qi["name"],
            "zhuqi_wuxing": zhu_qi["wuxing"],
            "keqi": ke_qi["name"],
            "keqi_wuxing": ke_qi["wuxing"],
            "kezhu_jialin": jialin["relation"],
            "kezhu_jialin_detail": jialin["detail"],
        },
        "yunbu": {
            "zhuyun": {
                "steps": [{"step": z["step"], "wuxing": z["wuxing"]} for z in zhu_yun_list],
                "current_step": yun_step,
                "current_wuxing": zhu_yun_cur["wuxing"],
            },
            "keyun": {
                "steps": [{"step": k["step"], "wuxing": k["wuxing"]} for k in ke_yun_list],
                "current_step": yun_step,
                "current_wuxing": ke_yun_cur["wuxing"],
                "based_on_suiyun": sy["wuxing"],
            },
        },
        "objective_predisposition": obj,
        "yunqi_geju": geju,
        "suiyun_pathomech": _suiyun_pathomech(sy["wuxing"], sy["status"], sitz["sitian"]),
        "zangfu_tendencies": zangfu_tags,
        "rule_refs": rule_refs,
        "notes": notes,
    }
    return output


def main():
    parser = argparse.ArgumentParser(description="五运六气推算（CLI）")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("calc", help="输入生日推算禀赋")
    p.add_argument("--date", required=True, help="日期 YYYY-M-D")
    p.add_argument("--calendar", default="gregorian", choices=["gregorian", "lunar"])
    p.add_argument("--hour", type=int, default=None, help="出生小时 0–23，可选")
    p.add_argument("--gender", default=None, help="性别，可选（男/女/其它），仅记录")
    p.add_argument("--place", default=None, help="出生地，仅记录；真太阳时修正未实现")
    q = sub.add_parser("suiqi", help="岁气模式：输入就诊/发病日期（缺省今天），算当年当下岁气背景，不需生日")
    q.add_argument("--date", default=None, help="日期 YYYY-M-D（缺省=今天）")
    q.add_argument("--calendar", default="gregorian", choices=["gregorian", "lunar"])
    args = parser.parse_args()
    if args.cmd == "calc":
        result = compute(args.date, args.calendar, args.hour, args.gender, args.place)
    elif args.cmd == "suiqi":
        result = suiqian(args.date, args.calendar)
    else:
        parser.print_help()
        sys.exit(4)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "error" in result:
        sys.exit(4)
    sys.exit(0)


if __name__ == "__main__":
    main()
