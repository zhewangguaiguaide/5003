# Harness 开发指导（Agent 开发爬虫时的 prompt 文档）

> 本文件是 `src/` 爬虫的"开发指导文档"，与「接口定义」「eval 测试」共同构成 Harness 三件套。
> 方法学提炼自课外资料《AI Search 爬虫 Agent》（原文见 `docs/evidence/课外资料_AI_Search爬虫Agent.docx`），
> 并结合本项目实测结论（见 `docs/可行性研究.md`）改写。

## 1. 目标

为 CityU 学生服务 FAQ（申请 / 注册 / 签证 / 宿舍 / 学费 / 奖学金 / 图书馆 / 校历）采集可入库的干净语料，
供 agentic RAG 检索使用。

## 2. 三件套

| 要素 | 本项目对应物 | 作用 |
|---|---|---|
| 接口定义 | `src/crawler.py` 的 `ColumnCrawler`（`fetch_list_page` / `fetch_detail` / `crawl`）与 `DomainCrawler`（`crawl`） | 缩小 Agent 的执行空间 |
| eval | `tests/test_standard.py`（7 项标准化评估，离线可跑） | Agent 自我验证 + 人一条命令验收 |
| 开发指导文档 | 本文件 | 降低决策难度 |

## 3. 三条硬性工程要求

1. **增量爬取**：只抓新增内容，不重复全量重爬（避免无谓请求、避免触发反爬）。
2. **幂等**：中途崩溃/断网后重跑一次，不漏数据、不重复写库。
3. **清洗**：写入库的内容是清洗过的（正文、标题、日期、图片、附件分开），非正文内容不入库。

## 4. 核心数据结构：栈（LIFO）

假设目标站点满足：存在列表页与详情页；列表页头部是最新内容；历史内容不删除。

```
列表页扫描阶段：
    请求列表页 -> 解析详情页 URL -> 该 URL 已在库中?
        否 -> URL 入栈（不写库） -> 继续扫描
        是 -> 停止扫描（终止条件）
出栈阶段：
    栈非空 -> 出栈 -> 抓详情 -> 清洗 -> 入库
```

于是"**从新到旧入栈、从旧到新入库**"：即使中途崩溃，重跑时也会从上次断点处继续，天然幂等。

**终止条件（需连续统计以保证鲁棒性）**：
- 连续 n 次翻页返回 404（本实现：`max_consecutive_404`，默认 3）
- 连续 m 条已入库内容（本实现：命中第一条已入库 URL 即停止扫描，由 `storage.exists()` 判定）

## 5. 实现约定

1. 网络请求之间必须有 **随机延迟 1-3s**（本项目按合规要求设为 2-3s），在 `config.yaml` 的 `politeness` 配置。
2. 少数难爬页面用无头浏览器（本项目 = `scrapling StealthyFetcher`）；简单站点可直接 HTTP 规则解析。
3. 图片地址放 `image_urls`、附件（PDF/Office）放 `file_urls`；抓取失败保留 `error` 字段，便于后续 Loop 修复。
4. `date` 与 `crawled_at` 均为 ISO 时间；无法解析日期时用抓取时间兜底（`fetch_detail` 已实现）。
5. 外链无需入栈抓取。
6. 做好判断，不要抓取非正文部分——**清洗也是爬取的工作之一**。

## 6. 实测特有的坑（务必遵守）

1. **WAF 假 200**：cityu.edu.hk 全站在 Imperva Incapsula 后，被拦时返回 `HTTP 200` + ~850B 挑战页。
   `looks_like_challenge()` 的判据是"内容极短 **且** 含 `_Incapsula_Resource`/`incident_id`"——
   实测正常页面也会含 `_Incapsula_Resource`（WAF 注入脚本），**不能只看标记**。
2. **慢页面**：`StealthyFetcher` 必须 `disable_resources=True`，否则部分页面 `network_idle`/`goto` 会一直超时。
3. **依赖**：scrapling 0.4.x 需一并安装 `curl_cffi playwright patchright browserforge msgspec`，并执行 `scrapling install` 下载浏览器。
4. **不可达通道**：本网络环境无法访问 `r.jina.ai`、`web.archive.org`；`libguides.library.cityu.edu.hk` 与学院子站（`cb/mba.cb/ssweb.cityu.edu.hk`）可直连。

## 7. 维护 Loop（后续迭代方向）

同一站点的失败往往同因同报错，修一条即修一类：

```
按 error + 域名 + 栏目分类 -> 取一类错误数据 + 少量成功样本
    -> Agent 修复 -> 标准化集成测试 -> 回归验证成功样本仍可抓 -> 重爬失败数据
```

诀窍是上下文管理：**一次只让 Agent 处理一个栏目下的一类错误，处理完清空上下文**，由程序驱动循环。
