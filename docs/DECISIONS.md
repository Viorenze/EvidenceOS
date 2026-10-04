# Architecture Decisions — EvidenceOS

本文档记录 EvidenceOS 的核心技术选型原因，便于面试时追溯设计权衡（Trade-offs）。

## 1. 为什么选择 PostgreSQL + pgvector 而不是独立的向量数据库（如 Milvus / Qdrant）？

- **单一数据源（Single Source of Truth）**：元数据（文件名、页码、标题）、文本内容、分词切分、全文检索向量和稠密向量全部存储在同一个数据库中，天然保证事务一致性（ACID）。删除文档时级联删除 Chunks，不会产生孤儿向量。
- **运维复杂度低**：无需维护额外的独立向量数据库集群或同步管道（Out-of-sync 问题），大幅降低部署和自测门槛，单机 `docker-compose.yml` 即可跑起生产级环境。
- **混合检索友好**：PostgreSQL 原生同时支持 `tsvector`（全文检索）与 `pgvector`（HNSW/IVFFlat 向量检索），可以在同一个 SQL 引擎或事务内实现多路召回与融合。

## 2. 为什么选择混合检索（Hybrid Search + RRF）而不是纯向量检索？

- **纯向量检索的短板**：对精准关键词、专有名词、错误码、配置项名称（如 `EMBEDDING_PROVIDER`、`ts_rank_cd`）等缺乏强匹配能力，语义相似容易将不同但名字相近的配置混为一谈。
- **全文检索的短板**：无法理解同义词、泛化查询及自然语言意图。
- **RRF（Reciprocal Rank Fusion）优势**：无参数融合算法，不需要对向量余弦相似度分数与 BM25/ts_rank 分数做复杂的归一化校准，仅依据排名的倒数加权，在技术文档场景下稳定性显著优于单路检索。

## 3. 为什么全文检索选择 jieba 预分词存入 `content_seg` 并配合 `to_tsvector('simple', ...)`？

- **PostgreSQL 默认英文分词缺陷**：Postgres 内置的全文检索分词器（如 `english`）默认按空格及标点切分，对于无空格连写的中文句子几乎切不出有效 token，直接导致中文全文检索失效。
- **插件独立性**：虽然有 `zhparser` 或 `pg_jieba` 扩展，但在许多轻量 Docker 镜像或受限环境（如 Windows、标准 pgvector 镜像）中不易编译安装。
- **应用层预分词方案**：入库时通过 Python 端权威的 `jieba` 分词库将中文句子分词为空格隔开的词串存入 `content_seg`，再使用 PostgreSQL 自带的 `'simple'` 分词字典直接构建 GIN 倒排索引。既拥有高质量中文切词能力，又保持数据库镜像的纯净与通用。

## 4. 为什么 Agent 选择 LangGraph 并设计有条件循环而不是简单线性 Chain？

- **证据真实性的刚性约束**：传统 RAG（如线性 Chain）检索后直接注入 Prompt 生成，如果检索结果不足或偏离，模型极易产生幻觉瞎编。
- **循环改写与拒绝机制**：引入 Grade 节点判断证据充分性。如果不足，根据缺失信息重写 Query 并重新检索（最多循环 2 次）。如果依旧不足，坚决流向 Refuse 节点输出固定拒答文案，杜绝幻觉。
- **状态流转可追溯**：LangGraph 的 State 清晰记录了每一步的检索、评判结果与重写历史，天然适配前端逐步展示（SSE Step 事件）以及离线评测。

## 5. 为什么通信选择 SSE（Server-Sent Events）而不是 WebSocket？

- **单向流式天然匹配**：问答场景是典型的客户端发一次请求（POST）、服务端单向持续吐出 Token 与 Agent Step 事件，不需要服务端到客户端的双向实时交互。
- **协议简单轻量**：基于标准 HTTP/1.1 与 HTTP/2，天然穿透网关与防火墙，无需维护复杂的 WebSocket 握手、心跳维持与断线重连协议栈。
- **事件结构化**：SSE 原生支持 `event` 与 `data` 划分，方便分别派发 `step`、`token`、`citations`、`done`、`error` 等结构化数据。
