# EvidenceOS 评测报告 (Evaluation Report)

> **生成时间**: 2026-10-05 15:52:52
> **评测数据**: `evals/dataset.jsonl` (共 25 题: 20 道可回答, 5 道不可回答，受控评测集)
> **评测语料**: `evals/corpus/` (3 篇受控技术文档: FastAPI, pgvector, RAG Hybrid，共 15 个切片)
> **LLM 运行配置**: Provider=openai, Model=deepseek-chat

## 1. 三档模式综合指标对比

| 指标 (Metric) | 稠密向量 (Vector-Only) | 混合检索 (Hybrid RRF) | 智能体回路 (Hybrid + Agent) |
| :--- | :---: | :---: | :---: |
| **Hit@5 (召回率)** | 100.0% | 100.0% | 100.0% |
| **Gold-snippet Citation Precision** | N/A | N/A | 96.7% |
| **Refusal Accuracy (拒答准确度)** | 80.0% | 80.0% | 100.0% |
| ↳ *Unanswerable Refusal Rate* | 0.0% | 0.0% | 100.0% |
| ↳ *Answerable Rejection Rate* | 0.0% | 0.0% | 0.0% |
| **Latency p50 (中位数耗时)** | 12.46 ms | 15.46 ms | 5374.92 ms |
| **Latency p95 (长尾耗时)** | 13.56 ms | 18.14 ms | 12418.67 ms |

## 2. 评测指标与口径说明

1. **Hit@5**: 检索返回的前 5 个候选切片中，是否存在至少一个切片包含该题标注的 `gold_snippet`（仅针对 20 道可回答题目统计）。
   - `hybrid+agent` 的 Hit@5 **基于 Agent 最终检索状态（包含改写重试后的切片列表）**，真实体现改写回路对证据召回的修正效果。
   - **区分度说明**：在当前受控 3 篇文档、15 个分块的 corpus 规模下，Vector-only、Hybrid 与 Hybrid+Agent 均达到 100.0% Hit@5，因此该指标在当前小型基准集上没有显著区分度。
2. **Gold-snippet Citation Precision**: 仅针对 `hybrid+agent` 模式统计。考察模型最终回答中**所有通过服务端校验的合法引用切片**，其中实际包含 `gold_snippet` 的比例；若发生拒答或无引用则计 0.0，最后取宏平均（Macro-Average）。
3. **Refusal Accuracy**: 全局判定准确度。考察 5 道不可回答题目是否触发拒答，同时考察 20 道可回答题目是否未发生误拒：
   $$\text{Refusal Accuracy} = \frac{N_{\text{正确拒答}} + N_{\text{正确未拒}}}{25}$$
   - **纯检索说明**：Vector-only 与 Hybrid 属于纯检索（retrieval-only）模式，本身不具备对证据充足性进行审查与拒答的能力（no refusal capability），在当前评测体系下对所有 25 道题均默认未拒答，因此 5 道不可回答题目全部记为未拒答，准确度为 80.0% (20/25)。
4. **Latency Percentiles (p50 / p95)**: 采用无歧义线性插值法（Linear Interpolation，与 NumPy `method='linear'` 完全一致）计算真实端到端耗时分位数。
   - 真实商业 API（如 DeepSeek）端到端耗时包含外网网络传输与模型生成耗时；fake-provider 的极低延迟仅用于本地流程验证，不得作为正式 Agent 性能结论。

## 3. 架构表现与归因分析

### (1) 纯检索 vs 智能体条件回路 (Agent Loop)
- **证据审查与受控拒答**: 纯检索模式（Vector/Hybrid）没有 refusal capability，无法对召回片段的相关性进行语义判断；Hybrid+Agent 依托 Grade 节点的结构化判定与最多 2 次 Rewrite 条件循环，在面对不可回答问题时能稳定识别证据缺失并进入 Refuse 节点，输出固定拒答文本。
- **服务端引用合法性核对 (Index-level Verification)**: 模型生成的引用标记必须通过服务端物理校验（对账本次召回切片），虚构或越界的引用标记会被过滤，保障引用的真实可溯源性。本机制未运行自然语言推理（NLI）语义蕴含模型，不代表对文本事实的绝对真伪证明。

## 4. 逐题异常与偏差分析 (Per-Question Failure & Anomaly Analysis)

| 题号 (ID) | 问题概要 | 异常类型 | 详细情况与引用切片 |
| :--- | :--- | :--- | :--- |
| **q15** | PostgreSQL 中通过哪个函数基于词覆盖密度进行全文相... | Citation Precision 未达 100% (33.3%) | 引用的切片中存在未包含 gold_snippet '配合 `ts_rank_cd` 函数基于词覆盖密度进行词法相关度打分' 的切片。引用切片: [1] doc=postgresql_pgvector.md chunk_id=4fbac9f0, [3] doc=rag_hybrid_retrieval.md chunk_id=8e08c055, [4] doc=rag_hybrid_retrieval.md chunk_id=f287b9c5 |
