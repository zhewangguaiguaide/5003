# CityU Agentic RAG · DSC5003

面向学生服务FAQ的课程项目。仓库根目录是唯一运行目录，沿用成员①②已集成的最大可运行集合：采集、清洗导出、SQLite存储、完整快照接收、离线测试及联网搜索Agent雏形。

**当前还没有正式向量检索与完整自有语料RAG。** ③的索引和⑤的应用查询接入仍待实现；`--ask`调用的是已有联网搜索雏形。②的F1/F2修复及F3验证仍待验收，整理仓库不改变这些状态。

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

## 接收组内真实语料

②通过组内渠道交付完整快照及SHA，①先在独立数据库验收；数据放`data/`，不提交到公开仓库。

```powershell
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --import-corpus data/corpus.jsonl
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --quality --quality-source documents
.\.venv\Scripts\python.exe -m src.main --db data/acceptance.db --status
```

先核对F1/F2/F3和完整快照，再确认正式接收；质量命令只覆盖结构、版本与配置种子，不能代替语义验收。正式库默认`data/cityu_faq.db`。快照接收后禁止用旧`records`的`--migrate/--export`覆盖它。

真实抓取前按需执行`.\.venv\Scripts\scrapling.exe install`安装浏览器，再使用`--smoke <URL>`或`--live --column fees`；只在已确认范围内限速抓取。默认浏览器路径仍需②补足F3证据。联网问答使用本机环境变量`DEEPSEEK_API_KEY`，执行`python -m src.main --ask "your English question"`；当前模型配置以`config.yaml`为准，未在本次重组中做在线验证。

## 组员从哪里开始

| 要做什么 | 唯一入口 |
|---|---|
| 看当前状态、②返工、上下游等待与Git交接 | [协作与需求节点](docs/协作与需求节点.md) |
| 按①—⑥身份调用自动提示词 | [六岗位提示词](docs/岗位提示词.md)；项目自动入口为[AGENTS.md](AGENTS.md) |
| 查运行约束、快照、Hit与索引契约 | [开发与接口约定](docs/Harness开发指导.md) |
| 看甘特图、工时和建议日期 | [排期与工时](docs/排期与工时.md) |
| 接收、复核或准备岗位交接 | [.agents/skills/team-handoff/SKILL.md](.agents/skills/team-handoff/SKILL.md) |

## 目录与Git交接

```text
src/                 运行源码
tests/               离线测试及fake流程依赖的合成站点，必须保留
config.yaml          采集、存储、联网搜索配置
schema.sql           SQLite模型与索引
requirements*.txt    运行依赖与版本约束
data/                本机语料、质检和数据库，仅.gitkeep入Git
docs/                上表四份维护文档、两张工时图
.agents/skills/      可复用交接skill
AGENTS.md            按岗位与节点选择提示词
```

代码、必要测试、脱敏配置及当前节点状态通过Git交接；变更原因、验证命令、数据/索引版本和下游影响写进提交或PR说明。接收者按节点验收后更新同一张状态表，不再复制整包、diff、环境冻结日志或多份交接报告。没有新证据时保留“待验证”。

本次整合以原提交`7f1d43b`为来源。旧交接、验收与实验原件可用`git show 7f1d43b:<旧路径>`查看，当前目录只保留其有效结论。Git提交追踪代码版本；组内语料仍用SHA-256绑定，二者不能混用。

## 发布与验证边界

登记表、个人信息、密钥、网页全文、数据库、索引、原始日志和虚拟环境不入仓；详细证据保存在本机忽略目录`runs/`，Git中只记脱敏摘要。网页来源须标注City University of Hong Kong website，仅用于课程演示。既有历史记录不构成再分发网页全文的授权。

2026-10-21重组验证覆盖48项离线测试、根目录CLI与合成站点流程；使用已有依赖环境。未验证全新机器安装、真实抓取、在线模型调用或尚未实现的RAG。
