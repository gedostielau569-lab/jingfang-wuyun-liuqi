# 经方五运六气（Classical Formulas · Five Movements and Six Qi）

> *Jīngfāng Wǔyùn Liùqì* ｜ 又名「经方·五运六气辨证」｜ Coze Skill 内部标识：`jingfang-bianzheng`

面向**执业医师 / 中医专业用户**的经方临床辨证参考技能（Coze Skill）。
> 以宋本《伤寒论》《金匮要略方论》为核心，兼采九部中医经典，**纯本地检索原文接地**，
> 凡引用必标注【典籍·篇目/卷次·条文序号】，禁止凭记忆背条文；提供生日/发病日期时可加做五运六气客观推算。

## 这是什么

一个运行在 Coze Agent 上的「技能（Skill）」目录。装入后，Agent 就拥有一套可溯源、防幻觉的经方辨证流程：

- **辨证三模块**：病机分析 → 经方选择与方义加减 → 用药禁忌，逐条引经典原文。
- **双层运气**：①不依赖生日的「当下岁气」模式（岁运、司天在泉、六气步位客主加临、运气同化格局）；
  ②据生日的禀赋倾向；五运太过/不及十格病机由离线库直接给出并附《素问·五运行大论》原文。
- **纯本地、零外呼**：随技能冻结本地索引，默认断网运行，不上传任何病例；构建/抓取脚本不随包分发。

## 证据来源（仅九部典籍）

1. 宋本《伤寒论》（赵开美翻刻宋本，398 条体系）
2. 《金匮要略方论》
3. 《黄帝内经·素问》　4. 《黄帝内经·灵枢》（素问、灵枢合称《内经》，计为一部）
5. 《神农本草经》　6. 《备急千金要方》　7. 《太平惠民和剂局方》
8. 《傅青主女科》　9. 《古今医案按》　10. 《诸病源候论》

> 以上均为**公有领域古籍**，按通行整理本结构化，版本随条文标注。
> 辨证三模块**只允许引用这九部典籍**；运气参考只接地于《素问》七篇大论与随包离线病机库。

## 目录结构

```
jingfang-bianzheng/
├── SKILL.md                 # 技能主说明（角色、辨证流程、引用与合规规范）
├── references/              # 推算口径、规则、自测说明
└── scripts/
    ├── tcm_common.py        # 公共工具（默认封网，TCM_ALLOW_NETWORK=1 仅开发者刷新底本）
    ├── local_store.py       # 本地索引读取
    ├── tcm_clause.py        # 九经统一检索内核（books/get/search/clause）
    ├── shanghan_logic.py    # 伤寒 398 条编号对齐
    ├── yunqi.py             # 五运六气推算引擎（calc/suiqi）
    ├── yunqi_pathomech.py   # 五运病机离线库（十格）
    ├── *_selftest.py        # 各模块金标准自测
    └── data/                # 随包冻结的九经本地索引（公有领域）
```

## 快速验证（无需联网）

```bash
cd scripts
python3 selftest.py                  # 九经检索/编号/隔离自测，并重生成 SELFTEST.md
python3 yunqi_selftest.py            # 运气 155 项断言
python3 yunqi_pathomech_selftest.py  # 病机库约 62 项断言

# 日常检索示例
python3 tcm_clause.py search --book shanghan --query "桂枝汤"
python3 tcm_clause.py clause --book jinkui --item 1
python3 yunqi.py suiqi --date 2026-10-26
```

## 如何装入 Coze

1. 将本目录整体打包（保持根目录名 `jingfang-bianzheng/`，内含 `SKILL.md`）。
2. 在 Coze「技能 / 我的技能」中以 ZIP 导入为草稿，或放置到 Agent 的技能目录后加载。
3. Agent 命中经方辨证类请求时会自动读取 `SKILL.md` 并按其流程调用脚本。

```bash
# 打包示例（在仓库上级目录执行）
zip -r jingfang-bianzheng.zip jingfang-bianzheng \
  -x '*/__pycache__/*' -x '*/.git/*'
```

## 免责声明（重要）

本项目输出**仅供执业医师临床思路参考**，不构成诊疗建议、不构成处方，不面向患者作通俗科普，
**不替代医师面诊与四诊辨证**。五运六气仅为传统医学的气化背景/禀赋倾向参考，不构成命运判断，
更不得据此直接定经方、定剂量；与真实四诊冲突时一律以四诊为准。经典原文不同版本间可能存在异文，
关键条文应以校勘纸本复核。使用本项目造成的任何后果由使用者自行承担。

## 版权与许可

- **代码与文档**：[MIT License](./LICENSE)。
- **古籍语料（`scripts/data/`）**：公有领域内容，仅供学习与临床参考。
- 本仓库**不包含**任何第三方现代出版物的受版权保护语料；开发者内部研究用的 OCR 旁参库
  因版权原因不分发，运行时也不依赖它。

## 在线试用

本技能同时发布在 Coze 技能平台「虾评」（试用版，免费）：
<https://xiaping.coze.com/skill/0a3930d9-832c-4515-a45b-1c08cecb99b2>

如果你是执业医师、也在用 Coze，欢迎下载后留下**真实评测**——这能帮助它通过平台转正、被更多同行检索到。
