# Evals 说明文档

本文档用于说明 `evals` 目录下两个评测脚本的作用与使用方式。

## 1. `memory_eval.py` 的作用

### 目标
验证“长期记忆检索”能力是否可用，重点检查：
- 记忆是否能成功写入
- 查询时是否能命中预期记忆

### 覆盖内容
1. 从 `memory_cases.json` 读取测试样例。
2. 将样例中的 query 写入记忆库（`memory_items`）。
3. 对每条样例执行检索：`retrieve_relevant_memories(...)`。
4. 判断检索结果是否包含 `expect` 字段。

### 输出解读
- `PASS`：该条样例命中预期记忆。
- `FAIL`：未命中预期记忆。
- 最终会输出 `pass=x/y`，反映记忆检索基础准确性。

### 适用场景
- 你刚改完记忆写入、检索、冲突处理逻辑时
- 发布前快速确认“记忆能力仍可用”

---

## 2. `week4_regression.py` 的作用

### 目标
验证多 Agent 主链路是否回归，重点检查：
- 路由是否正确
- 工具调用与审批流是否正常
- 执行链路是否可观测

### 覆盖内容
脚本包含 4 个关键用例：
1. `geo review path`
   - 检查总结/复盘请求是否走 Geo 路径并给出证据点。
2. `pending approval`
   - 检查高风险动作（邀请）是否进入待审批队列。
3. `approval execute`
   - 检查批准后是否能真正执行该工具调用。
4. `trace visibility`
   - 检查 run/tools/guards 等调试链路是否可读取。

### 输出解读
- 每条用例输出 `PASS/FAIL`。
- 最终 `Summary: a/b passed` 代表本次核心链路健康度。

### 适用场景
- 你改了 Orchestrator / Agent / ToolExecutor / 审批流后
- 发布前做一次“核心功能体检”

---

## 3. 运行方式

推荐在项目根目录执行：

```powershell
python evals\memory_eval.py
python evals\week4_regression.py
```

也可在 `evals` 目录执行：

```powershell
python .\memory_eval.py
python .\week4_regression.py
```

> 说明：脚本已兼容自动注入项目根路径，因此两种运行方式都可用。

---

## 4. 建议通过标准（开源发布前）

1. `memory_eval.py`：建议通过率 >= 80%。
2. `week4_regression.py`：建议 4/4 全通过。
3. 若未通过：优先修复失败用例对应链路，再重新回归。

---

## 5. 这两个脚本的区别

- `memory_eval.py`：偏“能力准确性测试”（记忆是否检索对）。
- `week4_regression.py`：偏“系统稳定性回归”（核心流程是否还通）。

两个都跑，才能同时证明：
- 功能“有”
- 功能“稳”
