# CityU Agentic RAG · DSC5003

面向学生服务FAQ的课程项目。仓库根目录是唯一运行目录，沿用成员①②已集成的最大可运行集合：采集、清洗导出、SQLite存储、完整快照接收、离线测试及联网搜索Agent雏形。

**基础向量检索及构建源码已上传，完整自有语料RAG与正式验收仍待完成。** 已有`src/retriever.py`、`scripts/build_wsb_index.py`及历史补交脚本；实际模型为`intfloat/multilingual-e5-small`。源码交付不等于真实运行或下游接收，依赖/模型准备、版本绑定、切块缺陷及正式20题指标仍待补齐。2026-10-31已核对①②语料版本一致，具体SHA及范围见协作页；不再将①②版本未知列为阻塞。`--ask`尚未接本地Retriever，仍调用独立Web Agent。实际证据和接收范围只看[协作页](docs/协作与需求节点.md)。

## 从根目录运行

需要Python 3.12。克隆后不再进入“成员1集成”等子项目目录。

```powershell
git clone https://github.com/zhewangguaiguaide/5003.git
cd 5003
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m src.main --dry-run
.\.venv\Scripts\python.exe -m src.main --live --mode fake
.\.venv\Scripts\python.exe -m src.main --mode fake --status
```

Windows直接调用虚拟环境解释器即可；macOS/Linux把`.venv\Scripts\python.exe`换成`.venv/bin/python`。依赖版本由`requirements-lock.txt`约束，换机器重新建环境。

`fake`流程使用`tests/mock_site.py`的合成网页，不联网、不需要API密钥或真实语料；固定使用`data/demo_fake.db`，会忽略`--db`覆盖。重复执行保留幂等行为。它用于验证采集与存储链路，不能代替真实网站或RAG验收。

## 已发布数据库与同版语料

2026-10-31组长授权将当前开发基线随Git发布，克隆后已有`data/cityu_faq.db`及同版`data/corpus.jsonl`，无需再从旧集成目录取这两份文件。发布库保留159条活动文档、83条原始采集记录和2条导入记录；个人问答和抓取日志均为0。两条导入记录及报告中的本机路径已改为相对路径，并重整数据库移除残留页；原始数据库未修改。文件字节SHA及检查范围见[data/release_manifest.json](data/release_manifest.json)。

来源为City University of Hong Kong website，各条记录保留原网页URL。该基线用于课程开发，发布不表示已复核所有制度的现行适用性，不包含本轮研究中新抓的全部政策页。

建议把发布库视作固定输入，实际写入和问答记录用忽略的本机副本：

```powershell
Get-FileHash -Algorithm SHA256 data/cityu_faq.db
Get-FileHash -Algorithm SHA256 data/corpus.jsonl
# runtime.db已存在时保留自己的版本，勿覆盖已有日志。
if (-not (Test-Path data/runtime.db)) { Copy-Item data/cityu_faq.db data/runtime.db }
.\.venv\Scripts\python.exe -m src.main --db data/runtime.db --status
```

③现有构建脚本直接读已发布的JSONL；另行准备E5模型及检索依赖后执行`python -m scripts.build_wsb_index`。本次没有附带模型、索引或真实模型验收结果；①⑤的数据与检索应用接入仍需实施。

②后续更新完整快照时，①先在独立数据库验收；未重新检查的数据、日志与数据库不自动入Git：

```powershell
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --import-corpus data/corpus.jsonl
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --quality --quality-source documents
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --status
```

先核对F1/F2/F3和完整快照，再确认正式接收；质量命令只覆盖结构、版本与配置种子，不能代替语义验收。正式库默认`data/cityu_faq.db`。快照接收后禁止用旧`records`的`--migrate/--export`覆盖它。

2026-10-31组长确认①②在采集后未更新语料；本地只读核对159行JSONL与数据库159条活动文档的URL及全部12个交付字段一致，数据库来源SHA均匹配。该快照SHA为`2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`，可据此交付当前开发基线。版本一致性已确认，F项语义复核与下游取件范围分别记录。代码中的`pending_member2`、`release_ready=false`是固定输出，不能单独据此判断人工审核是否发生。

当前JSONL和脱敏SQLite已纳入Git白名单；③可直接基于上述SHA准备候选索引，正式指标及接受范围仍按节点验收。④⑥的标注工具和⑤接口开发可并行，公开数据可用不代表候选规则目录或正式金标已经批准。

真实抓取前按需执行`.\.venv\Scripts\scrapling.exe install`安装浏览器，再使用`--smoke <URL>`或`--live --column fees`；只在已确认范围内限速抓取。默认浏览器路径仍需②补足F3证据。联网问答使用本机环境变量`DEEPSEEK_API_KEY`，执行`python -m src.main --ask "your English question"`；当前模型配置以`config.yaml`为准，未在本次重组中做在线验证。

## 组员从哪里开始

| 要做什么 | 唯一入口 |
|---|---|
| 看真实语料研究、分类制度表与目标流程图 | [制度规则与目标流程](knowledge/README.md) |
| 开始四模式评测、快速证据标注，区分知识库/golden/rubric | [评测启动入口](evals/README.md) |
| 看当前状态、②返工、上下游等待与Git交接 | [协作与需求节点](docs/协作与需求节点.md) |
| 按姓名或①—⑥岗位调用自动提示词 | [六岗位提示词](docs/岗位提示词.md)；项目自动入口为[AGENTS.md](AGENTS.md) |
| 查运行约束、快照、Hit与索引契约 | [开发与接口约定](docs/Harness开发指导.md) |
| 看甘特图、工时和建议日期 | [排期与工时](docs/排期与工时.md) |
| 接收、复核或准备岗位交接 | [.agents/skills/team-handoff/SKILL.md](.agents/skills/team-handoff/SKILL.md) |
| 审查工程/成员进展、条件化排期、准备本轮跟进话术 | [协作页](docs/协作与需求节点.md)、[当前话术](docs/岗位提示词.md#current-followup)及仓库内交接skill |

2026-10-25分工已同步到上述入口：组长负责交互与集成，燕萍负责Agent侧rubric、测试集和回答评测；PPT由组长后续提供统一模板、全员各做自己的部分。成员姓名、认领原话和最新责任只在协作页维护，报告/视频整合人待确认。

## 目录与Git交接

```text
src/                 运行源码
tests/               离线测试及fake流程依赖的合成站点，必须保留
knowledge/           官网核查、规则候选和目标流程；未获准进入正式索引
evals/               四模式评测与真实证据标注入口、rubric；真实题集私下交付
scripts/             索引构建、评测资产校验与历史维护脚本
config.yaml          采集、存储、联网搜索配置
schema.sql           SQLite模型与索引
requirements*.txt    运行依赖与版本约束
data/                已发布数据库、同版JSONL及版本清单；其他本机产物保持忽略
docs/                上表四份维护文档、两张工时图
.agents/skills/      可复用交接skill
AGENTS.md            按岗位与节点选择提示词
```

代码、必要测试、脱敏配置及当前节点状态通过Git交接；变更原因、验证命令、数据/索引版本和下游影响写进提交或PR说明。接收者按节点验收后更新同一张状态表，不再复制整包、diff、环境冻结日志或多份交接报告。没有新证据时保留“待验证”。

本次整合以原提交`7f1d43b`为来源。旧交接、验收与实验原件可用`git show 7f1d43b:<旧路径>`查看，当前目录只保留其有效结论。Git提交追踪代码版本；组内语料仍用SHA-256绑定，二者不能混用。

## 发布与验证边界

按组长要求，协作页保留任务相关姓名、岗位及必要认领原话；聊天原图、昵称数字、学号、登记表和其他身份资料不入仓。2026-10-31明确授权的公开数据仅为上列已检查的JSONL、脱敏数据库及版本清单，其他数据库、模型、索引、密钥、原始日志、浏览器资料、私有golden和虚拟环境保持忽略。后续更新重新检查，避免把本机运行痕迹混入发布库。详细证据留本机`runs/`，Git只记录检查摘要；数据来源保留City University of Hong Kong website及原URL。

2026-10-21重组验证覆盖48项离线测试、根目录CLI与合成站点流程；使用已有依赖环境。未验证全新机器安装、真实抓取、在线模型调用或尚未实现的RAG。

2026-10-26调整为真实制度研究路线：先核官网与数据库，再维护来源、候选规则表及目标流程；不再提供独立合成知识库或合成DEV题集。知识目录当前30个官方来源、43条候选记录（39条官网摘要、4条研究核对规则）、8个研究流程和7条条件化付款日期。18条来源登记项已有完整正文及SHA，全部候选仍待②⑥复核。评测显式指定真实语料与私有题集；四模式runner仍待实现。

## 本次GitHub提交范围（2026-10-26）

本轮已成功fetch确认远端main仍为`5282703`。下面是相对此版本的提交范围；fetch成功不表示push成功，最终同步状态须以实际推送结果核对。

| 一并提交的材料 | 文件及用途 |
|---|---|
| 研究入口与唯一底稿 | `knowledge/README.md`、`knowledge/catalog.json`：规则、流程、来源状态及K01–K08缺口 |
| 评测启动与通用判分标准 | `evals/README.md`、`evals/rubric.json`：④⑥如何标注与评分，⑤如何提供被测输出 |
| 校验工具及必要测试 | `scripts/check_eval_assets.py`、`scripts/check_policy_assets.py`、`tests/test_eval_assets.py`、`tests/test_policy_assets.py`；校验通过不等于政策或性能验收通过 |
| 统一协作入口 | `README.md`、`AGENTS.md`、`docs/协作与需求节点.md`、`docs/Harness开发指导.md`、`docs/岗位提示词.md`、`docs/排期与工时.md`：含最新分工、接口、启动话术及条件依赖 |
| 交接经验及忽略规则 | `.agents/skills/team-handoff/SKILL.md`、其`references/经验与依据.md`及`.gitignore`；避免按过时路径或依赖交接 |

合计17个净变更文件，复用已有入口。③已经上传的Retriever和构建脚本继续保留，本次没有替③修复或验收检索实现。

以上为10/26提交范围的历史说明。10/31新增发布的数据库、JSONL及版本清单见本页“已发布数据库与同版语料”；`data/wsb_index/`索引、`evals/private/`金标、`runs/`研究快照与日志、模型缓存和密钥仍未发布。其他取件位置见[节点页](docs/协作与需求节点.md#用git交接文件放哪里)及[知识入口](knowledge/README.md#原文快照如何交接)，不能把候选目录当作获准运行知识库。
