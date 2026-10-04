# FastAPI 核心技术指南

FastAPI 是一个用于构建现代高效 Web API 的 Python 框架，基于 Starlette 和 Pydantic 构建。

## 架构与核心特性

FastAPI 原生支持异步并发（`async` 和 `await`），基于标准 ASGI 协议运行。它在提供极致性能的同时，自动生成符合 OpenAPI 规范的交互式 API 文档（Swagger UI 与 ReDoc）。

### 类型提示与数据验证

FastAPI 深度集成了 Pydantic。通过在函数参数中声明 Pydantic 模型，FastAPI 自动完成：
1. 请求数据的解析与反序列化（支持 JSON、表单数据和查询参数）。
2. 严格的数据校验：当客户端传入不符合模式的数据时，框架自动返回 422 Unprocessable Entity 状态码及详细错误信息。
3. 响应数据的序列化与字段过滤，防止敏感字段泄漏。

## 依赖注入系统（Dependency Injection）

FastAPI 拥有强大且可嵌套的依赖注入机制，使用 `fastapi.Depends` 声明：
- 依赖项可以是普通函数或异步生成器（Generator），方便管理数据库会话（Session）的生命周期。
- 依赖项支持层次化组合与缓存复用（`use_cache=True`），同一个请求内相同依赖仅执行一次。
- 典型的依赖模式包括数据库事务管理、用户认证与权限校验、公用配置注入。

## 后台任务与事件循环

在 HTTP 响应返回后需要执行耗时操作时（例如发送邮件、文档切分与向量计算），FastAPI 提供了轻量级的 `BackgroundTasks` 类：
- 路由处理函数中声明 `background_tasks: BackgroundTasks`。
- 调用 `background_tasks.add_task(func, *args, **kwargs)` 注册任务。
- FastAPI 会在将 HTTP 202 或 200 响应发回客户端后，在同一个异步事件循环中调度执行该后台函数。
