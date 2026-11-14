# Architecture Decisions — EvidenceOS

本文档记录 EvidenceOS 的核心技术选型原因，便于面试时追溯设计权衡（Trade-offs）。

## 1. 为什么选择 PostgreSQL + pgvector 而不是独立的向量数据库（如 Milvus / Qdrant）？

- **单一数据源（Single Source of Truth）**：元数据（文件名、页码、标题）、文本内容、分词切分、全文检索向量和稠密向量全部存储在同一个数据库中，天然保证事务一致性（ACID）。删除文档时级联删除 Chunks，不会产生孤儿向量。
- **运维复杂度低**：无需维护额外的独立向量数据库集群或同步管道（Out-of-sync 问题），大幅降低部署和自测门槛，单机 `docker-compose.yml` 即可跑起本地 PostgreSQL + pgvector 基础设施。
- **混合检索友好**：PostgreSQL 原生同时支持 `tsvector`（全文检索）与 `pgvector`（HNSW/IVFFlat 向量检索），可以在同一个 SQL 引擎或事务内实现多路召回与融合。

## 2. 为什么选择混合检索（Hybrid Search + RRF）而不是纯向量检索？

- **纯向量检索的短板**：对精准关键词、专有名词、错误码、配置项名称（如 `EMBEDDING_PROVIDER`、`ts_rank_cd`）等缺乏强匹配能力，语义相似容易将不同但名字相近的配置混为一谈。
- **全文检索的短板**：无法理解同义词、泛化查询及自然语言意图。
- **RRF（Reciprocal Rank Fusion）优势**：无参数融合算法，不需要对向量余弦相似度分数与 BM25/ts_rank 分数做复杂的归一化校准，仅依据排名的倒数加权，在技术文档场景下综合两路排序信号。
- **评测基准边界注记**：在当前受控 15-chunk 极小语料库中，纯向量与混合检索均达到 100% Hit@5（天花板饱和），本测试未在数值上证明混合检索的准确度提升；混合检索选型基于符号精确匹配与语义泛化的互补性理论设计，而非微型基准的刷榜产物。

## 3. 为什么全文检索选择 jieba 预分词存入 `content_seg` 并配合 `to_tsvector('simple', ...)`？

- **PostgreSQL 默认英文分词缺陷**：Postgres 内置的全文检索分词器（如 `english`）默认按空格及标点切分，对于无空格连写的中文句子几乎切不出有效 token，直接导致中文全文检索失效。
- **插件独立性**：虽然有 `zhparser` 或 `pg_jieba` 扩展，但在许多轻量 Docker 镜像或受限环境（如 Windows、标准 pgvector 镜像）中不易编译安装。
- **应用层预分词方案**：入库时通过 Python 端权威的 `jieba` 分词库将中文句子分词为空格隔开的词串存入 `content_seg`，再使用 PostgreSQL 自带的 `'simple'` 分词字典直接构建 GIN 倒排索引。既拥有高质量中文切词能力，又保持数据库镜像的纯净与通用。

## 4. 为什么 Agent 选择 LangGraph 并设计有条件循环而不是简单线性 Chain？

- **证据真实性的刚性约束**：传统 RAG（如线性 Chain）检索后直接注入 Prompt 生成，如果检索结果不足或偏离，模型极易出现无据编造。
- **循环改写与拒绝机制**：引入 Grade 节点判断证据充分性。如果不足，根据缺失信息重写 Query 并重新检索（最多循环 2 次）。如果依旧不足，坚决流向 Refuse 节点输出固定拒答文案，在源头降低无据编造风险。
- **状态流转可追溯**：LangGraph 的 State 清晰记录了每一步的检索、评判结果与重写历史，天然适配前端逐步展示（SSE Step 事件）以及离线评测。

## 5. 为什么通信选择 SSE（Server-Sent Events）而不是 WebSocket？

- **单向流式天然匹配**：问答场景是典型的客户端发一次请求（POST）、服务端单向持续吐出 Token 与 Agent Step 事件，不需要服务端到客户端的双向实时交互。
- **协议简单轻量**：基于标准 HTTP/1.1 与 HTTP/2，天然穿透网关与防火墙，无需维护复杂的 WebSocket 握手、心跳维持与断线重连协议栈。
- **事件结构化**：SSE 原生支持 `event` 与 `data` 划分，方便分别派发 `step`、`token`、`citations`、`done`、`error` 等结构化数据。
- **客户端实现考量**：浏览器原生 `EventSource` 仅支持 GET 请求，而问答输入通常较长且带有 JSON payload。因此前端采用基于 `fetch` + `ReadableStream` 的 SSE 客户端解析协议，兼具 POST 灵活性与 SSE 结构化优势。

## 6. 为什么流式生成选择“先校验后推流（Verify-then-Stream）”而不是直接透传生成？

- **校验前置与用户体验的权衡**：系统接受较高的首字等待时间（TTFT，约等于 LangGraph 整图执行耗时），以确保在正式向客户端推流回答前完成引用索引有效性核对，防止非法或悬空引用标记被推送到前端，并在证据不足时受控拒答。该机制聚焦于引用标号与检索证据的物理对账，但不代表商用 LLM 的文本生成本身具备确定性（deterministic），亦不保证回答中所有陈述在语义层面的绝对真实性。

## 7. 关于流式取消（Abort）的系统边界

- **客户端与传输层**：用户点击前端“停止”按钮时，浏览器端 `AbortController` 立即取消 `fetch` 请求，切断 HTTP 连接并重置前端交互状态；FastAPI 检测到客户端断开后终止当前响应推流。
- **Agent 执行边界**：底层连接断开后，后续的 LangGraph 节点不再调度执行。
- **上游 LLM 算力边界**：若客户端中断时服务端恰好有一个外部阻塞式 LLM HTTP 请求正在进行，Python 线程需等待该次单次请求返回或超时，系统并不保证强制中断外部模型供应商服务端的后台推理计算。

## 8. 为什么从 Next.js 迁移至 TanStack Start + Vite+？（TanStack Start + Vite+ over Next.js）

- **统一高效的 Vite 现代构建流水线**：Next.js 在演进中形成了 Webpack 与 Turbopack 并存的双轨构建架构，其服务端组件（RSC）黑盒与特定运行时深度绑定；而 Vite+ 基于 Vite 8 原生 ESM 架构，具备极速冷启动与毫秒级热模块替换（HMR），并通过单层插件体系原生支持 SSR 与 CSR 混合流式渲染。
- **全栈端到端严格类型安全（Full-Stack Type Safety）**：TanStack Start 基于 TanStack Router 构建，将路由路径、URL search 参数、loader 数据及流式 SSR 上下文全部纳入 TypeScript 类型系统。任何路由变动或参数类型不匹配均在编译期报错，彻底消除 Next.js 中常见的字符串路由拼写错误与运行时类型漂移风险。
- **面向 Agent 的无状态秒级验证（Stateless Fast Verification）**：配合 Vite+ 官方统一工具 `vp check`，Agent 与 CI 可以在不启动阻塞终端的长驻 dev server 的前提下，一键并行完成 TypeScript 类型校验、Oxlint 快速静态代码分析与 Oxfmt 代码格式化，显著提升 Agent 协作迭代与自动化合规审查的执行确定性与吞吐量。
- **清晰透明的轻量架构心智**：TanStack Start 避免了 Next.js 复杂的 `use server` / Server Actions 与隐式服务端数据缓存陷阱，保持清晰直观的 Client/Server 边界，与 EvidenceOS 的 FastAPI 独立后端契约（REST API + SSE 流式推流）天然契合。

## 9. 为什么选择 Meta StyleX 替代 Tailwind CSS？（Meta StyleX over Tailwind CSS）

- **确定性与编译期类型约束（Deterministic Type Safety）**：Tailwind CSS 基于纯字符串 utility class，缺乏编译期语法校验与强类型提示，易因类名拼写错误而静默失效；在组件样式覆盖与复用场景下，Tailwind 容易发生 CSS 优先级冲突，往往需要依赖 `tailwind-merge` 等运行时库进行低效的字符串解析。Meta StyleX 由 Meta 官方开源，采用声明式 TypeScript API（`stylex.create`），所有 CSS 属性与取值受 TypeScript 严格类型约束，并且在样式合并时遵循严格的“后传入者胜出”（Last Applied Wins）确定性覆盖规则，从根本上消除了样式层叠冲突。
- **零运行时开销与无碰撞原子 CSS（Zero Runtime Overhead & Collision-Free Atomic CSS）**：StyleX 通过 `@stylexjs/unplugin` 深度集成于 Vite 编译管道，在构建阶段静态解析所有样式定义并抽离生成纯静态原子 CSS。在客户端运行时没有任何 JavaScript 样式计算或动态 `<style>` 标签注入开销，原子类的 CSS 产物体积极小且随着代码库规模增长近乎线性平缓，兼具 Utility-first CSS 的极致复用度与 CSS-in-JS 的封装隔离性。
- **设计系统 Token 强契约（Design Token Enforcement）**：通过 `src/styles/tokens.stylex.ts`（`stylex.defineVars`）统一定义颜色、间距、字体与边框半径等设计 Token。样式中只能引用合规的 Token 变量，有效杜绝了代码中随处硬编码魔法值（Magic Numbers）的乱象，保证跨页面交互组件的视觉规范严谨统一。
- **彻底清除外部样式编译管线负债**：全面清理了 `tailwindcss`、`postcss`、`autoprefixer` 以及 `tailwind.config.js`、`postcss.config.js` 等冗余配置文件与编译层，整体前端样式链完全收敛于 Vite + StyleX 纯净管线之中。

## 10. 为什么引入 Agent 原生工具链与开发规则？（Agent-Native Tooling and Rules Integration）

- **Agent 行为基线固化（`apps/web/.cursorrules`）**：在前端根目录建立面向 AI Agent 的强约束规则集，明确锁定“严禁引入 Tailwind CSS”、“遵循 StyleX 静态创建与 `stylex.props()` 挂载规范”、“TanStack Router 强类型路由范式”等关键架构契约，防止多 Agent 协作或自动化迭代过程中出现技术栈退化或代码范式污染。
- **多维度可观测性与实时排错（Observability & Debuggability）**：
  - 集成 `@tanstack/react-router-devtools`：在开发环境中以可视化面板呈现整树路由拓扑、当前匹配状态、Loader 数据流与导航历史，极大提升流式 Q&A 与文档管理多路由状态的调试效率。
  - 集成 `vite-plugin-inspect`：允许开发者与 Agent 通过 Web 界面深入观测 Vite 插件流水线中每个模块经由 `@stylexjs/unplugin` 与 TanStack Start 转换前后的真实 AST/代码产物，消除编译黑盒。
- **严格的静态合规防御网**：
  - 配置 `@stylexjs/eslint-plugin`：在编码与 CI 阶段静态拦截动态字符串样式构建或非法 StyleX 调用，确保样式代码 100% 满足编译期静态提取前提。
  - 接入 Vite+ `vp check`：提供统一、标准化的一键代码质量守护，确保每一次 Agent 交付的代码均在类型、风格与静态语法层面达到最高工程质量标准。
