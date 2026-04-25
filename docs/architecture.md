# 旅行地图智能助手架构说明（全中文）

## 1. 项目目标
打造一个可开源、可演进的旅行 Agent 应用，具备以下能力：
- 多 Agent 协同处理用户请求
- 记忆管理与上下文预算控制
- 工具调用、审批、审计可观测
- Streamlit 前端可直接演示

## 2. 系统架构
### 2.1 核心角色
- `Orchestrator`：统一入口，负责意图路由、上下文组装、运行追踪。
- `GeoAgent`：地点检索、轨迹回放、旅行总结/复盘。
- `SocialAgent`：找搭子、发起邀请、社交相关动作。
- `MemoryAgent`：长期记忆写入、检索、冲突处理。
- `ToolExecutor`：统一工具执行层，负责策略判定、日志落库、审批联动。

### 2.2 技术栈
- 前端：Streamlit
- 后端：Python 服务层 + Agent 编排
- 存储：SQLite（默认本地）
- 模型通道：OpenAI / DeepSeek / Kimi / 自定义 OpenAI 兼容网关

## 3. 请求处理流程
1. 用户在“智能助手”输入问题。
2. `agent_service.answer()` 拉取会话历史、地点、附件上下文。
3. `Orchestrator` 根据意图路由到目标 Agent。
4. Agent 进入 ReAct 循环：思考 -> 选择工具 -> 执行工具 -> 继续推理。
5. 工具统一经过 `ToolExecutor`：
   - 应用策略（风险分级、频率限制）
   - 记录工具调用日志
   - 高风险动作写入审批队列
6. 返回答复并记录运行轨迹（route/tool/guard/request_id）。

## 4. 数据与可观测
### 4.1 关键数据表
- 业务数据：`spots`、`photos`、`invites`
- 对话与记忆：`conversations`、`agent_memory`、`memory_items`、`memory_conflicts`
- 可观测日志：`agent_run_logs`、`agent_tool_logs`、`agent_guard_logs`、`agent_pending_actions`
- 摘要与附件：`conversation_summaries`、`assistant_attachments`

### 4.2 调试能力
- 本轮 Agent 调试信息面板
- 按 `request_id` 回放执行链路
- 待审批工具调用面板（批准/拒绝）

## 5. 记忆机制
### 5.1 长期记忆
- 支持偏好、计划、事实、画像等类型
- 查询时按相关性返回 Top-K

### 5.2 冲突处理
- 新旧记忆冲突时进入待审状态
- 人工批准后：新记忆生效，冲突旧记忆失活
- 非冲突记忆保留

### 5.3 历史压缩
- 基于 token 阈值触发压缩
- 支持手动“压缩并导出 Markdown”
- 最近一次 `History Summary` 可在 UI 查看与下载

## 6. 安全与治理
- 工具策略沙箱：`low/medium/high` 风险分级
- 高风险工具默认进入人工审批（HITL）
- 审计日志记录决策原因、工具参数、执行结果
- ReAct 结果支持反思校验与一次重试

## 7. 四周迭代路线（已落地）
### 第 1 周：多 Agent 骨架
- 完成 Orchestrator + 3 子 Agent + ToolExecutor 主链路
- 实现基础路由与工具日志

### 第 2 周：记忆与上下文
- 完成长短期上下文预算管理
- 记忆检索接入推理链
- 冲突记忆审批流上线

### 第 3 周：策略与反思
- 高风险工具审批队列
- 审计日志体系化
- 反思机制与重试

### 第 4 周：稳定性与开源化
- 总结/复盘路径稳定
- request_id 链路回放
- 会话摘要导出 Markdown
- 文档、模板、脚本完善

## 8. 下一阶段建议（面试加分）
1. 接入多用户认证（账号体系 + 用户隔离）。
2. 记忆检索升级向量索引（FAISS/Milvus）。
3. 引入任务队列与异步工具执行。
4. 增加 CI（lint + 测试 + 快速回归）。
5. 增加线上观测（OpenTelemetry / Prometheus）。

## 9. 发布前检查清单
1. `.env` 不入库，`.env.example` 完整。
2. `README.md` 可独立指导新用户启动。
3. `evals` 脚本可运行并有通过结果。
4. `LICENSE`、`CONTRIBUTING.md`、`CHANGELOG.md` 齐全。
