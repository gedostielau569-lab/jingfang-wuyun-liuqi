# -*- coding: utf-8 -*-
"""经方辨证引擎 · 公共抓取/解析/缓存模块

只依赖 Python 标准库。职责：
- 低频、带浏览器 UA 的 HTTP GET（gzip、超时、重试1次）
- URL 级 sqlite 缓存（记录 ETag/Last-Modified/fetched_at，--refresh 可强刷）
- HTML 工具：编码探测、去标签、BeginContent 正文抽取、段落切分
"""
import gzip
import html as ihtml
import io
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip",
}
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 15
SLEEP_BETWEEN = 0.6  # 串行低频，尊重站点

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_DB = os.path.join(DATA_DIR, "cache.db")
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 缓存默认7天

_last_request_at = [0.0]


# ---------------------------------------------------------------------------
# 离线闸（offline gate）
#
# 发布版默认「纯本地运行」：检索只读随技能冻结的 data/ 索引，绝不外呼。
# 仅当显式 --refresh 且设置环境变量 TCM_ALLOW_NETWORK=1 时才联网更新底本
# （开发者维护底本用，不是使用者的运行前提）。任何外呼都收口在
# http_get / health_probe，本闸保证默认情况下零网络请求、零用户数据外发。
# ---------------------------------------------------------------------------
def network_allowed():
    return os.environ.get("TCM_ALLOW_NETWORK", "") == "1"


class OfflineError(RuntimeError):
    """离线模式下拒绝联网。调用方应直接回退本地索引或明确告知未核对。"""


def now_cn():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat(timespec="seconds")


def _polite():
    wait = SLEEP_BETWEEN - (time.time() - _last_request_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_at[0] = time.time()


def _open_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS page_cache(
        url TEXT PRIMARY KEY,
        status INTEGER,
        content BLOB,
        encoding TEXT,
        etag TEXT,
        last_modified TEXT,
        fetched_at TEXT
    )""")
    conn.commit()
    return conn


def _decode(raw, encoding, content_type_header):
    if encoding:
        candidates = [encoding]
    else:
        candidates = []
    ct = (content_type_header or "").lower()
    m = re.search(r"charset=([\w\-]+)", ct)
    if m:
        candidates.append(m.group(1))
    head = raw[:2000].decode("ascii", errors="ignore")
    m = re.search(r'charset=["\']?([\w\-]+)', head, re.I)
    if m:
        candidates.append(m.group(1))
    candidates += ["gb18030", "utf-8"]
    seen = set()
    for enc in candidates:
        enc = enc.lower().replace("gb2312", "gb18030").replace("gbk", "gb18030")
        if enc in seen:
            continue
        seen.add(enc)
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore"), "utf-8"


def http_get(url, refresh=False, use_cache=True, force_encoding=None):
    """返回 (text, encoding, fetched_at or None, error or None)。
    refresh=True 强制走网络；网络失败时回退缓存（即使过期）。
    """
    conn = _open_db()
    row = None
    if use_cache and not refresh:
        cur = conn.execute(
            "SELECT content,encoding,fetched_at FROM page_cache WHERE url=?", (url,))
        row = cur.fetchone()
        if row:
            fetched_at = row[2]
            fresh = False
            try:
                ts = datetime.fromisoformat(fetched_at).timestamp()
                fresh = (time.time() - ts) < CACHE_TTL_SECONDS
            except Exception:
                pass
            if fresh:
                conn.close()
                return row[0].decode("utf-8", errors="ignore"), row[1], fetched_at, None

    # 离线闸：默认纯本地，未显式放行则绝不发起网络请求（用户数据零外发）
    if not network_allowed():
        conn.close()
        if row:  # 本地有（哪怕过期）缓存时回退缓存
            return row[0].decode("utf-8", errors="ignore"), row[1], row[2], None
        return None, None, None, "离线模式：未联网，且本地无该页缓存（默认不发起网络请求）"

    _polite()
    req = urllib.request.Request(url, headers=dict(HEADERS))
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT + READ_TIMEOUT) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            text, enc = _decode(raw, force_encoding, resp.headers.get("Content-Type"))
            fetched = now_cn()
            if use_cache:
                conn.execute(
                    "INSERT OR REPLACE INTO page_cache VALUES(?,?,?,?,?,?,?)",
                    (url, resp.status, text.encode("utf-8"), enc,
                     resp.headers.get("ETag"), resp.headers.get("Last-Modified"), fetched))
                conn.commit()
            conn.close()
            return text, enc, fetched, None
    except Exception as e:  # 含 URLError/timeout/HTTPError
        # 重试一次
        time.sleep(1.0)
        try:
            _polite()
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=dict(HEADERS)),
                    timeout=CONNECT_TIMEOUT + READ_TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                text, enc = _decode(raw, force_encoding,
                                    resp.headers.get("Content-Type"))
                fetched = now_cn()
                if use_cache:
                    conn.execute(
                        "INSERT OR REPLACE INTO page_cache VALUES(?,?,?,?,?,?,?)",
                        (url, resp.status, text.encode("utf-8"), enc,
                         resp.headers.get("ETag"),
                         resp.headers.get("Last-Modified"), fetched))
                    conn.commit()
                conn.close()
                return text, enc, fetched, None
        except Exception as e2:
            if row:  # 网络失败，退回（即使过期的）缓存
                conn.close()
                return row[0].decode("utf-8", errors="ignore"), row[1], row[2], None
            conn.close()
            return None, None, None, "抓取失败: %s（重试仍失败: %s）" % (e, e2)


def _cache_bulk():
    """一次性读入全部缓存 {url: (text, encoding, fetched_at)}。

    云盘挂载上 sqlite 单条查询约 0.2~2.5s，批量构建索引时用本函数一次读全表。
    """
    conn = _open_db()
    out = {}
    for url, content, enc, fetched in conn.execute(
            "SELECT url,content,encoding,fetched_at FROM page_cache"):
        out[url] = (content.decode("utf-8", errors="ignore"), enc, fetched)
    conn.close()
    return out


def health_probe(url, force_encoding=None):
    """健康探测：不走缓存，返回 (healthy:bool, latency_ms:int|None)。

    离线模式（默认）下不发起任何网络请求，直接返回 (False, None)；
    发布版的"健康"以本地索引完整性自检为准（见 local_store.local_index_report），
    不再以源站可达性为依据。
    """
    if not network_allowed():
        return False, None
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=dict(HEADERS))
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
            raw = resp.read(4096)
            ok = resp.status == 200 and len(raw) >= 0
            return ok, int((time.time() - t0) * 1000)
    except Exception:
        return False, None


# ---------------- HTML 工具 ----------------

def strip_tags(fragment):
    """去脚本/样式/HTML注释/残留标签，反转义实体，保留文本。<br>视为换行。

    注意：100md 正文结尾标记 <!--DuYiHuaAdd EndContent--> 会被 BeginContent
    正则切成两半，残留未闭合注释头 ``<!--DuYiHuaAdd``；<[^>]+> 无法匹配它
    （无 >），必须显式剥离注释，包括未闭合的注释头。
    """
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", fragment)
    # 完整 HTML 注释（含跨行）
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    # 被截断的未闭合注释头/尾（如 <!--DuYiHuaAdd 或注释尾 -->）
    s = re.sub(r"<!--[^\n>]*$", "", s, flags=re.M)
    s = s.replace("-->", "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</p\s*>", "\n", s)
    s = re.sub(r"(?is)</div\s*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = ihtml.unescape(s)
    return s


def extract_begin_content(html_text):
    """抽取 100md 系页面 <!--DuYiHuaAdd BeginContent--> ... EndContent 之间的原始 HTML。"""
    m = re.search(r"BeginContent-->(.*?)EndContent", html_text, re.S)
    if not m:
        return None
    frag = m.group(1)
    frag = re.sub(r"(?is)<script[^>]*>.*?</script>", "", frag)
    # 剥掉可能残留的注释碎片（截断的标记），交给 strip_tags 双保险
    frag = re.sub(r"(?is)<!--.*?-->", "", frag)
    frag = re.sub(r"<!--[^\n>]*$", "", frag, flags=re.M)
    return frag


def split_br_paragraphs(fragment):
    """把正文 HTML 片段按 <br><br> / 空行 切成文本段列表。
    返回 [(raw_text, is_strong_title)]。
    """
    # 先把 <strong>x</strong> 段标记出来
    blocks = []
    # 在 <br><br> 处切
    parts = re.split(r"(?i)<br\s*/?>\s*<br\s*/?>", fragment)
    for p in parts:
        pc = p.replace("&nbsp;", " ").strip()
        sm = re.match(r"(?is)<strong[^>]*>(.*?)</strong>\s*$", pc)
        if sm:
            title = clean_text(strip_tags(sm.group(1)))
            if title:
                blocks.append((title, True))
            continue
        # 段首即以 <strong> 起头、后接正文（如方剂名），也作为标题块
        sm2 = re.match(r"(?is)<strong[^>]*>(.*?)</strong>(.*)$", pc)
        if sm2 and len(clean_text(strip_tags(sm2.group(2)))) < 2:
            title = clean_text(strip_tags(sm2.group(1)))
            if title:
                blocks.append((title, True))
            continue
        txt = clean_text(strip_tags(p))
        if txt:
            blocks.append((txt, False))
    return blocks


def clean_text(s):
    s = s.replace("\xa0", " ")
    s = s.replace("　", " ")
    # 站点噪音：原文中不会出现 '#'（100md 有 "复恐?##" 之类的缺字/截断标记）
    s = re.sub(r"#+", "", s)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def normalize(s):
    """归一化用于比对：去标点空白、繁简差异不处理（源都是简体）。"""
    return re.sub(r"[\s，。、；：？！,.;:?！…·“”\"'‘’（）()【】《》〈〉\-—~～]",
                  "", s or "")
