# -*- coding: utf-8 -*-
"""本地段落索引（data/<book>_index.json）。

发布版默认「纯本地运行」：tcm_clause 的 get/search/clause 只读随技能冻结的
本索引（纯 JSON，规避云盘挂载上 sqlite 单次 1~2.5s 的连接开销），默认不联网。
仅开发者维护底本时（--refresh 且 TCM_ALLOW_NETWORK=1）才由 build_index.py
预抓取并重新落盘；普通使用者无需也不会触发任何网络请求。

索引文件结构：
{
  "book": "shanghan", "built_at": "...", "item_count": N,
  "items": [
    {"book","volume","chapter","section","item_no","locator",
     "title","text","source_name","source_url","edition"}
  ]
}
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_cache = {}  # book -> {"items":[...], "built_at":...}


def index_path(book):
    return os.path.join(DATA_DIR, "%s_index.json" % book)


def has_index(book):
    return os.path.exists(index_path(book))


def load(book):
    """返回索引 dict（含 items），不存在返回 None。进程内缓存。"""
    if book in _cache:
        return _cache[book]
    p = index_path(book)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("items"):
        return None
    _cache[book] = data
    return data


def save(book, items, built_at):
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {"book": book, "built_at": built_at,
            "item_count": len(items), "items": items}
    tmp = index_path(book) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, index_path(book))
    _cache.pop(book, None)
    return data


# 九部核心典籍（运行时检索范围）。开源版只含公版古籍语料。
CORE_BOOKS = ["shanghan", "jinkui", "suwen", "lingshu", "bencaojing",
              "qianjin", "jufang", "jingfulvke", "yianan", "zhuhou"]

# 条级检索库（v3 起随包冻结，search 一跳定位用）
CLAUSE_INDEX = {
    "shanghan": ("shanghan_clauses.json", 300),   # 388 条，留出余量
    "jinkui": ("jinkui_clauses.json", 1000),      # 1227 段
}


def local_index_report(books=None):
    """本地索引完整性自检（离线健康检查，不发起任何网络请求）。

    返回 dict：
      ok           全部核心书索引可读且非空
      offline      恒 True（本检查不联网）
      books        每书 {"present","item_count","built_at"}
      clause_index 条级库 {"present","item_count"}
      missing      缺失/为空的书 id 列表
    """
    books = books or CORE_BOOKS
    report_books = {}
    missing = []
    for b in books:
        d = load(b)
        n = len(d["items"]) if d else 0
        present = bool(d) and n > 0
        report_books[b] = {
            "present": present,
            "item_count": n,
            "built_at": (d or {}).get("built_at"),
        }
        if not present:
            missing.append(b)

    clause_report = {}
    for b, (fname, min_n) in CLAUSE_INDEX.items():
        p = os.path.join(DATA_DIR, fname)
        n = 0
        try:
            with open(p, encoding="utf-8") as f:
                n = len(json.load(f).get("items", []))
        except Exception:
            n = 0
        clause_report[b] = {"present": n >= min_n, "item_count": n,
                            "file": fname}

    return {
        "ok": not missing and all(v["present"] for v in clause_report.values()),
        "offline": True,
        "books": report_books,
        "clause_index": clause_report,
        "missing": missing,
    }


# 典籍校勘夹注保留的符号（白名单说明用）；清洗在 tcm_common.strip_tags 完成，
# 正文里的"（一云…）""（……）"等中文圆括号夹注不是 HTML，本就不会被删。
