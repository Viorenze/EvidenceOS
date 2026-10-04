# PostgreSQL 与 pgvector 扩展技术指南

PostgreSQL 是一款功能强大的开源对象关系型数据库。通过安装 `pgvector` 扩展，PostgreSQL 能够原生存储向量并进行高效的高维向量相似度检索。

## pgvector 扩展基础

在使用向量类型前，必须在数据库实例中初始化扩展：
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
扩展提供 `vector(n)` 数据类型，其中 `n` 表示向量维度。例如 `vector(512)` 适用于存储 512 维的稠密文本嵌入向量。

### 距离度量算子

pgvector 支持多种常用的向量距离计算算子：
- `<=>`：余弦距离（Cosine Distance），定义为 $1 - \text{cosine\_similarity}$。对于归一化后的向量，余弦距离范围为 0 到 2。
- `<->`：欧氏距离（L2 Distance）。
- `<#>`：内积负值（Negative Inner Product），用于最大内积检索（MIP）。

## 向量索引：HNSW 与 IVFFlat

为了避免全表暴力扫描，pgvector 提供了两种主流的近似最近邻（ANN）索引：
1. **HNSW（Hierarchical Navigable Small World）**：
   - 基于分层可导航小世界图结构构建，召回率高且查询延迟低。
   - 创建索引时可以调节 `m`（每个节点的最大双向链接数，默认 16）与 `ef_construction`（构建时的搜索动态候选列表大小，默认 64）。
   - 在生产环境通常优先选用 HNSW 索引。
2. **IVFFlat（Inverted File Flat）**：
   - 基于倒排聚类中心索引，内存占用相对较小，但需要预先加载一定量的数据训练聚类中心。

## 中文全文检索与 GIN 索引

PostgreSQL 内置了 tsvector 与 tsquery 全文检索系统。由于默认分词器不支持无空格连写的中文字符串，实践中推荐采用外部切词（如 jieba）将文本切分成空格隔开的词串存入 `content_seg` 字段。
利用生成的 `to_tsvector('simple', content_seg)` 列构建 GIN（Generalized Inverted Index）索引，配合 `ts_rank_cd` 函数基于词覆盖密度进行词法相关度打分。
