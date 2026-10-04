# EvidenceOS 工程审计：D1 → D3

- 审计日期：2026-10-05
- 审计基线：`HEAD = 473096e`（4 个提交：`9d5fd63` D1、`7327da4` 测试修正、`96a4a7f` D2、`473096e` D3）
- 规范基线：`docs/PRD.md`、`AGENTS.md`
- 审计方式：只读。通读全部 `apps/`、`tests/`、`evals/`、配置文件与 Git 历史；在仓库外写了两个临时探针脚本做行为验证（见第 9 节）。除本文件外**未修改仓库内任何文件，未提交**。

---

## 0. 结论摘要

**总体判断：骨架正确，但"能跑"和"可信"之间还有距离。**

做对的部分：

- 图的拓扑符合 PRD。`retrieve → grade → rewrite(≤2) → retrieve …` 的条件循环存在，`refuse` 不调用 LLM。我用打桩检索跑了一遍，实测 `rewrites` 上限为 2，拒答路径的 LLM 调用序列是 `grade, rewrite, grade, rewrite, grade`，没有 generate。
- LLM 和 embedding 都走抽象层，业务代码里没有散落的 SDK。
- 大部分阈值进了 `Settings`。
- RRF 实现正确，且有精确数值断言。
- 入库在提交前不会暴露半成品 chunk（chunk 在最后一次 commit 才可见）。
- tsquery 的词元经过 `\w` 清洗，没有 tsquery 语法注入面。

但有 5 个 P0 问题会直接损伤 D4 的验收或面试可信度：

1. 流式输出与"生成后才校验引用"在设计上互相冲突，PRD 没给出解法。
2. 7 个 agent 测试依赖在线 Postgres 和库内已有数据，`make test` 在干净环境下不绿。这违反 AGENTS.md "agent 测试离线、确定性"。
3. 分块器的"重叠 50"在主路径上没有实现，而对应的重叠测试是空转的，会误导你。
4. 引用校验会对 `[1, 2]`、`【1】` 误拒答，会把正文里的 `data[0]` 删成 `data`，还会压缩代码缩进。
5. LLM 调用没有任何失败语义，一次 JSON 解析失败就让整个 run 崩掉，D4 的 `error` 事件无从谈起。

另外，**D2/D3 的验收从未在真实 embedding 或真实 LLM 下跑过**。仓库里没有任何检索效果或 agent 行为的真实证据。评测语料只有 15 个 chunk，又是 AI 代写的，目前几乎不能说明 hybrid 优于 vector。

> 建议：D4 开工前先清掉 P0（预计 3–4 小时），再把 P1 中的"真实 LLM 冒烟"做掉。在此之前，不要把 D3 当作"已完成"写进简历。

---

## 1. 验证范围与环境限制

| 项 | 状态 |
|---|---|
| `uv run pytest tests/ -q` | **实测：42 passed, 1 skipped, 7 errors**。Docker daemon 未运行，Postgres 不可达。7 个 error 全部是 `tests/test_agent.py`，原因是 `db_session` fixture 连不上库。 |
| 集成测试 `test_live_ingest_search_and_delete_cycle` | 因库不可达被 **skip**。本次审计**没有**验证 pgvector、HNSW、`GENERATED ... STORED` 的 tsv、中文 FTS 的真实行为。 |
| 真实 embedding（bge-small-zh） | 未运行。 |
| 真实 LLM | 未运行，仓库里也没有任何一次真实 LLM 的运行记录。 |
| PDF 正向路径（含文本的 PDF） | 未验证。测试只覆盖"空白页抛错"。 |
| 离线探针（分块、jieba、agent 图、引用校验） | 已运行，结果见各条目中标注"实测"的部分。 |

凡标注"静态分析"的结论，都是读代码推导而来，没有在真实库或真实模型上跑过，**必须在 D5 评测中证伪或证实**。

---

## 2. PRD 验收对照（D1–D3）

| 日 | PRD 验收项 | 状态 | 说明 |
|---|---|---|---|
| D1 | compose + 三张表 | 部分 | compose 只有 `db` 服务。三张表与 PRD 字段一致（静态核对）。表和索引创建未在真实库验证。 |
| D1 | 上传 md/pdf、分块、embedding、入库 | 部分 | md 路径完整。PDF 正向路径无测试。分块器有 P0 缺陷（见 P0-3）。 |
| D1 | 命令行向量检索 | 代码在 | `cli.py search --mode vector`。未在真实库运行。 |
| D2 | jieba + tsvector + RRF + `/api/search` | 代码在 | RRF 已测。FTS SQL 只有 mock 测试，没有任何中文 FTS 的真实库测试。 |
| D2 | 开始手写评测题 | **偏离** | 数据集和语料由 AI 在 `96a4a7f` 一次性生成，不是"我自己手写"（PRD §9）。 |
| D3 | LLM 抽象 + LangGraph + grade/rewrite/refuse + 引用校验，非流式 | 代码在 | 条件循环正确。引用校验有盲区（P0-4）。 |
| D3 | 可回答题有引用，不可回答题拒答 | **未验证** | 只在 FakeLLM 下验证过拓扑，从未用真实 LLM 和真实检索跑过任何一题。 |

---

## 3. 🔴 必须修复

### P0-1　流式输出与引用校验的顺序冲突（D4 设计阻塞）

**现状**：`generate_node` 调用 `llm.generate()`（非流式，`nodes.py:221`）。`verify_citations` 在整段回答生成完之后才运行（`graph.py:71`），并且会改写答案：删除非法标记，压缩空格。失败时还会重新 generate 一次，最终可能整体换成拒答文本。

**冲突**：PRD §8 要求 generate 流式输出，§6 的 SSE 只有 `token / citations / done`，没有"撤回/替换"事件。一旦 D4 把 token 实时推给前端：

- 用户会先看到未经校验的文本，包含 `[99]`；
- 重试发生时，旧 token 已经发出去了；
- 最终被拒答时，用户已经读到了一段"答案"。

这与"可核对引用、不编造"的核心叙事直接冲突。`done` 事件里也没有最终答案，前端无法对账。

**必须在写 D4 代码前做一个明确决定，并同步更新 PRD（AGENTS.md Rule 4）**，可选方案：

- **A. 先校验后推送**：generate 完整生成，verify 通过后，把已校验的文本用 `token` 事件分片推出（`FakeLLMProvider.stream_generate` 已经是这个思路）。`step` 事件仍然实时。实现最简单、行为最诚实，代价是"首字延迟"等于整段生成时间。
- **B. 真流式 + 末尾对账**：边生成边推 token，结束后校验；通过则发 `citations`；失败则必须新增事件（如 `answer_reset` 或在 `done` 里带 `answer`）。要改 SSE schema。
- 一周内推荐 **A**，并在 README 的已知限制里写明。

同时要决定：`stream_generate` 在图内怎么用。目前 `AgentNodes` 只有 `generate`，没有流式入口。

### P0-2　Agent 测试不是离线、确定性的（实测）

**证据**：`pytest` 在无库环境下 `7 errors`，全是 `tests/test_agent.py`。原因是这些测试用了 `db_session` fixture（`conftest.py:29`），并通过 `retrieve_node` 查**真实库**（`test_agent.py:33` 起）。

**更糟的是静态分析可推出的数据依赖**：`grade_node` 在 `chunks` 为空时**不调用 LLM**（`nodes.py:99-104`），因此不会消耗 `custom_grades`。结果：

- 库为空（干净 `make up` 后）：`test_agent_path_answerable_direct_success` 会走到 rewrite，步骤断言失败；`test_agent_citation_retry_*` 里的 `custom_answers` 被 rewrite 消耗，序列错位。
- 库里有开发数据：测试才碰巧通过。

此外：

- `test_run_agent_persistence_in_db` 往开发库写 `runs` 行且从不清理。
- 测试与开发共用 `evidenceos` 库。

违反：AGENTS.md "Agent tests use a fake LLM provider so they run offline and deterministically"。

**修法**：测试里用 `patch("apps.api.agent.nodes.hybrid_search", return_value=[...])` 提供固定 chunk，`db=MagicMock()`；`run_agent` 的持久化测试单独标 `@pytest.mark.integration`，并使用独立测试库。我的探针脚本就是这样做的，且在无库环境下全部跑通。

### P0-3　分块重叠在主路径上没有实现，而测试是空转的（实测）

**证据**（`chunker.py:66-80`）：命中标点（`\n\n`、`。` 等）的分支执行 `pos = pos + cut_offset`，**下一块从上一块结尾紧接着开始，没有重叠**。只有"找不到标点"的兜底分支才用 `pos += step`（`chunk_size - chunk_overlap`）。技术文档几乎总能找到标点，所以重叠基本不会发生。

**实测**：对非周期文本 `chunk_text(text, 400, 50)`，7 个 chunk，**所有相邻块都没有重叠**（"前块末尾 30 字符是否出现在后块"全部为 `False`）。

**测试为什么看不出来**：`test_chunker.py:39-61` 的输入是同一句话重复 30 次，文本具有周期性，任意 15 字符窗口都会出现在下一块里，所以 `overlap_found` 恒为 `True`。这个测试**无法失败**。另外，`len(c.content) <= 500` 对 `chunk_size=400` 的容差也过松。

**后果**：

- `chunker` 是 PRD §11 第一个"必须吃透"的模块。被问"overlap 为什么是 50"，答案会是"其实没生效"。
- 跨 chunk 边界的答案被切断，直接拉低 Hit@5。
- `chunker.py` 的模块文档字符串声称有重叠，与事实不符。

**修法**：标点切分后，下一块起点取 `cut_end - overlap`，并对齐到最近的句边界；测试改用非周期文本，断言"后块开头包含前块结尾的最后 N 字符"。

### P0-4　引用校验的盲区会造成误拒答和文本损坏（实测）

`citations.py` 只认 `\[(\d+)\]`。我用探针实测：

| 模型输出 | 实测结果 |
|---|---|
| `A [1][2]。` | 通过，OK |
| `A [1, 2]。` | `valid=False`，**走重试，仍失败则整体拒答** |
| `A [1-3]。` | 同上，误拒答 |
| `A 【1】。` | 同上，误拒答（国产模型常见全角括号） |
| `见 data[0] 与 arr[1]` | 变成 `见 data 与 arr[1]`：**合法正文被删除**，而 `arr[1]` 被当成"引用 1"，还能让校验通过 |
| 代码缩进 `    if x:\n        y = 1  [1]` | 缩进被压成单个空格（`citations.py:44` 的 `re.sub(r" +", " ")`） |
| "事实一（编造）。事实二（编造）。只有最后一句有引用 [1]。" | `valid=True`：**只要有一个合法标记，整段答案都算已校验** |

**影响**：

- 技术文档问答里"代码和下标"是高频内容。校验器既会破坏正文，也会被正文欺骗。
- 真实模型输出 `[1, 2]` 或 `【1】` 时，会把本可回答的题误判为拒答，压低 Refusal accuracy，并在 D4 演示时随机"翻车"。

**修法**（保持简单）：

1. 先把 `[1, 2]`、`[1-3]`、`【1】` 归一成 `[1][2]` 形式再校验；
2. `clean_answer_citations` 只处理"紧跟在句末标点或词尾的引用样式"，或至少跳过代码围栏和行内代码；不要全局压缩空格，只清理被删标记留下的那一个空格；
3. 在 generate 提示词里明确"引用必须写成 `[1]` 或 `[1][2]`，不要用逗号或全角括号"，作为第二道防线。

"每个论断都要有引用"的更强校验见 P1-3。

### P0-5　LLM 调用没有失败语义，D4 的 `error` 事件无从实现

**证据**：

- `grade_node` 调 `structured_output`（`nodes.py:130`）；JSON 解析失败、Pydantic 校验失败、HTTP 4xx/5xx、超时，都会直接抛出，整个 `graph.invoke` 崩溃。我用 `BadLLM` 实测，`ValueError` 一路传播，没有兜底。
- `run_agent` 不捕获异常（`runner.py:61`），所以失败的 run **不写入 `runs`**，也没有 steps 记录。
- `rewrite_node` 的返回值没有判空；`generate_node` 同理。
- `OpenAILLMProvider.stream_generate` 只捕获 `JSONDecodeError`（`provider.py:150`），而 `chunk_data["choices"][0]` 在末尾 usage chunk（`choices` 为空）或缺字段时会抛 `IndexError/KeyError`。
- `provider.py` 完全没有针对 `OpenAILLMProvider` 的 HTTP 层测试（`test_llm.py` 只测了构造函数和 Fake）。`structured_output` 的 markdown 围栏剥离、`stream_generate` 的 SSE 行解析都没有被运行过。

**修法**：

- 约定"grade 解析失败"的处理：要么重试一次再抛，要么保守地视为 `insufficient`。我倾向前者再抛，因为静默当成不足会把基础设施故障伪装成"知识库没答案"。
- `run_agent` 用 try/except 包住，失败也写一条 `runs`（`refused=false` 并在 steps 里记错误）。
- 给 `OpenAILLMProvider` 加 `httpx.MockTransport` 测试：正常、围栏 JSON、坏 JSON、5xx、流式分片、空 `choices`。
- 这些是 D4 `/api/chat` 里 `error` 事件的前置条件。

---

### P1-1　全文检索查询质量：无停用词、OR 拼接、`ts_rank_cd` 没有 IDF（静态分析，待 D5 证实）

`fulltext_search`（`retrieval.py:96-113`）把 jieba 的**所有**词元用 `|` 连起来。我实测 `"pgvector 中表示余弦距离的运算符是什么？"` 切成 `['pgvector','中','表示','余弦','距离','的','运算符','是','什么']`，其中 `中 / 的 / 是 / 什么` 都会进入 OR 查询。

- `'simple'` 配置没有停用词表，所以 `的 / 是` 会命中几乎所有 chunk。
- `ts_rank_cd` 只看词的出现与邻近度，**不使用全局词频（没有 IDF）**，也没有长度归一化（第三参数默认 0）。一个稀有关键词 `pgvector` 与一个常见字 `的` 在排名里几乎等价；
- 结果：Top-20 的全文通道可能被"高频虚词多、篇幅长"的 chunk 占满，RRF 融合时把噪声带进 Top-5。这可能让 hybrid 不优于 vector，推翻 DECISIONS.md 的叙事。

**修法**：加一份小的中文停用词表（配置化），过滤单字虚词；评估是否改用 `AND` 优先、`OR` 兜底，或对 `ts_rank_cd` 设置长度归一化标志。**不要先改，先在 D5 评测里量化，再决定。** 但必须在 D5 之前把停用词过滤做掉，不然 hybrid 的数字没有意义。

另一个相关点：索引端用 `jieba.cut` 精确模式，查询端同样。同一短语在文档上下文与查询里切法可能不同，造成漏召回。常规做法是索引端用 `cut_for_search`。作为 D5 调参杠杆记录即可。

### P1-2　评测资产不可用：语料太小、AI 代写、自指、题目泄漏

- **规模（实测）**：3 份语料共 6.5KB，切出 **15 个 chunk**（每份 5 个）。检索 Top-5 覆盖了 1/3 的全部语料，Hit@5 的随机基线约 33%，vector 与 hybrid 的差异在这个量级上区分不出来。
- **来源**：PRD §9 明确要求"由我自己手写"，语料用"开放许可的官方文档章节"。现状是 AI 在 `96a4a7f` 里一次性生成了数据集和语料，既不是手写，也不是真实官方文档的摘录。`rag_hybrid_retrieval.md` 甚至是在描述 EvidenceOS 自己的设计（`content_seg`、`EMBEDDING_PROVIDER`），评测在"考自己写的笔记"。
- **题目泄漏**：问题与 `gold_snippet` 词汇高度重合（如 q18 "平滑常数 k" 对应 "平滑常数 k=60 …"）。这会系统性偏向全文检索，放大 hybrid 的收益。
- **正确性**：`fastapi_overview.md` 称 `BackgroundTasks` 在"同一个异步事件循环中调度"，对同步函数并不准确（同步任务在线程池执行）。
- **好消息（实测）**：20 条 `gold_snippet` 都完整落在单个 chunk 内，未被切断（`snippets split/missed: 0`）。但这只是在语料很短的前提下成立，换成真实长文档后，P0-3 的无重叠问题会让它失效。

**修法**：换成 3–5 份真实、许可明确的文档（FastAPI / PostgreSQL / pgvector 官方文档章节，几万字级别），题目由你自己手写，问法要与原文措辞拉开距离，并加入需要跨 chunk 综合的问题。`test_dataset.py` 现在只证明"snippet 在原文里"，请加一条"每个 `gold_snippet` 切完块后落在单个 chunk 内"的校验。

### P1-3　引用"可核对"只到序号层面（面试高频追问点）

`verify_citations` 只检查 `1 ≤ n ≤ k`。它不检查"被引 chunk 是否真的支撑该句"，也不要求每个论断都有引用（P0-4 末行实测）。`snippet` 取的是 chunk 前 200 字符（`citations.py:78`），不一定是支撑句。`200` 也是写死的数值（Rule 8）。

**建议的最小加强**：按句拆分，要求每个含事实的句子至少带一个合法引用，否则整题判为"引用不足"并走重试；`snippet` 改为被引 chunk 中与该句重叠最多的那一句。这样 Citation precision 才有意义。至少要在 README 的已知限制里如实写"校验的是序号合法性，不是语义支撑"。

### P1-4　D3 验收从未在真实 LLM / 真实 embedding 下运行

- `grade` 完全依赖一次 LLM 判断。向量检索永远返回 k 条结果（没有相似度下限），不可回答题能否被拒掉，**只取决于 grade 提示词的严格程度**，目前没有任何真实数据。
- `FakeLLMProvider` 的 grade 是**关键词表**（`量子纠缠 / 火星移民 / 宇宙飞船`…，`provider.py:216-225`），所以 `test_agent`/`test_llm` 里"不可回答题被拒答"测的是假对象的关键词表，不是 grade 逻辑。
- PRD 说"D3 完成后就开始投递"。在投递前，至少对 5 道可回答题和 5 道不可回答题用真实 LLM 跑一遍 `cli ask`，把真实输出贴进 `docs/`，确认引用格式、拒答行为、步骤事件都符合预期。**这是目前最大的"未验证风险"。**

### P1-5　评测数据真实性的护栏缺失（AGENTS.md Rule 9）

`FakeLLMProvider` 与 `FakeEmbeddingProvider` 通过环境变量 `LLM_PROVIDER=fake` / `EMBEDDING_PROVIDER=fake` 即可启用，且生产模块里内置了 `[TEST_INVALID_CITATION]` 等魔法字符串和关键词规则。

- D5 的 `make eval` 如果在 fake 配置下运行，会产出看似合法、实为伪造的指标。
- `get_embedding_provider` 对未知取值（包括 PRD 里写的 `api`）会**静默回落到 local**（`embeddings.py:94-97`）。

**修法**：eval runner 启动时检测到 fake provider 直接退出并报错；把 Fake 实现移到 `tests/` 或 `apps/api/llm/fakes.py`；对未知 provider 取值抛错。同时 PRD 写的 `EMBEDDING_PROVIDER=local|api` 目前没有 `api` 实现，要么实现，要么在 PRD 里改成 `local|fake` 并注明。

### P1-6　Markdown 解析：代码围栏里的 `#` 被当成标题（实测）

`chunk_markdown`（`chunker.py:102-127`）不识别 ``` 围栏。实测：

```text
fence test: heading='Title'              content='intro text\n\n```python'
fence test: heading='this is a comment'  content='x = 1\n```\n\nafter'
```

围栏被从中间劈开，Python/Shell 注释被当成一级标题，面包屑被污染。技术文档里这是常见情形。

同类问题：

- **标题不进入索引文本**：`content` 和 `content_seg` 都不含标题，只有元数据里有。用户常用标题里的词提问，向量与全文都匹配不上；
- **小节不合并**：实测有 67、84、73 字符的碎 chunk，它们会占 Top-5 席位。

**修法**：识别围栏状态；入库时给 embedding 和 `content_seg` 前置标题文本（`content` 保持原文，以保证 `gold_snippet` 子串匹配）；合并过小的相邻小节。

### P1-7　契约漂移与 README 过度承诺（AGENTS.md Rule 4/9）

D2、D3 两个提交**没有修改** `docs/PRD.md`、`.env.example`、`README.md`、`docs/DECISIONS.md`。但 D3 已经改变了：

- 状态字段新增 `generate_retries`（PRD §8 的 State 清单没有）；
- 新增配置 `LLM_PROVIDER`、`LLM_TIMEOUT_SECONDS`、`MAX_GENERATE_RETRIES`、`FIXED_REFUSAL_TEXT`，`.env.example` 一个都没有；
- `README.md:9-10` 声称已有"SSE 流式回答"和"自动化离线评测"，实际上两者都不存在；`README.md:22` 的 `docker compose up -d` 只会启动数据库，没有 api/web 服务；
- `DECISIONS.md:15` 写"稳定性显著优于单路检索"，`:26` 写"杜绝幻觉"。这两句在没有评测数据和 grade 本身可错的前提下是断言，面试官会直接追问证据，同时有违 Rule 9 精神。

**修法**：补 PRD（State、配置项、provider 取值）、`.env.example`、README 的"当前进度/已知限制"，把 DECISIONS 里的结论性措辞改成"预期/待评测验证"。

---

## 4. 🟡 建议修复（P2）

| # | 问题 | 位置 / 证据 | 建议 |
|---|---|---|---|
| 1 | `run_agent(mode=...)` 的 `mode` 只写入 `runs`，检索永远是 hybrid（`nodes.py:59`）。传 `vector` 会"记录为 vector，实际跑 hybrid"。 | `runner.py:39`、`nodes.py:56` | D5 要对比三档，需要让 `mode` 真正影响检索，或删掉该参数。 |
| 2 | `/api/search` 默认 `k`：vector 取 20，hybrid 取 5（`search.py:51-55`）。直接对比同一问题的结果不公平，PRD D2 验收就是"可对比"。 | `routers/search.py` | 默认统一为 `final_top_k`，评测显式传 `k=5`。 |
| 3 | PRD §9 没有定义 vector-only 与 hybrid 两档如何产生"回答/引用/拒答"，Citation precision 与 Refusal accuracy 对它们无定义。 | `docs/PRD.md` §9 | D5 前在 PRD 里补一句基线定义（例如"检索后直接 generate，无 grade"），否则 runner 没法实现。 |
| 4 | 重复上传同名/同内容文件会产生重复 chunk，Top-5 被重复内容占满。 | `routers/documents.py:84-94` | 评测 runner 每次先清库；产品侧可按文件内容哈希去重（需改 schema，要走 Rule 4）。 |
| 5 | `init_db()` 失败只 `print`，应用照常启动，之后所有接口 500。`/api/health` 不检查数据库。 | `main.py:19-23`、`routers/health.py` | `health` 做一次 `SELECT 1`；生产配置下启动失败应直接退出。 |
| 6 | `Vector(512)` 写死，而配置里有 `embedding_dim`。改配置不会改列定义。 | `models.py:72` | 要么从配置读，要么删掉该配置项并注明。 |
| 7 | 没有 `Chunk(document_id, idx)` 唯一约束，`documents.status` 无 CHECK。无 Alembic，`create_all` 无法演进 schema。 | `models.py` | 一周内可接受。至少在 DECISIONS 记一条"schema 变更需删卷重建"。 |
| 8 | 删除文档用 ORM 级联，会把该文档所有 chunk（含 512 维向量）加载进内存再逐行删，而库里已有 `ON DELETE CASCADE`。 | `documents.py:127`、`models.py:47` | 在 relationship 上加 `passive_deletes=True`。 |
| 9 | pgvector HNSW 的 `ef_search` 默认 40；`/api/search` 允许 `k` 到 100（`search.py:21`），向量通道超过 40 条时可能返回不足。（按 pgvector 文档推断，本次未实测。） | `routers/search.py:21` | 上限收紧到 40，或查询前 `SET hnsw.ef_search`。 |
| 10 | 前台上传完文件后，服务器崩溃会让文档永远停在 `processing`；没有大小上限；上传后台任务与首次请求并发时，embedding 单例可能被初始化两次。 | `documents.py`、`embeddings.py:89-98` | 启动时把遗留的 `processing` 标为 `failed`；加一个最大上传体积配置；在 lifespan 里预热 embedding 模型（同时避免首问慢 10 秒以上）。 |
| 11 | 写死数值，违反 Rule 8：引用片段 `[:200]`、CLI 预览 `[:150]`、`connect_timeout: 2`、各函数签名里的 `k=20/60/5` 默认值。 | `citations.py:78`、`cli.py:76`、`session.py:19`、`retrieval.py` | 收进 `Settings`，函数签名默认值改为 `None`。 |
| 12 | 工程细节：`Makefile` 的 `lint` 调用 `ruff`，但 `ruff` 不在依赖/lockfile；`eval` 指向尚不存在的 `evals/runner.py`；`make test` 需要先 `make up`，文档未写；`.env.example` 缺 D3 新增项；`cli.py` 中途 `import`（第 47 行）并重复导入 `vector_search`。 | `Makefile`、`cli.py` | D4 前一并整理，并更新 AGENTS.md 的命令清单（该文件要求"保持最新"）。 |
| 13 | `FakeLLMProvider.generate` 靠 `"改写" in prompt_text or "rewrite" in prompt_text.lower()` 判断是否改写。若检索到的 chunk 内容里恰好含 "rewrite"（比如 URL rewrite 文档），生成会被误判成改写。 | `provider.py:195` | 随 P1-5 一起把 Fake 改成按调用类型而非内容分流。 |
| 14 | 向量查询未使用 bge 推荐的检索指令前缀。bge-small-zh-v1.5 不加也能用，且注释已说明。 | `embeddings.py:79-83` | 记为 D5 调参杠杆，不是缺陷。 |
| 15 | 依赖：`sentence-transformers` 会拉取 torch。在 Linux 镜像里默认可能带 CUDA 轮子，镜像体积和构建时间会很大；模型首次运行时从 HuggingFace 下载，在国内网络下可能失败。（未验证，D6 才会触发。） | `pyproject.toml`、`uv.lock` | D6 的 Dockerfile 里指定 CPU 轮子，并用 volume 缓存模型目录；README 写镜像源设置。 |

---

## 5. 🟢 可以忽略（当前阶段不值得花时间）

- 无登录、CORS 为 `*` 且 `allow_credentials=True`（`main.py:35-41`）：本机单用户演示，PRD 明确不做鉴权。如果将来公网部署再收紧。
- `docker-compose.yml` 里数据库口令是 `evidence/evidence`、端口 5432 对外：本地开发可接受。
- 没有 `apps/__init__.py`、`apps/api/__init__.py`（命名空间包）：当前 pytest 与 uvicorn 都能工作。
- `.txt` 被接受为上传格式（PRD 只写 md/pdf）：无害的小超范围。
- `DELETE` 返回 200 + JSON 而不是 204；`latency_ms` 用 `Float`：不影响契约使用。
- 默认 `DATABASE_URL` 用 `localhost`，在 Windows 上会先尝试 `::1`。本次失败的根因是数据库没启动，不是这个。需要时改成 `127.0.0.1` 即可。
- 提交粒度较粗（D1 一个提交 4255 行，D3 打包了 agent、LLM、runs）：个人项目可接受，下次拆开更利于回溯。
- 没有 `/api/chat`：D4 的任务，不算 D3 缺陷。

---

## 6. D4 前的风险清单（在 P0/P1 之外）

1. **POST + SSE 不能用浏览器原生 `EventSource`**（它只支持 GET）。前端要用 `fetch` + `ReadableStream` 自己解析 `event:`/`data:`。DECISIONS.md 的 SSE 条目没提这点，面试时会被问到。
2. **Next.js 的 `rewrites` 代理可能缓冲/压缩 SSE**，导致"流"变成"一次性到达"。要么前端直连 FastAPI（已有 CORS），要么确认代理不缓冲。
3. **图是同步的**：`compiled_graph.invoke` 与 `OpenAILLMProvider` 都是阻塞调用。在 `async def` 路由里直接调用会堵事件循环。需要同步路由 + 线程池，或 `iterate_in_threadpool`。
4. **Session 生命周期**：`AgentNodes` 持有 `self.db`。流式响应期间要确认 `Depends(get_db)` 的会话没有被提前关闭，并且不能跨线程共享同一个 Session。
5. **步骤事件**：现在每个节点把整个 `steps` 列表复制后返回，没有 reducer。要做实时 `step` 事件，应使用 `graph.stream(..., stream_mode="updates")`，让节点返回增量。
6. **客户端断开**：LLM 请求不会随连接断开而取消，需要决定是否忽略。
7. **模型冷启动**：第一次提问才加载 bge 模型，首问会明显变慢，演示时要预热（见 P2-10）。
8. **`done` 事件缺 `answer`**：与 P0-1 同一个决定一起处理。

---

## 7. 面试官可能深挖的问题（按风险排序）

| 问题 | 目前能诚实回答的程度 | 差距与建议 |
|---|---|---|
| "overlap 50 怎么实现的？为什么是 50？" | **答不上**：主路径没有重叠。 | 修 P0-3 后才能讲。 |
| "你怎么证明 hybrid 比 vector 好？" | 目前**没有数据**。语料 15 个 chunk、题目泄漏。 | 做 P1-2，D5 用真实评测数字回答。 |
| "引用是'可核对'的，核对的是什么？" | 核对序号是否在检索范围内，不核对语义支撑，也不要求每句都有引用。 | 做 P1-3，或明确写进已知限制。 |
| "模型输出 `[1,2]` 会怎样？" | 会被误判成无引用，重试后拒答。 | 修 P0-4。 |
| "grade 全靠 LLM，它错了怎么办？拒答准不准？" | 没有任何真实数据；Fake 的 grade 是关键词表。 | 做 P1-4，D5 单独报告 Refusal accuracy 与误拒率。 |
| "为什么中文全文检索要 jieba 预分词？OR 查询、停用词呢？" | 前半能答好；后半有 P1-1 的缺陷。 | 加停用词过滤并用评测验证。 |
| "ts_rank_cd 和 BM25 有什么区别？" | 要能说出：`ts_rank_cd` 看覆盖密度/邻近度，无 IDF。 | 把 P1-1 的分析内化。 |
| "RRF 为什么用 k=60？不同通道分数怎么融合？" | 能答好，且有数值测试。 | 无。 |
| "流式输出时，引用校验怎么做？" | 现在**没有方案**。 | 修 P0-1。 |
| "LangGraph 的 state 和条件边怎么设计的？最多循环几次？为什么 State 里多了 `generate_retries`？" | 能答好，且我实测过拓扑；但 PRD 没同步。 | 修 P1-7。 |
| "SSE 为什么不用 WebSocket？POST 能用 EventSource 吗？" | 第一问可答；第二问 DECISIONS 没覆盖。 | 补一句，见第 6 节第 1 条。 |
| "你的测试能证明什么？为什么这些 agent 测试需要数据库？" | 当前答案不好看。 | 修 P0-2。 |
| "LLM 抽象层为什么直接用 httpx？超时和重试呢？" | 能答前半；失败语义缺失。 | 修 P0-5。 |

---

## 8. 与 AGENTS.md 的符合性

| 规则 | 结论 |
|---|---|
| 1 单仓库单架构 | 符合 |
| 2 LLM / embedding 走抽象层 | 符合 |
| 3 密钥只在环境变量 | 符合（`.env` 已忽略，`.env.example` 已提交；缺项见 P1-7） |
| 4 不静默改契约，改了要同步 PRD | **不符合**：D3 增加状态字段、配置项、provider 取值，PRD 未更新（P1-7）。 |
| 5 保持条件循环 | 符合（实测） |
| 6 服务端校验引用 | 部分符合：做了序号校验，但有盲区（P0-4、P1-3） |
| 7 拒答不调用 LLM | 符合（实测） |
| 8 阈值走配置 | 大部分符合，少数写死（P2-11） |
| 9 指标只来自真实运行 | 目前没有任何指标，没有造假；但 README/DECISIONS 有未经验证的断言，且缺少对 Fake provider 的评测护栏（P1-5、P1-7） |
| 10 不超范围 | 基本符合（`.txt` 等无害小项） |
| 11 核心函数有 docstring | 符合；但 `chunker.py` 的模块说明与实际行为不一致（P0-3） |
| 测试要求：agent 测试用假 LLM 且离线 | **不符合**（P0-2）；"upload→ingest→search 集成测试"存在，但库不可达时静默 skip，无法保证它真的跑过 |

---

## 9. 本次审计实际运行了什么

仓库外的临时脚本（位于 `C:\Users\ASUS\.gemini\antigravity\brain\1d841a38-162c-435a-8ff5-e7c8a83083cf\scratch\`，未写入仓库）：

- `audit_probe.py`：对三份语料调用 `chunk_markdown`，统计 chunk 数量与长度；检查 20 条 `gold_snippet` 是否落在单个 chunk；用周期文本和非周期文本检验重叠；检验代码围栏与空标题；打印 jieba 对查询的切词结果。
- `audit_probe2.py`：用 `patch(hybrid_search)` + `FakeLLMProvider` 跑完整 LangGraph（无需数据库），检验正常路径、拒答路径的 LLM 调用序列、多种引用写法、半数论断无引用、grade 抛异常。

另外运行了 `uv run --frozen pytest tests/ -q -p no:cacheprovider`，结果见第 1 节。

**未覆盖**：真实 Postgres/pgvector 行为、真实 embedding 模型、真实 LLM、PDF 含文本路径、Docker。凡依赖这些的判断，已在文中标注"静态分析"或"未验证"。

---

## 10. 建议的修复顺序

| 顺序 | 事项 | 预估 |
|---|---|---|
| 1 | P0-2 把 agent 测试改成打桩检索，集成类单独标记 | 0.5h |
| 2 | P0-3 修分块重叠 + 重写测试；P1-6 顺手处理代码围栏与标题前置 | 1.5h |
| 3 | P0-4 引用归一化与文本清理收敛 | 1h |
| 4 | P0-5 失败语义 + `OpenAILLMProvider` 的 MockTransport 测试 | 1.5h |
| 5 | P0-1 决定流式方案，更新 PRD（先写文档，再写 D4 代码） | 0.5h |
| 6 | P1-7 同步 PRD / `.env.example` / README / DECISIONS | 0.5h |
| 7 | P1-4 真实 LLM 冒烟（10 题），把结果存档 | 1h |
| 8 | P1-5 评测护栏与 Fake 移位 | 0.5h |
| 9 | P1-1 停用词过滤；P1-2 换语料、手写题（可放到 D5 早段） | D5 |

**D4 开工门槛**：第 1–6 项完成，且 `make test` 在**只启动了数据库、库为空**的环境里全绿，在**没有数据库**的环境里 agent/引用/分块相关测试仍然全绿。
