# DSC5003 前端原型 · 证据问答与交付演示

## 启动

```powershell
cd 04_前端原型                # 在仓库根目录下进入前端目录
python .\app.py --backend .. --open
```

默认地址 `http://127.0.0.1:8501/`。依赖只有 Python 标准库；不需要 Streamlit、Node 或额外包。


## F1 首屏架构

00 总览页先给两条车道、模块链、人机交互与核心命令；01 提问页只保留输入、结果和引用：

- **Offline**：无密钥、本地 BM25/摘录、answer-type gate、S1–S5 引用；不调用模型。
- **Online**：同一 881 片段索引 → 证据约束回答 → 独立复核（pass/revise/reject）→ 服务器映射引用；失败回退离线。
- 两条车道下方是模块链（R02 采集 → R03 索引 → R05 检索/Agent → F1–F5 界面；R04/R06 评测复核回环）、人机交互回路（人 → 系统 → 人）和核心命令（启动/健康检查/强制离线/API）。
- 问题输入框随内容自动增高；回答按 `answered / clarify / abstained / out_of_scope` 自适应为要点、选项、拒答或问题清单。顶部导航为 `00 架构 / 01 提问 / 02 数据 / 03 检索 / 04 评估 / 05 交付`，不再重复“演示路线”条。
- F5 的根目录/仓库卡改为离线/在线细节对照，并保留 `app.py / evidence_qa.py / web/ / data/` 入口和 GitHub 链接。
- F2 新增 `Knowledge base` tab：157/159 已索引、2 篇未索引、主题筛选、文档→chunk 首个片段抽屉、JSONL→SQLite 字段映射和 snapshot receipt。
- F3 新增 `Vector index anatomy`：FAISS 0-based ID、chunk_id、doc/URL、R05 881 vs R03 863、index SHA、normalize/max_seq/DB binding。
- F4 新增可展开的 `Rubric 与 golden 题集`：4 维 rubric anchors、hard fail、关键规则、CORE20/R4DEV 的聚合计数与字段说明；题面示例为合成结构，不复制受控 gold；并显示 R06 硬失败候选。

## F1 问答链路

F1 提供三种彼此分开的结果：

1. **证据问答（主路径）**：`Ask evidence index` → `POST /api/answer`。服务器读取 R05 冻结快照的 `data/wsb_index/chunks.json`（881 片段），先做本地主题识别与检索，再把 Top-5 证据交给模型。模型只能使用证据中的 `S1…S5`，不能自己生成 URL；随后再运行一次独立证据复核，复核可以 `pass / revise / reject`。
2. **离线摘录（fallback）**：没有 `DEEPSEEK_API_KEY`，或显式设置 `DSC5003_DISABLE_LLM=1` 时使用。系统直接摘录匹配句子并附来源；若问题类型与句子不匹配（例如问开放时间但证据没有时间），会拒答而不是硬答。
3. **合成接线检查（次级）**：`Backend wiring check (synthetic)` 调用 R05 的 `--rag-demo` 夹具。它只证明 UI/CLI 能连通，返回文本被折叠，不作为政策答案展示。

### 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 启用在线模型与独立复核 | 未设置则离线摘录 |
| `DSC5003_DISABLE_LLM` | 设为 `1` 强制离线 | 未设置 |
| `DSC5003_LLM_MODEL` | 模型名 | `deepseek-flash` |
| `DSC5003_LLM_BASE_URL` | OpenAI 兼容端点 | `https://api.deepseek.com` |
| `DSC5003_LLM_TIMEOUT` | 单次调用超时（秒） | `60` |

模型调用会关闭 thinking（`thinking: {"type":"disabled"}`），减少等待和截断；若端点不支持该参数，会自动回退到离线摘录并在 `warnings` 中说明。模型返回的 `summary` 与 `points` 都会做引用校验：不得包含 URL、不得引用不存在的 S 编号、point 不得自带引用标记；独立复核的 verdict 必须是 `pass / revise / reject`，否则不发布答案。

### API

```powershell
# 健康检查：索引、模型配置、默认模式
Invoke-RestMethod http://127.0.0.1:8501/api/health

# 证据问答
$body = @{question='How do I pay my tuition?'} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8501/api/answer `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

返回字段包括：`status`、`mode`、`answer`、`citations`、`retrieval_rounds`、`llm_calls`、`usage`、`review`、`clarify_options`、`scope_note`、`warnings`、`versions`。

### 建议测试

- `How do I pay my tuition?` / `学费怎么交？` → 缴费渠道与截止条件
- `What do I need to enter the library?` / `进入图书馆需要什么？` → 学生证与 EID 分开说明
- `Can I get a refund?` → 先给四种退款选项，再按选项检索
- `How are non-local entrance scholarships awarded?` → 非本地生入学奖学金
- `When is the add/drop period?` → 校历日期
- `图书馆几点开门？` → 证据没有具体时间时应拒答（abstained）
- `Who won the World Cup?` → 超出范围（out_of_scope）

## 边界

- 索引只覆盖 8 个城大学生服务主题、159 篇页面、881 个片段；不是城大网站全量，也不是通用助手。
- 答案语言跟随问题（中文问→中文答，英文问→英文答）；界面语言由右上角 `EN / 中文` 单独控制。
- F1 的主题选择器只在用户点选主题或样例时改变；自动模式不会被上一次结果改写。
- 引用身份（URL、chunk_id、S编号）由服务器映射；模型不能生成引用。引用只能证明“文本来自哪里”，不自动证明语义支持；独立复核是第二道检查，不是正式人工验收。
- 已发布 SQLite 的 `chunks=0`、R05 运行索引的 `881`、R03 对比构建的 `863` 是三个不同产物，不能合并成一个数字。
- 合成夹具（`example.invalid`）不是学校政策，也不能计入 N5/N7 正式成绩。
- 真实 N5/N7 需要 E5 模型、运行索引和本机密钥；本前端的在线模型路径是“检索 + 生成 + 复核”的演示，不替代 R05 的正式模型运行记录。

## 目录

```text
app.py            HTTP 服务、F2 只读 SQL、/api/answer
evidence_qa.py    主题识别、BM25 检索、离线摘录、模型回答、独立复核
build_ui_data.py  生成 data/ui_data.json（冻结证据视图）
web/              原生 HTML/CSS/JS
data/             冻结页面数据
```

## 版本

- 后端快照：`c7b067f`（76 个 Git 文件）
- 检索快照：`data/wsb_index/chunks.json`，881 片段，384 维，模型 `intfloat/multilingual-e5-small`
- 评估：R04 `9de28ad`，R06 `39a1f81`
- 语料：159 篇，SHA-256 `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`
