# 发布前检查清单

## 1. 代码与配置
- [ ] `.env` 未提交，`.env.example` 完整可用
- [ ] `requirements.txt` 可成功安装
- [ ] `streamlit run streamlit_app.py` 可正常启动

## 2. 核心功能
- [ ] 地点新增/删除/搜索正常
- [ ] 相册按地点展示正常
- [ ] 轨迹回放可按年份播放
- [ ] 智能助手可回复并显示调试信息
- [ ] 高风险工具进入审批队列

## 3. Agent 可观测性
- [ ] 本轮工具调用日志可见
- [ ] `request_id` 链路回放可查询
- [ ] 审批动作（批准/拒绝）有日志

## 4. 文档完整性
- [ ] `README.md`（启动、架构、FAQ）
- [ ] `docs/architecture.md`
- [ ] `CONTRIBUTING.md`
- [ ] `CHANGELOG.md`
- [ ] `LICENSE`

## 5. 回归测试
- [ ] `python evals/memory_eval.py`
- [ ] `python evals/week4_regression.py`

## 6. 开源准备
- [ ] 仓库描述、Topic、首页截图已补齐
- [ ] 首个 Release 说明已撰写
