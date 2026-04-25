# 贡献指南

感谢你参与这个项目。

## 开发环境
1. 安装依赖：`pip install -r requirements.txt`
2. 复制配置：`Copy-Item .env.example .env`
3. 启动应用：`streamlit run streamlit_app.py`

## 提交规范
1. 一个 PR 只解决一个明确问题（例如“修复审批流展示顺序”）。
2. 涉及功能改动时，请同步更新文档：
   - `README.md`
   - `docs/architecture.md`
   - `CHANGELOG.md`
3. 提交前至少执行：
   - `python evals/memory_eval.py`
   - `python evals/week4_regression.py`

## 代码约定
1. 保持模块边界清晰：
   - `agent_core`: 编排、路由、ReAct、工具执行
   - `memory`: 长期记忆能力
   - `services`: 业务服务与数据接口
2. 新增工具调用必须补齐：
   - 策略决策（`src/agent_core/policy.py`）
   - 工具日志与审计信息
3. 高风险动作默认走审批流，不允许直接自动执行。

## PR 模板建议
1. 背景与目标
2. 关键改动列表
3. 本地验证步骤
4. 风险与回滚方案

## Issue 反馈
请优先使用 `.github/ISSUE_TEMPLATE` 下的模板提交 Bug 或需求。
