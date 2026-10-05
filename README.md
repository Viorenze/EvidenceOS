# EvidenceOS — 可核对引用的技术问答系统

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Frontend-Next.js%2014-black.svg)](https://nextjs.org/)
[![PostgreSQL + pgvector](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Tests](https://img.shields.io/badge/Tests-82%20passed%2C%202%20skipped-brightgreen.svg)]()

> **EvidenceOS** 是一个面向技术文档、具备严谨证据审查与**服务端引用核对**机制的端到端 AI 知识库问答系统。
> 核心原则：**宽度精简，深度聚焦——混合检索、有条件循环 Agent、服务端引用核验、可复现基准评测。**

---

## 1. 核心架构与系统流程 (Architecture)

```mermaid
flowchart TD
    subgraph Ingestion["文档入库流 (Ingestion Pipeline)"]
        doc["上传文档 (.md / .pdf)"] --> chunker["分级标题感知分块 (Markdown Headings / PDF Pages)"]
        chunker --> jieba["jieba 应用层预分词 (content_seg)"]
        chunker --> bge["本地 BGE-small-zh-v1.5 (512 dims)"]
        jieba --> pg[("PostgreSQL 16 + pgvector<br/>• to_tsvector('simple', content_seg) GIN 索引<br/>• vector(512) HNSW 索引")]
        bge --> pg
    end

    subgraph Serving["智能体问答回路 (LangGraph Agent Loop)"]
        q["用户输入问题"] --> ret["retrieve 节点<br/>两路召回 + RRF (k=60) 融合"]
        pg -.-> ret
        ret --> grade{"grade 节点 (LLM 结构化输出)<br/>证据是否充足？"}

        grade -- "证据不足 (Sufficient: False)" --> check_rw{"重写次数 < 2 ?"}
        check_rw -- "是" --> rewrite["rewrite 节点<br/>根据 missing 扩充关键词"]
        rewrite --> ret
        check_rw -- "否 (仍不足)" --> refuse["refuse 节点<br/>固定拒答文案 (无据不编造)"]

        grade -- "证据充足 (Sufficient: True)" --> gen["generate 节点<br/>严格基于片段标号 [n] 回答"]
        gen --> verify{"verify_citations 节点<br/>服务端白名单校验 [n] 是否在 Top-K"}

        verify -- "无任何有效引用" --> retry{"重试次数 < 1 ?"}
        retry -- "是" --> gen
        retry -- "否" --> refuse

        verify -- "校验通过 / 清洗非法标号" --> stream["Verify-then-Stream (SSE 推流)<br/>event: token / citations / done"]
        refuse --> stream
    end

    subgraph Client["Web 前端交互 (Next.js 14)"]
        stream --> ui["Chat 页面<br/>1. 实时 LangGraph 思考步骤面板<br/>2. 逐 Token 流式答案渲染<br/>3. 点击 [n] 引用徽标打开 ChunkModal 对话框原文对账"]
    end
```

---

## 2. 核心技术特性 (Core Features)

1. **结构化分块与标题上下文绑定**：
   - 追踪 Markdown 分级标题（`# H1 > ## H2 > ### H3`），将完整的面包屑元数据绑定至每一个分块，防止深层代码块脱离上下文。
   - 目标切片大小 400～500 字符，保留 50 字符滑动重叠，避免切断跨句上下文。
2. **应用层分词与单库检索架构**：
   - 统一使用 PostgreSQL + pgvector 存储元数据、正文、分词和向量，天然具备 ACID 事务一致性。
   - 应用层使用 `jieba` 分词生成空格分隔的 `content_seg`，配合内置 `to_tsvector('simple', ...)` 与 GIN 索引，规避了在数据库容器中编译第三方 C 插件的运维复杂性。
3. **两路召回与互惠排名融合 (RRF)**：
   - 向量通路基于余弦距离召回语义相近候选（Top 20）；全文通路基于 `ts_rank_cd` 词覆盖密度打分召回精确匹配候选（Top 20）；
   - 使用学术界与工业界通用的 RRF 平滑公式（$k=60$）无参数融合出 Top 5 核心切片。
4. **LangGraph 有条件循环 Agent 回路**：
   - 严禁传统的线性 Chain 模式；引入 `Grade` 节点审查检索切片是否足以支撑回答；若证据不足，根据缺失点自动触发 `Rewrite` 节点补充技术关键词重试（最多 2 次）；
    - 若重试后仍不足，坚决流向 `Refuse` 节点，输出固定拒答文案，避免无据编造。
5. **服务端引用强校验（Server-Side Citation Verification）**：
   - 绝不信任 LLM 随意生成的引用标记。服务端逐一提取并验证 `[n]`、`【n】` 或 `[n, m]` 是否严格落在本次检索到的切片范围内；
   - 自动过滤越界标记（如不存在的 `[99]`），且保护代码中的数组下标（如 `data[0]`）；
   - 每一个引用徽标均绑定真实切片 ID，支持前端一键展开查看完整原始切片与章节路径；
   - **机制边界说明**：服务端引用校验验证的是引用标记与本次检索候选集的物理对应关系，不执行昂贵的自然语言推理（NLI）语义蕴含检验，不代表对每句话建立了绝对语义证明。
6. **先校验后推流（Verify-then-Stream）SSE 架构**：
   - 执行阶段实时推送 `event: step` 暴露后台思考状态；
   - 完整生成并通过引用核验后，流式向客户端发送 `event: token`；
   - **设计权衡**：系统接受较高的首字等待时间（TTFT，约等于整图执行耗时），以在答案推向客户端前完成服务端的引用有效性核验，防止向前端推送非法或悬空的引用标号，并在证据不足时受控拒答。该设计防止了悬空引用产生，但 LLM 生成本身并不具备确定性，亦不保证回答中所有陈述在语义层面的绝对无误。

---

## 3. 真实评测基准数据 (D5 Benchmark Report)

> **数据来源**：本基准测试数据全部来自 `evals/runner.py` 在真实 WSL2 PostgreSQL + pgvector + 真实 DeepSeek 模型上的完整运行结果（绝无手工虚构或占位数据），完整报告详见 [`reports/eval.md`](reports/eval.md)。
> **评测语料**：`evals/corpus/` 3 篇受控技术文档（基于 FastAPI, pgvector, RAG 核心主题合成整理），共 15 个切片。
> **评测题目**：`evals/dataset.jsonl` 共 25 题（配套评测题集，含 20 道可回答题与 5 道显式不相关题）。

| 评测指标 (Metric) | 稠密向量 (Vector-Only) | 混合检索 (Hybrid RRF) | 智能体回路 (Hybrid + Agent) |
| :--- | :---: | :---: | :---: |
| **Hit@5 (召回率)** | 100.0% | 100.0% | 100.0% |
| **Gold-snippet Citation Precision** | *N/A* | *N/A* | **96.7%** |
| **Refusal Accuracy (拒答准确度)** | 80.0% | 80.0% | **100.0%** |
| ↳ *Unanswerable Refusal Rate* | 0.0% | 0.0% | **100.0%** |
| ↳ *Answerable Rejection Rate* | 0.0% | 0.0% | **0.0%** |
| **Latency p50 (中位数端到端耗时)** | 12.46 ms | 15.46 ms | 5,374.92 ms |
| **Latency p95 (长尾端到端耗时)** | 13.56 ms | 18.14 ms | 12,418.67 ms |

### 评测结果核心发现与指标说明：
1. **Hit@5 饱和性与混合检索定位**：
   - 在当前受控的 3 篇文档、15 个分块的小型语料规模下，三种模式在 20 道可回答题目上的 Hit@5 均达到 100.0%（Hit@1 均为 90.0%）。
   - 因为语料规模小且召回打满，发生了天花板饱和效应，当前基准测试尚未在数据上建立混合检索优于纯向量检索的准确率优势；混合检索的核心价值在于工程设计上同时融合语义泛化（向量）与专有名词/配置精确匹配（全文）的双路信号。
2. **Gold-snippet Citation Precision (96.7%)**：
   - 衡量模型最终回答中**所有通过服务端校验的合法引用切片**中，实际包含标注 `gold_snippet` 的比例；
   - 在 20 道可回答题目中，19 道题目的精度为 100%，唯独 **`q15`**（*PostgreSQL 中通过哪个函数基于词覆盖密度进行全文相关度打分？*）单题精度为 33.3%（1/3）：模型回答正确引用了包含答案的切片 `[1]`（`ts_rank_cd`），同时综合引用了另外 2 个阐述稀疏检索机制与 RRF 算法的切片 `[3]` 和 `[4]`，宏平均统计为 96.7%。
3. **拒答能力差异 (Refusal Accuracy)**：
   - 纯检索模式（Vector-Only / Hybrid）本身属于 retrieval-only，不具备对证据充足性进行审查与拒答的能力（no refusal capability），在评测定义下默认未拒答，导致 5 道不可回答题目全部被判定为未拒答，整体准确度恒为 80.0%（20/25）；
   - Hybrid+Agent 依托 Grade 节点的结构化判定与 Rewrite 条件循环，成功将 5 道不可回答题目 100% 拒答，且 20 道可回答题目误拒率为 0.0%。
4. **延迟差异归因**：
   - 纯检索模式仅需本地 CPU 向量计算与 Postgres SQL 查询，耗时仅 12～18 ms；
   - Hybrid+Agent 的耗时（p50 ~5.37s, p95 ~12.42s）主要由真实商业 LLM API（DeepSeek）的公网网络往返、多轮条件判定回路（Grade + Rewrite）以及串行 Token 生成耗时决定。

---

## 4. 快速开始与可复现指南 (Quick Start)

本项目支持本地 Docker 数据库基础设施一键启动，配合 uv 与 npm 本地运行全栈应用，并提供离线单元测试（全量 Mock 确定性执行）与在线基准测试（连接真实 LLM）双模验证。

### 1. 准备环境与依赖
* 安装 [Docker Desktop](https://www.docker.com/)
* 安装 Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)（推荐包管理器）
* 安装 Node.js 18+ 与 npm

```bash
# 克隆仓库
git clone <repository-url>
cd EvidenceOS

# 复制环境变量配置
cp .env.example .env
```

在 `.env` 中按需填入配置（如使用真实模型，填入 `LLM_API_KEY`；如做离线开发，设置 `LLM_PROVIDER=fake` 即可完全免 Key 运行）：
```ini
DATABASE_URL=postgresql+psycopg://evidence:evidence@127.0.0.1:5432/evidenceos
EMBEDDING_PROVIDER=local
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_api_key_here
LLM_MODEL=deepseek-chat
```

### 2. 启动数据库服务
```bash
# 启动 PostgreSQL 16 + pgvector 容器
make up
# 或 docker compose up -d
```

### 3. 初始化评测语料并运行评测基准
```bash
# 显式入库 3 篇受控评测语料 (15 chunks)
make setup-eval

# 运行三档对比评测基准 (自动输出并更新 reports/eval.md)
make eval
```

### 4. 启动后端 API 与前端 Web
```bash
# 终端 1：启动 FastAPI 后端服务 (端口 8000)
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

# 终端 2：启动 Next.js 前端服务 (端口 3000)
cd apps/web
npm install
npm run dev
```

打开浏览器访问 `http://localhost:3000`：
* **Documents 页面 (`/documents`)**：上传技术文档、查看分块入库进度及分块数；
* **Chat 页面 (`/`)**：提问、查看实时思考回路展开、流式接收答案、点击 `[n]` 徽标在 ChunkModal 对话框查看原始切片对账。

### 5. 运行完整自动化测试套件
```bash
# 运行自动化测试套件 (82 passed, 2 skipped；82 个单元测试完全离线确定性执行，2 个集成测试在无本地数据库时自动跳过)
make test
# 或 uv run pytest -v
```

---

## 5. 项目结构 (Project Structure)

```text
EvidenceOS/
├── apps/
│   ├── api/                     # FastAPI 后端服务
│   │   ├── agent/               # LangGraph 状态图定义 (state, nodes, graph, runner, citations)
│   │   ├── db/                  # SQLAlchemy 数据模型 (documents, chunks, runs) 与会话管理
│   │   ├── llm/                 # LLM 提供商抽象层 (OpenAI-compatible HTTP & FakeLLM)
│   │   ├── rag/                 # RAG 核心算法 (heading-aware chunker, BGE embedding, jieba tsvector, RRF)
│   │   ├── routers/             # API 路由 (documents, search, chunks, chat SSE)
│   │   ├── config.py            # 全局配置管理 (基于 pydantic-settings)
│   │   └── main.py              # FastAPI 应用入口与中间件配置
│   └── web/                     # Next.js 14 前端单页应用
│       ├── src/app/             # App Router 页面 (chat 页面, documents 页面)
│       └── src/components/      # UI 组件 (Header, ChunkModal 对话框, SSE 客户端流解析器)
├── evals/                       # 评测基准
│   ├── corpus/                  # 3 篇受控技术文档语料 (FastAPI, pgvector, RAG Hybrid)
│   ├── dataset.jsonl            # 25 道受控评测问题 (20 道可回答 + 5 道不可回答)
│   └── runner.py                # 评测执行脚本 (计算 Hit@5, Citation Precision, Refusal Acc, p50/p95)
├── reports/
│   └── eval.md                  # D5 真实生成的基准评测报告
├── tests/                       # 自动化测试套件 (82 passed, 2 skipped)
│   ├── test_agent.py            # Agent 条件边、节点及持久化测试 (解耦 Mock)
│   ├── test_chat.py             # Chat SSE 协议与 Verify-then-Stream 测试
│   ├── test_chunker.py          # 分块有效重叠与代码块保护测试
│   ├── test_citations.py        # 引用提取、清洗与合法性核对测试
│   ├── test_eval.py             # 评测指标算法、零除保护与分位数边界测试
│   └── test_integration_pipeline.py  # 真实 PostgreSQL 入库与检索全链路集成测试
├── docker/                      # Docker 初始化脚本 (init.sql)
├── docs/                        # 设计与架构决策文档 (PRD.md, DECISIONS.md)
├── docker-compose.yml           # pgvector 容器编排
├── Makefile                     # 标准化命令接口 (make up, make test, make eval)
└── pyproject.toml               # Python 项目依赖与 pytest 配置
```

---

## 6. 技术决策与权衡 (Design Decisions & Limitations)

详见 [`docs/DECISIONS.md`](docs/DECISIONS.md)，核心面试阐述点：

1. **单库架构优势（PostgreSQL + pgvector）**：
   - 避免独立向量数据库与关系数据库之间的双写不一致问题（孤儿向量）。删除文档时级联物理删除关联 Chunks；同时原生支持 GIN 全文检索与 HNSW 向量索引。
2. **混合检索必要性（Hybrid + RRF）**：
   - 纯稠密向量检索侧重语义相似度，全文检索（jieba + tsvector）侧重专有名词与精确符号匹配，RRF 提供无参数平滑融合。在当前 15-chunk 微型语料库中二者均发生 Hit@5 饱和，当前数据未直接证明精度差异，但架构上消除了单一检索通路的单点盲区。
3. **Verify-then-Stream 权衡**：
   - 核心系统承诺是“可核对引用，有据可依”。如果 LLM 边生成边直接推流，非法或越界的引用标号会直接暴露给前端；系统接受较高的首字等待时间（TTFT，约等于整图执行耗时），在答案推向客户端前完成服务端的引用索引核对与清洗。此机制防止了悬空引用的产生，但不代表大模型生成本身具有确定性，亦不保证文本层面的绝对事实正确性。
4. **引用核验范围边界（Non-Goal）**：
   - 服务端引用校验保证引用索引严格落在本次检索到的切片范围内，剔除模型编造的越界标号，防止悬空引用；系统聚焦于引用编号与切片集合的物理对账，未运行昂贵的自然语言推理（NLI）语义蕴含模型，引用核验不代表对每个事实陈述提供了语义层面的真伪证明。
5. **流式取消与 Abort 边界**：
   - 前端点击 Stop 触发客户端 `AbortController`，立即断开 SSE 流并重置界面状态；后端检测到底层连接断开后终止后续 Agent 节点调度，但已发出的单次上游 LLM 阻塞式 HTTP 请求依赖网络返回或超时，不承诺物理中断外部模型提供商的后台算力计算。

---

## 7. 3 分钟面试现场演示路径 (Demo Script)

1. **第 1 分钟：语料库入库与分块感知**
   - 访问 `http://localhost:3000/documents`，展示已入库的技术文档列表与切片数。
   - 现场上传一份新的技术 Markdown 文档，后台自动异步触发分级标题解析、jieba 中文切词与 BGE 向量生成，页面自动刷新为 `ready` 状态。
2. **第 2 分钟：严谨问答、实时思考回路与原文对账**
   - 切换至 `http://localhost:3000`，提问：`FastAPI 如何做依赖注入？`
   - 展示前端折叠面板动态展示 LangGraph 思考状态（`retrieve` → `grade: Sufficient: True` → `generate` → `verify_citations`）；
   - 展示答案逐字流式渲染，文末附带清晰的引用徽标 `[1]`；
   - 点击徽标 `[1]`，弹出 `ChunkModal` 原文对话框，核对该引用的来源文件、章节面包屑（`FastAPI 核心技术指南 > 依赖注入系统`）以及完整切片文本。
3. **第 3 分钟：不可回答问题的受控拒答与评测对账**
   - 提问超范围问题：`FastAPI 如何原生配置接入 Apollo GraphQL 订阅服务器？`
   - 观察思考面板展现 9 个步骤：第 1 次检索不足 → 第 1 次改写重试 → 第 2 次改写重试 → 最终触发 `refuse` 节点；
   - 页面渲染固定拒答文案，避免无据编造；
   - 切换至终端执行 `make eval`，现场跑出三档对比数据，打开 [`reports/eval.md`](reports/eval.md) 结合 `q15` 案例解释指标定义与技术归因。
