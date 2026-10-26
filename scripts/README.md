# tcm_clause 脚本说明（九部十书中医经典检索）

仅依赖 Python 3.13 标准库，无需安装第三方包。

## 1. 命令一览

```bash
cd scripts

# 健康探测：列出十书 + 各源连通状态（会触网）
python3 tcm_clause.py books

# 按定位取原文（优先本地索引，秒回；--refresh 强制联网）
python3 tcm_clause.py get  --book shanghan --locator "辨太阳病脉证并治法上第五"
python3 tcm_clause.py get  --book bencaojing --locator "人参"
python3 tcm_clause.py get  --book zhuhou --locator "风癔候"

# 全文关键词检索（标题权重×3，含子串/异文模糊匹配）
python3 tcm_clause.py search --book qianjin --query "独活寄生汤" --limit 5
python3 tcm_clause.py search --book shanghan --query "桂枝汤"

# 条级检索：伤寒直接带398条号、金匮带"内N"内部段序，一跳定位，省去先search再clause
# --brief 只回 条号/locator/confidence + 30余字 preview，定位阶段显著省 token
python3 tcm_clause.py search --book shanghan --query "无汗而喘 麻黄汤" --brief
python3 tcm_clause.py search --book jinkui  --query "咽中如有炙脔"

# 伤寒第 N 条（1-398，运行时首句锚点+指纹动态核验，不达标严格降级）
python3 tcm_clause.py clause --no 12
python3 tcm_clause.py clause --no 100
```

> 条级库由 `build_clause_items.py` 离线生成（不联网）：`data/shanghan_clauses.json`
> （398 中可可靠定位的 high/medium 条全文，与 clause 同一分级口径）、
> `data/jinkui_clauses.json`（25 篇按自然段切出的 1227 段，序号为内部段序）。
> search 命中条级库优先；无命中回退篇/章索引；仍无再按 `--refresh` 联网兜底。


### 退出码契约

| 退出码 | 含义 |
|---|---|
| 0 | 成功（有结果） |
| 2 | 无结果 / clause 条号越界（1-398 之外） |
| 3 | 抓取/解析失败（联网失败且本地索引也无兜底） |
| 4 | 参数错误（未知 book、缺参数、argparse 校验失败） |

所有输出均为合法 JSON（`ok / book / locator / title / text / source_name /
source_url / confidence / note / fetched_at / error`），不向用户抛裸
traceback；任何内部异常都会被包成 JSON 错误对象。

### confidence 语义

- `high`：原文来自可靠来源且定位精确；伤寒 clause 表示首句锚点 +
  索引指纹运行时核验**双双通过**。
- `medium`：异文模糊命中 / 内部序（医案按卷内序号无通行权威编号）/
  主源未命中走备源。
- `low`：伤寒条号**未通过动态核验**，此时 `item_no=null`、
  `note="条文序号待核实…"`、并给 `candidates`（同篇候选条首句）供人工核对。
  **宁可 low，绝不把不确定的条号标高置信。**

## 2. 构建本地索引（一次性长任务）

```bash
python3 build_index.py --prefetch
```

- 先串行、低频（请求间隔约 0.6s，见 `tcm_common.SLEEP_BETWEEN`）、带浏览器
  UA 把十书的目录页与正文页全部抓进 sqlite 缓存 `data/cache.db`，
  尊重 robots（100md 允许缓存；中医宝典 Disallow 仅对其搜索页）。
- 再从缓存离线解析，生成：
  - `data/shanghan_398.json`：伤寒 398 条锚点核实索引（clause 字段 1..398
    完整；该文件 verified 为页面锚点覆盖率旧统计，仅供构建用，不等于运行时分级）。
  - `data/shanghan_clauses.json` / `data/jinkui_clauses.json`：由
    `build_clause_items.py` 从本地冻结索引**离线**生成的条级检索库（伤寒可有序定位
    388 条：anchor_clause=high 310 / variant_clause=medium 78，low 10 条不收录；
    金匮 1227 段 local_internal=medium）。`search` 优先查它，一跳返回条号+正文。
  - `data/jinkui_internal.json`、`data/yianan_internal.json`：内部序。
  - `data/<book>_index.json`：十书段落索引（字段
    book/volume/chapter/section/item_no/locator/title/text/
    source_name/source_url/edition）。
  - `data/shanghan_pages.json`：伤寒 14 篇页 blocks，clause 热路径直接读，
    不再碰慢 sqlite。
- 只有新增/缓存缺失的页面才会发请求，已缓存页秒过；中断后重跑会续抓。
- 不加 `--prefetch` 时只重建索引（纯离线，约 15s）。

## 3. 运行时取数顺序（发布版纯本地、零外呼）

> **离线闸**：`tcm_common.network_allowed()` 仅在环境变量 `TCM_ALLOW_NETWORK=1`
> 时放行网络；默认（含使用者运行时）为纯本地，`http_get`/`health_probe` 一律不发
> 起请求（strace 实测对外 connect=0），病例与关键词零外发。

1. `get` / `search` / `clause` **只读本地冻结 JSON 索引**（单次命令
   0.3–1.1s；本机云盘挂载下 sqlite 单查询约 0.27s，是改造前超时的主因，
   JSON 热路径已完全绕开 sqlite）。
2. 条级库（伤寒 398/金匮段）→ 篇/章索引，全部离线命中。
3. 仅开发者维护底本时设 `TCM_ALLOW_NETWORK=1` 并加 `--refresh` 才联网抓取，
   命中后写回 sqlite；该路径对使用者不可达。
4. `books` 默认输出本地索引完整性自检（每书条目数、built_at、条级库状态），
   不再探测外部源站。

## 4. 各源选择器 / 编码 / 坑

| 源 | 编码 | 选择器要点 | 坑 |
|---|---|---|---|
| book.100md.com（伤寒/千金/局方/医案按/诸病/本草/金匮/内经部分） | **GB18030** | 正文切片标记 `BeginContent-->` … `EndContent`；段落靠 `<p>`/`<strong>`/`<br>` | 每篇页尾有被切断的 HTML 注释 `<!--DuYiHuaAdd`，旧清洗会把它留在末条正文；已在统一抽取层剥离。卷页内 strong 是方名/候名，千金按它切细段 |
| guoxuedashi.com（国学大师：金匮、本草经药页、诸病70卷安禾本） | UTF-8 | 目录/正文在缓存样页结构内 | 局方该站为 JS 渲染、结构不同，未采用；诸病安禾本 70 卷用于补 100md 仅有的卷5–34 |
| huangdineijing.org（素问/灵枢主源） | UTF-8 | `<article class="markdown book-article">`，h1 为篇名，h2 分篇；`【原文】…【白话参考译文】` | 只取"原文"段，遇 `<h2>白话参考译文` 整体截断，杜绝译文混入 |
| zhongyibaodian.com（傅青主女科） | UTF-8 | 卷→门→症三级，锚点定位症块 | 目录门名不能当 section，section 必须是症名（如"白带下"） |
| qihuang.vip（岐黄：诸病 1729 候，可选备源） | UTF-8 | `book-188.html` 目录，`content-*.html` 一候一页 | 约 1740 请求、17 分钟以上；当前双源缓存（1687 候）已满足 ≤20s，未默认启用 |

文本清洗（`tcm_common.clean_text`，对所有来源生效）：剥离全部 HTML
注释（含未闭合注释头）、script/style、标签、`###/##` 残留、HTML 实体、
控制字符，合并空白；**保留**典籍正文里本就有的校勘夹注（"（一云…）"
"（赵本有…）"）。

## 5. 回归测试

```bash
python3 selftest.py        # 自动跑 books / 十书各 get+search / clause 1,12,100,398
                           # 结果写入 SELFTEST.md（含耗时、来源、节选）
```

也可手工验证退出码：

```bash
python3 tcm_clause.py search --book shanghan --query zzzqqw ; echo $?   # 2
python3 tcm_clause.py get    --book notabook --locator x ; echo $?      # 4
python3 tcm_clause.py clause --no 400 ; echo $?                          # 2
```

## 6. 文件

- `tcm_clause.py`：CLI 入口（books/get/search/clause）。
- `tcm_common.py`：http/缓存（sqlite）、GB18030 解码、统一文本清洗。
- `local_store.py`：本地 JSON 索引读写。
- `sources_100md.py / sources_gxds.py / sources_hdnj.py /
  sources_zybd.py / sources_zhuhou_gxds.py`：各站适配器。
- `shanghan_logic.py`：伤寒候选条切分、398 锚点对齐与指纹核验。
- `build_index.py`：`--prefetch` 预抓取 + 索引构建。
- `selftest.py`：回归测试，生成 `SELFTEST.md`。
- `data/`：sqlite 缓存、398/内部序索引、十书段落索引、伤寒篇页。

## 7. 已知限制

- 100md《太平惠民和剂局方》源站正文缺个别名方条文（如二陈汤、藿香正气散
  目录错链到 07_01.htm，该页无方），本地索引如实反映源站，未杜撰补齐。
- 伤寒 398 三态定位结果为 high 310 / medium 78 / low 10：low 条（22、62、84–87、
  129、252、253、339）为本地源真缺失或多短条并入他段，只给同篇候选与权威基准首句，
  不给 item_no；medium 条为版本异文（跌/趺、鞕/硬、以后/已后等），条号可定、正文以本地宋本为准。
- `books` 仍做实时源连通探测（约 30-40s），属预期；get/search/clause
  不触网时均在 1.1s 内。

## 8. 五运六气（仅服务 SKILL.md 第 6 节）

- `yunqi.py`：干支运气客观推算，两个模式。
  - 出生禀赋：`python3 yunqi.py calc --date YYYY-M-D [--calendar gregorian|lunar] [--hour 0-23] [--gender] [--place]`；
  - 发病/就诊岁气（不依赖生日）：`python3 yunqi.py suiqi [--date YYYY-M-D] [--hour 0-23]`——给气象年岁运、司天在泉、
    当下六气步位与客主加临顺逆、运气同化格局（天符/岁会/太乙天符/同天符/同岁会）。
  口径见 `../references/yunqi_rules.md`，自测 `python3 yunqi_selftest.py`（155 项金标准，含六十甲子格局遍历）。
- 禁止手算排干支；本脚本只给客观干支/岁运/司天在泉/主客气/步位/格局。
- `yunqi_pathomech.py` + `data/yunqi_pathomech.json`：第三层**岁运病机离线库**（纯本地、不联网）。
  - 固化五运太过/不及共 10 格，字段 `流行之气/受邪脏腑/经典病候/甚则·脉绝·复气/上临/星纪/原文 quote/locator`，
    `quote` 逐字抽自随技能冻结的本地《素问·五运行大论》（`local_pian/high`），自测逐字回核原文防幻觉。
  - `pathomech_for(五行, 太过|不及, 当年司天)` 返回结构化推理链；上临变局须司天相符才置 active。
  - **仅覆盖五运十格**：六气司天在泉病候、病机十九条、胜复郁发、岁运治则方药本地节选未收全，脚本不出，
    仍走 `tcm_clause search --book suwen` 接地，命不中不写。
  - 独立入口 `python3 yunqi_pathomech.py --wx 水 --status 太过 [--sitian 太阳寒水]`；
    自测 `python3 yunqi_pathomech_selftest.py`（约 62 项：十格齐全/引文逐字核原文/受邪五行/上临校验/平气不套库）。
  - 已随 `calc`/`suiqi` 的 `suiyun_pathomech` 字段输出。

## 9. 开源版语料边界

本仓库随包分发的语料**全部来自公有领域古籍**，辨证三模块只引用九部典籍，五运六气参考只接地于
《素问》七篇大论原文与 `data/yunqi_pathomech.json` 离线病机库。

开发者在内部研究阶段曾为一部**近现代影印古籍**建立独立 OCR 旁参库（与九经物理隔离、
不注册进 `tcm_clause.BOOK_META`）。因该版本受著作权保护，**该 OCR 语料、其构建器与检索器均不随
本仓库分发，运行时也不依赖它们**；使用者无须、也不应自行补入此类受版权保护的全文。
