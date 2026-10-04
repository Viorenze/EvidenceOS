# EvidenceOS — PRD（1 周精简版）

> 目标：10 月 11 日前做出一个能现场演示、能被追问到底的 AI 全栈项目，边做边投递。
> 原则：宽度砍到最小，深度只留四处——混合检索、有条件循环的 Agent、可核对引用、评测。

## 1. 一句话

上传技术文档 → 混合检索 → Agent 判断证据是否充足（不足则改写查询重检索，仍不足则拒答）→ 流式输出带可核对引用的回答；命令行跑评测并生成报告。

## 2. 第 7 天的验收标准

- [ ] `docker compose up` 后访问 `localhost:3000` 可用，无需登录
- [ ] 上传 md/pdf → 提问 → 流式回答，点击引用能看到原文片段
- [ ] 知识库里没有答案时，系统明确拒答，而不是编造
- [ ] `make eval` 生成 `reports/eval.md`，包含 vector-only / hybrid / hybrid+agent 三档对比
- [ ] README（含架构图）+ 3 分钟演示视频
- [ ] 我能不看代码讲清第 11 节列出的核心模块

## 3. 范围

| 做 | 不做（全部进 backlog） |
|---|---|
| 单用户、免登录、一个知识库 | 登录/权限/多 Workspace |
| 2 个页面：Documents、Chat | Dashboard、评测网页 |
| 单轮问答，记录每次运行 | 多轮对话记忆 |
| SSE 流式输出（含 Agent 步骤事件） | WebSocket |
| 混合检索（向量 + 全文，RRF 融合） | Reranker、Redis、MCP、Web Search |
| LangGraph 单 Agent，带条件循环 | 多 Agent |
| 命令行评测 + markdown 报告 | K8s、微服务、云部署 |
| Docker Compose、pytest | 复杂 CI（最后有时间再加一个跑 pytest 的 workflow） |

## 4. 技术选型（锁定）

| 层 | 选择 | 备注 |
|---|---|---|
| 前端 | Next.js + TypeScript + Tailwind | UI 能用就行，不花时间美化 |
| 后端 | FastAPI + Pydantic + SQLAlchemy | 异步接口，SSE 用 StreamingResponse |
| 数据库 | PostgreSQL + pgvector | 向量与全文检索同库 |
| 中文分词 | jieba | Postgres 默认全文检索不会切中文，见第 7 节 |
| Embedding | 本地 `BAAI/bge-small-zh-v1.5`（512 维） | 经 `EMBEDDING_PROVIDER=local\|api` 切换，CPU 可跑 |
| LLM | 国内 OpenAI 兼容接口（DeepSeek / 通义 / 智谱任选） | 经薄抽象层调用，`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` |
| Agent | LangGraph | |
| 工程 | Docker Compose、pytest、Git | |

依赖版本在 M0 由 lockfile 固定，不手写版本号。

## 5. 数据模型（3 张表）

- `documents`：id, filename, status（processing/ready/failed）, n_chunks, error, created_at
- `chunks`：id, document_id, idx, page, heading, content, content_seg（jieba 分词后的文本）, tsv（tsvector，由 content_seg 生成，GIN 索引）, embedding vector(512)（HNSW 索引，cosine）
- `runs`：id, question, mode, answer, citations（jsonb）, steps（jsonb）, refused（bool）, latency_ms, created_at

## 6. API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/documents` | multipart 上传，返回 202 与文档 id，后台入库 |
| GET | `/api/documents` | 文档列表与状态 |
| DELETE | `/api/documents/{id}` | 删除文档及其 chunks |
| GET | `/api/chunks/{id}` | 引用原文展示 |
| POST | `/api/search` | `{query, mode: vector\|hybrid, k}`，供评测与调试 |
| POST | `/api/chat` | `{question}`，返回 SSE |

SSE 事件：

- `step`：`{node, status, detail}`（retrieve / grade / rewrite / generate）
- `token`：`{text}`
- `citations`：`{items: [{n, chunk_id, document, page, heading, snippet}]}`
- `done`：`{run_id, refused, latency_ms}`
- `error`：`{message}`

## 7. 检索设计

**分块**：优先按 markdown 标题与段落切，目标约 400–500 中文字符，重叠约 50；保留 `heading` 与 `page`。PDF 先用文本提取，扫描件不支持（写进 README 的已知限制）。

**中文全文检索**：入库与查询时都先用 jieba 分词，空格连接后存入 `content_seg`，`to_tsvector('simple', content_seg)` 建索引。不这样做，中文关键词检索基本等于失效。

**混合检索**：

1. 向量检索 top 20（cosine）
2. 全文检索 top 20（`ts_rank_cd`）
3. RRF 融合（k=60）取 top 5

所有数值走配置，评测时可调。

## 8. Agent 图

```text
START → retrieve → grade ──sufficient──→ generate → verify_citations → END
                     │                                    │
                     │insufficient                        └─ 无有效引用：重试一次，仍无则 refuse
                     ├─ rewrites < 2 → rewrite ──→ retrieve
                     └─ rewrites = 2 → refuse → END
```

**State**：`question, query, rewrites, chunks, grade, answer, citations, refused, steps`

**grade**：LLM 结构化输出 `{sufficient: bool, reason: str, missing: str}`，判断当前检索结果能否回答问题。

**rewrite**：根据 `missing` 生成新查询，最多 2 次。

**generate**：上下文片段编号为 `[1]…[k]`，要求回答中用 `[n]` 标注来源，流式输出。

**verify_citations**：服务端校验每个 `[n]` 都指向本次检索到的 chunk，剔除非法引用；若没有任何合法引用，重试生成一次，仍没有就拒答。

**refuse**：固定文案，说明知识库中没有足够证据，不调用 LLM 编造。

**工具调用（P1，评测做完才做）**：给 grade 节点加一个 function-calling 工具 `get_neighbors(chunk_id)`，取相邻 chunk 扩展上下文。做完才能在简历里写 Tool Calling。

## 9. 评测

数据集 `evals/dataset.jsonl`，约 25 题，**由我自己手写**：

- 20 题可回答：`{id, question, type: "answerable", gold_doc, gold_snippet}`，`gold_snippet` 是答案所在原文中的一小段，用子串匹配判定，不依赖具体分块
- 5 题不可回答：`{id, question, type: "unanswerable"}`，问题看似相关但文档里没有答案

语料：3–5 份开放许可的技术文档（例如 FastAPI、PostgreSQL 官方文档的若干章节），确认许可后放进 `evals/corpus/`。

指标：

- **Hit@5**：检索 top 5 中是否有 chunk 包含 `gold_snippet`
- **Citation precision**：回答引用的 chunk 中，包含 `gold_snippet` 的比例
- **Refusal accuracy**：不可回答题是否拒答，且可回答题没有误拒
- **Latency**：p50 / p95

三档对比：vector-only、hybrid、hybrid+agent。报告里的每个数字都来自真实运行，写进简历前核对一遍。

## 10. 一周计划

| 天 | 目标 | 当天验收 |
|---|---|---|
| D1 | M0 + 入库：compose、三张表、上传 md/pdf、分块、embedding、写入 | 上传文档后 chunks 与向量入库；命令行能做向量检索 |
| D2 | 混合检索：jieba + tsvector + RRF，`/api/search`；开始手写评测题 | 同一问题 vector 与 hybrid 结果可对比；检索有 pytest |
| D3 | Agent：LLM 抽象层、LangGraph 图、grade/rewrite/refuse、引用校验，先非流式 | 可回答题有引用，不可回答题拒答 |
| D4 | SSE + 前端：Documents 与 Chat 两页，步骤展示，引用点击看原文 | 浏览器里走通完整主流程 |
| D5 | 评测 runner + 报告；按失败用例调分块、阈值、提示词 | `make eval` 出三档对比报告 |
| D6 | 收尾：错误处理、pytest、README、架构图、演示视频；在干净克隆上验证 `docker compose up` | 陌生机器按 README 能跑起来 |
| D7 | 缓冲、P1 工具调用（如果有余量）、简历、面试自测 | 简历定稿，能不看代码讲清第 11 节 |

**投递节奏**：27 届秋招已在进行，D3 完成后就开始投递，简历项目如实标注"进行中"，D5 之后补上真实评测数据。

## 11. 必须自己吃透的部分

下面这些可以让 Agent 起草，但我必须逐行读懂，最好自己改写一遍。每天晚上用 20 分钟不看代码口头讲一遍：

1. 分块函数（为什么这样切，换大小会怎样）
2. 混合检索 SQL 与 RRF 公式
3. jieba 分词与 tsvector 的配合方式
4. LangGraph 的 state、节点、条件边
5. 引用校验逻辑
6. 评测 runner 与指标定义

UI、Docker、CRUD、样板代码可以放心交给 Agent。

## 12. 面试叙事与简历

- 叙事：我做了一个带引用的知识问答系统，用评测证明混合检索优于纯向量，用带条件循环的 Agent 处理证据不足的情况，并让系统在没有答案时拒答。
- 简历只写已经做完并测过的内容；数字只写评测报告里的真实数字。
- 演示方式：本地 `docker compose up` 现场运行，另备演示视频兜底。

## 13. Backlog（一周后再说）

Reranker、多轮记忆、登录与多 Workspace、Redis 缓存与限流、MCP、评测网页、CI/CD、云部署、Web Search。
