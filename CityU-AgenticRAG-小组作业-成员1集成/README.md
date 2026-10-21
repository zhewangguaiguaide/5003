# CityU 学生服务 Agentic RAG（小组作业）

## 成员①集成版当前入口（2026-10-12）

本目录已完成返工包合并、JSONL 接收及旧库集成。当前 `data/cityu_faq.db` 含 159 条活动 documents，历史 records 为原始采集层；成员③使用 `documents.active=1` 开发检索。当前交接只需阅读 [成员①②实施与成员③交接报告](docs/交接单_成员1与成员2实施_至成员3.md)；②返工看 [返工与补交清单](../交接文件_2026-10-12/01_给成员2_返工与补交清单.md)，详细证据集中在整理包附件。

```powershell
& .\.venv\Scripts\python.exe -m src.main --status
& .\.venv\Scripts\python.exe -m src.main --quality --quality-source documents
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
# 收到成员②完整修正版后，先保留原文件，再明确接收：
& .\.venv\Scripts\python.exe -m src.main --import-corpus '修正版完整语料.jsonl'
```

新建环境已按锁定依赖验收：20/20 版本匹配，pip check 通过，48/48 离线测试通过。重新建环境须使用 Python 3.12，再运行 `python -m venv .venv`、`.venv\Scripts\python.exe -m pip install -r requirements-lock.txt`；后续浏览器采集另行安装浏览器并验证网络路径。

JSONL 导入完整验证后通过事务同步快照；`column` 保存为 `column_name`，附带 `corpus_sha256/active/index_dirty`。旧文档若有 chunk 引用则停用保留，实际索引清理由成员③完成。相同快照重导不会把已建索引重新标脏。JSONL 接收审计在 `corpus_imports`，真实抓取审计仍在 `crawl_runs`。

**F1/F2 数据修复和 F3 浏览器验证仍由成员②完成。** 接收报告 `release_ready=false` 表示本次不授予封版；结构接收通过不能代替语义质检。

下文保留原采集说明。其中 `--migrate/--export` 仅适用于未接收 JSONL 的原始 records 库；集成快照库会拒绝这些旧操作，避免覆盖交付语料。`--quality` 默认为 records；接收库使用 `--quality --quality-source documents`，结果另存 `data/quality_documents.json`。

---


> 用 CityU 官网公开信息构建"校园 / 国际学生 / 新生服务"问答语料，并落地一套可维护的采集程序。
> **本目录是独立的小组作业工作区，与课程其他材料（课件、教材、Assignment）无关，请勿混放。**

## 一、项目定位

- **业务目标**：覆盖 8 大主题的学生服务 FAQ —— 申请、注册、签证、宿舍、学费、奖学金、图书馆、校历。
- **技术目标**：① RAG 语料采集（爬虫）；② 采集过程可维护（Harness + Loop 方法学）；③ 可行性 / 合规论证。
- **交付物**：可运行爬虫 + 标准化集成测试（eval）+ 开发指导文档 + 可行性研究报告。

## 二、目录结构

```
CityU-AgenticRAG-小组作业/
├── README.md                     ← 本文件（从这里开始看）
├── requirements.txt              ← 依赖
├── config.yaml                   ← 站点/主题清单、限速、存储路径
├── src/                          ← 爬虫程序
│   ├── storage.py                ← 幂等写入 + 已存在查询（+ MockStorage）
│   ├── parser.py                 ← HTML -> 结构化记录（清洗）
│   ├── fetcher.py                ← 限速 + 重试 + WAF 挑战页检测 + 适配器
│   ├── crawler.py                ← ColumnCrawler / DomainCrawler（栈式增量幂等）
│   ├── llm.py                    ← DeepSeek 客户端（Chat Completions + tools）
│   ├── websearch.py              ← 搜索后端适配器（bing / fake，可替换）
│   ├── agent.py                  ← web_search 工具 + function calling 循环
│   ├── config.py                 ← 配置读取
│   └── main.py                   ← CLI 入口
├── tests/
│   ├── mock_site.py              ← 离线 mock 站点
│   ├── test_standard.py          ← 爬虫标准化集成测试（12 个用例）
│   └── test_websearch.py         ← 联网搜索 eval（8 个用例，全离线）
├── docs/
│   ├── 选题说明.md                ← 选题说明（中英双版，含 Track 选择/论文参考/类似应用）
│   ├── 可行性研究.md              ← 爬取/法律/技术可行性 + 实用性 + 必要性
│   ├── 内容覆盖核查.md            ← 8 栏目实测：能爬到什么/细度/意外发现（含修复记录）
│   ├── Harness开发指导.md         ← 开发指导文档（Harness 三件套之一）
│   └── evidence/                 ← 证据：探针脚本、课外资料原文、抓取日志
└── data/                         ← 抓取产物（.db / .jsonl，已 gitignore）
```

## 三、快速开始

```bash
cd CityU-AgenticRAG-小组作业-成员1集成
py -3.12 -m venv .venv && source .venv/Scripts/activate   # Windows bash，接收方自行重建
pip install -r requirements.txt
scrapling install                                          # 下载无头浏览器（约 300MB，仅 live 抓取需要）

python -m unittest discover -s tests                       # 跑 eval（离线，秒级）
python -m src.main --dry-run                               # 看抓取计划（不联网）
python -m src.main --live --mode fake                      # 离线跑通全流程（mock 站点）
python -m src.main --live --column fees                    # 真实抓取某一栏目
python -m src.main --smoke https://www.cityu.edu.hk/admo/faq   # 单页连通性验证
python -m src.main --status                                # 查看库内统计
python -m src.main --quality                               # 13 个种子覆盖核查，生成 data/quality_report.json
python -m src.main --migrate                               # 合格语料同步至 documents
python -m src.main --export data/corpus.jsonl              # 去重+规范化后导出 RAG 语料（JSONL）
python -m src.main --live --full --repair-loops 2          # 八栏目补齐：所有种子优先，已有 URL 不终止

export DEEPSEEK_API_KEY=<your-key>                         # 联网问答需要（Key 走环境变量，不入仓）
python -m src.main --ask "非本地本科生学费是多少？"          # DeepSeek + web_search 联网问答
```

## 四、爬虫设计要点（详见 `docs/Harness开发指导.md`）

1. **列表页 / 详情页模型 + 栈（LIFO）**：列表页 URL 先入栈不写库，命中"已在库中"即停止扫描；
   出栈时才抓详情入库 → **从新到旧入栈、从旧到新入库**，天然增量 + 幂等。
2. **礼貌抓取**：请求间随机延迟 2-3s（`config.yaml` 可调）、失败重试、连续失败即停。
3. **WAF 挑战页检测**：cityu.edu.hk 全站在 Imperva Incapsula 后，被拦时返回**假 200**（~850B 挑战页），
   判据是"内容极短 **且** 含 `_Incapsula_Resource`/`incident_id`"。
4. **清洗即抓取的一部分**：正文、标题、日期、`image_urls`、`file_urls`、`error` 分字段入库；
   自动排除登录/SSO/员工名录等非服务页（`DEFAULT_EXCLUDE` + 栏目 `exclude`），
   正文短于 `min_content_len`（默认 300 字）的空壳页不入库。
5. **可替换适配器**：`stealthy`（无头浏览器，实测可过 WAF）/ `http`（简单站点）/ `fake`（离线测试）。

## 五、可行性结论摘要（详见 `docs/可行性研究.md`）

| 维度 | 结论 |
|---|---|
| 爬取可行性 | ✅ **已实测打通**：纯 HTTP 全被拦；`scrapling StealthyFetcher` 可稳定拿到真实正文（`/admo/faq` 11 万字符验证通过），每页 10-30s |
| 法律可行性 | ✅ 有条件：课堂内部使用 + 署名 = 低风险（香港 fair dealing）；**公开部署/全文再分发 = 中高风险**，不建议 |
| 技术可行性 | ✅ 40-160 页一轮约 15-60 分钟；站外替代源（libguides、学院子站）可直连补充 |
| 实用性 | ✅ 高：8 主题正是新生/国际生咨询痛点，信息分散在 6+ 部门子站 |
| 必要性 | 课程项目 ✅ 合适；作为真实对外产品 ⚠️ 需校方授权（校方 FAQ 本身已完善） |

## 六、验证记录（2026-09-25/26 实测）

| 验证项 | 结果 |
|---|---|
| 标准化集成测试 | `python -m unittest discover -s tests` → **20 项全过**（12 项爬虫 eval + 8 项联网搜索 eval），全程离线 |
| 离线全流程 | `--live --mode fake` → mock 站点 2 列表页 / 6 详情页，新增 6 条，导出正常 |
| 单页真实抓取 | `--smoke https://www.cityu.edu.hk/admo/faq` → 成功拿到标题 `FAQ \| CityUHK Admission` 与完整正文（WAF 已绕过） |
| 真实栏目抓取 | `--live --column fees --max-pages 6` → 7 请求 / 0 挑战页 / 0 错误，新增 3 条、空壳跳过 3 条，1 分 4 秒完成，已导出 `data/corpus_sample.jsonl` |
| 入库质量 | 记录含正文（2400-3600 字）、附件（2-4 个 PDF）、图片（12-28 张）、发布日期（含真实页内日期 2014-06-01） |
| 联网问答（live） | `--ask "非本地本科生学费"` → DeepSeek 自主发起 9 次 web_search、5 轮 LLM 调用，结果不可靠时明确回答“未查到”不编造（行为正确；Bing 免费结果页质量有限，见“已知限制”） |
| 栏目覆盖核查 | 13 个种子页全通（0 挑战页 0 失败，3 分钟）；7/8 栏目细度直接达标，scholarship 壳页问题已修复（详见 `docs/内容覆盖核查.md`） |

## 七、联网搜索（DeepSeek function calling）

**官方事实核查（2026-09-26，api-docs.deepseek.com）**：DeepSeek API **没有服务端联网搜索**；
Responses API 里的 `web_search` / `file_search` 等内置工具会被**静默忽略**（见官方
`guides/responses_api` 兼容性表）。因此本功能的官方正解 = **客户端 function calling**：

1. `src/agent.py` 定义 `web_search` 工具 schema，随对话发给 DeepSeek；
2. 模型需要搜索时返回 `tool_calls` → 本地 `src/websearch.py` 执行真实搜索 → 结果以 tool 消息回灌；
3. 模型综合结果生成答案并标注来源 URL；超过轮数上限（默认 4）自动收尾。

搜索后端可替换（`config.yaml` 的 `websearch.provider`）：`bing`（curl_cffi 抓结果页，大陆可直连，默认）/ `fake`（离线测试）。

## 八、合规红线（小组必须遵守）

1. **仅用于课程项目、本地演示**，不公开部署、不再分发正文全文。
2. **限速 ≥2s/页**，只抓 `config.yaml` 清单内的页面。
3. 交付物与报告中标注：`Source: City University of Hong Kong website (cityu.edu.hk), for coursework demo only`。
4. 入库前清洗个人资料（人名/邮箱/电话/照片）。
5. 优先考虑向校方部门申请授权（以 CityU 学生身份做本校课程项目，通常最容易获批）。
6. 不主动绕过安全防护以外的用途；抓取内容仅作检索语料，回答以改写+摘要形式呈现并附来源 URL。

## 九、RAG 接入（下一步）

交接包不得包含 `.venv*`：虚拟环境含本机路径，无法跨机器移植。
接收方安装 Python 3.12 后自行建环境；`requirements.txt` 通过
`requirements-lock.txt` 锁定依赖版本，浏览器另行执行 `scrapling install`。
全量模式审计保存在 `data/crawl_audit.jsonl`，失败记录留在 `records.error`，
导出时排除失败/空白/导航薄页；`crawl_runs` 保存栏目级统计。

`--export data/corpus.jsonl` 产出的记录字段（`url/title/source/content/date/crawled_at/topic/column/academic_year`）
可直接切块（chunk）后向量化；建议：
- 元数据保留 `url + academic_year + crawled_at`，用于时效性标注与引用溯源；
- 按 `topic` 建 agentic router（如"校历查询""费用查询"分工具）；
- 导出阶段按规范化 URL + 正文 SHA-256 指纹去重（新旧 URL 体系并存，同学期内容可能有多个版本页面）。

## 十、分工建议（小组作业）

> 6 人具体排班、接口契约、交接规范与里程碑见 **`docs/分工与交接方案.md`**。

| 角色 | 任务 |
|---|---|
| 数据采集 | 维护 `config.yaml` 主题清单、跑 live 抓取、处理失败页 |
| 程序维护 | Harness/Loop：修 `src/`、扩 eval 评估项、跑回归 |
| 语料与 RAG | 清洗去重、切块向量化、agentic 路由与引用 |
| 合规与文档 | `docs/`：可行性论证、合规声明、答辩材料 |

## 十一、已知限制

- 部分页面为 JS 渲染或资源挂起，`disable_resources=True` 已处理典型情况，个别页面仍可能超时。
- FAQ 页面多无发布日期，`date` 会回落为抓取时间；时效性判断依赖 `crawled_at`。
- `r.jina.ai`、`web.archive.org` 在当前网络环境不可达（已记录在可行性报告）。
- Bing 免费结果页对冷门查询会返回不相关结果（实测出现游戏外设条目）；agent 会拒答而非编造，
  但正式演示建议换付费搜索 API（Tavily / Bing Web Search API），适配器接口已留好。


## GitHub公开副本说明（2026-10-21）

本仓库提供源码、离线测试、交接文档和排期。组员登记表、网页全文语料、数据库、抓取日志、虚拟环境及历史压缩包未上传。前文159篇数据和48项测试等数字属于历史验收记录，不能当作新克隆仓库已有数据。

接收者先建立自己的Python 3.12环境并安装锁定依赖，可运行离线测试。需要重现真实检索实验时，请由②通过小组内部渠道提供完整快照，①按交接清单验收后导入；API密钥仅在本机配置环境变量。
