# 旅行地图智能助手

基于 **Streamlit + SQLite + 多 Agent 架构**的旅行记录与 AI 助理平台。  
记录你走过的每一个地方，让 AI 帮你回忆、规划、分析，并与旅伴共享。

---

## ✨ 功能一览

| 模块 | 说明 |
|------|------|
| **地图总览** | 高德 / Leaflet 双地图引擎，国内聚合标记，海外普通标记，点击弹出地点详情 |
| **添加地点** | 关键词搜索（高德 POI / OpenStreetMap 自动降级），填写旅行日期、备注、上传照片 |
| **我的旅行相册** | 瀑布流展示，按年份 / 国家筛选，AI 自动打标签，可编辑 / 删除地点 |
| **轨迹回放** | 按时间顺序逐站播放，国内用高德、海外用 Leaflet+ESRI，4 秒一站可暂停重置 |
| **找搭子** | 基于旅行记录计算偏好相似度，排行榜展示，一键发起旅行邀请（需审批） |
| **旅行记忆** | 长期记忆存储与检索，支持手动写入 / AI 自动提取，冲突检测与合并 |
| **行程规划** | AI 生成多日行程，导出 PDF，可共享给其他用户 |
| **旅行报告** | 按年份 / 国家生成统计报告（地点数、照片数、里程），导出 PDF |
| **协作中心** | 共享相册地点给好友，@提及评论，接受 / 拒绝邀请，多用户实时演示 |
| **智能助手** | Supervisor 多 Agent 对话，支持上传 PDF/Excel/Word 让 AI 分析，对话历史压缩 |

---

## 🏗️ 架构设计

```
用户请求
   │
   ▼
Streamlit 前端页面（pages/）
   │
   ▼
Service 层（src/services/）         ← 业务逻辑，直接操作 DB
   │
   ▼
多 Agent 编排层（src/agent_core/）
   │
   ├─ TravelOrchestrator            ← 入口：决定单/多 Agent 路径
   │    ├─ Supervisor               ← LLM 把 query 分解为子任务
   │    └─ route_agent()            ← LLM 分类 + 关键词降级路由
   │
   ├─ GeoAgent                      ← 地点搜索 / 天气 / 年度复盘
   ├─ MemoryAgent                   ← 长期记忆写入 / 文档分析
   ├─ SocialAgent                   ← 搭子匹配 / 发起邀请
   └─ PlanAgent                     ← 行程规划生成
        │
        ▼
   ReAct Runner                     ← 工具调用循环（最多 8 轮）
        │
        ▼
   Tool Registry（@tool 装饰器注册）
   + Policy Engine（风险分级 + 人工审批）
        │
        ▼
   LLM Service（OpenAI 兼容接口）   ← 支持 OpenAI / DeepSeek / Kimi / 自定义
        │
        ▼
   Reflection & Quality Check       ← 答复反思校验 + 一次自动重试
```

### 核心设计决策

**1. 双地图引擎**  
高德地图仅覆盖中国大陆（坐标范围 lng 73–136, lat 3–54），境外地点自动切换 Leaflet + ESRI World Street Map（jsDelivr CDN，国内可访问）。

**2. Supervisor 模式**  
用户 query 先经过 LLM Supervisor 分解：若为单一意图直接路由到对应 Agent；若跨多个领域（如"规划东京行程并查天气"）拆成最多 3 个子任务并发执行，最终由 Synthesis LLM 合并回复。

**3. ReAct 工具循环 + 反思机制**  
每个 Agent 最多循环调用工具 8 次，得到草稿回复后经 `reflect()` 做质量校验，不通过则自动重试一次。文档附件场景下，反思上下文切换为文档内容而非旅行记录，防止错误判定。

**4. 长期记忆系统**  
`memory_items` 表存储用户偏好 / 计划 / 事实，写入时做冲突检测（n-gram 相似度），同主题矛盾记忆进入 `memory_conflicts` 等待人工解决。检索时支持 n-gram 余弦相似度（默认）或 OpenAI Embedding 语义重排（可选）。

**5. 规则降级（LLM_PROVIDER=none）**  
无 LLM 时系统不崩溃：路由通过关键词匹配，工具调用直接执行，回复使用预设模板。地图、相册、报告等非 AI 功能完全正常。

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/travel-map-agent.git
cd travel-map-agent
```

### 2. 安装依赖

建议使用 Python 3.10+，推荐虚拟环境：

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

用文本编辑器打开 `.env`，填入你的 API Key（见下方"API Key 获取"）。

### 4. 启动应用

```bash
streamlit run streamlit_app.py
```

浏览器自动打开 `http://localhost:8501`。

### 5. 初始化演示数据（可选但推荐）

首次启动后，在浏览器里只能看到空地图。运行以下命令导入 15 个横跨中、日、东南亚、欧洲的演示地点及实景照片，方便快速体验全部功能：

```bash
python scripts/seed_demo.py
```

> 照片通过网络从 Unsplash CDN 下载，需要能访问 `images.unsplash.com`。  
> 下载失败会自动尝试 Wikipedia 缩略图 → picsum.photos 备用图，不影响地点数据导入。

如需清空已有演示数据重新导入：

```bash
python scripts/seed_demo.py --reset
```

---

## 🔑 API Key 获取指南

### 高德地图（地图展示 + 地点搜索）

> 未配置时地图自动降级为 Leaflet，国内地点搜索回退到 OpenStreetMap，功能可用但体验较差。

1. 注册/登录 [高德开放平台](https://lbs.amap.com/)
2. 进入「控制台」→「应用管理」→「创建新应用」
3. 在同一个应用下创建 **两个 Key**：
   - 服务平台选 **「Web 服务」** → 填入 `AMAP_API_KEY`（供后端地理编码使用）
   - 服务平台选 **「Web 端(JS API)」** → 填入 `AMAP_JS_KEY`（供前端地图展示使用）
4. 如需安全密钥（推荐）：控制台 → 应用 → 数字签名 → 复制安全密钥 → 填入 `AMAP_SECURITY_CODE`

### LLM（AI 能力，至少配置一个）

| 服务商 | 申请地址 | 推荐模型 | 特点 |
|--------|---------|---------|------|
| **DeepSeek**（推荐） | https://platform.deepseek.com | `deepseek-chat` | 价格极低，中文能力强 |
| OpenAI | https://platform.openai.com | `gpt-4o-mini` | 能力全面，价格较高 |
| Kimi | https://platform.moonshot.cn | `moonshot-v1-8k` | 长上下文，中文友好 |
| 自定义 | 本地 Ollama / vLLM / 任意 OpenAI 兼容接口 | 按需配置 | 离线运行 |

**配置示例（DeepSeek）**：

```env
LLM_PROVIDER="deepseek"
DEEPSEEK_API_KEY="sk-your-key-here"
DEEPSEEK_MODEL="deepseek-chat"
```

> 若暂不配置 LLM，将 `LLM_PROVIDER="none"`，地图/相册/报告等功能仍正常使用。

---

## 📁 项目结构

```
.
├── streamlit_app.py           # 首页：地图总览 + 统计数据
├── pages/
│   ├── 1_智能助手.py           # 多 Agent 对话，支持附件上传与管理
│   ├── 2_添加地点.py           # 地点搜索 + 表单填写 + 照片上传
│   ├── 3_我的旅行相册.py       # 相册展示，AI 标签，编辑/删除
│   ├── 4_轨迹回放.py           # 按时间顺序播放旅行轨迹
│   ├── 5_找搭子.py             # 搭子推荐 + 邀请功能
│   ├── 6_旅行记忆.py           # 长期记忆管理
│   ├── 7_行程规划.py           # AI 生成行程 + 共享
│   ├── 8_旅行报告.py           # 统计报告 + PDF 导出
│   └── 9_协作中心.py           # 共享相册 + @评论 + 多用户
├── src/
│   ├── config.py               # 环境变量读取，路径常量
│   ├── db.py                   # SQLite 初始化（13 张表）
│   ├── ui.py                   # 地图 HTML 构建（高德 / Leaflet）
│   ├── agent_core/
│   │   ├── orchestrator.py     # TravelOrchestrator，Supervisor 路由
│   │   ├── react_runner.py     # ReAct 工具循环 + 反思机制
│   │   ├── router.py           # 单 Agent 意图分类
│   │   ├── models.py           # AgentContext, SubTask 数据类
│   │   ├── tool_executor.py    # 工具注册表 + Policy Engine
│   │   ├── context_manager.py  # Token 预算分配
│   │   ├── policy.py           # 工具风险策略（auto/approval/block）
│   │   └── agents/
│   │       ├── geo_agent.py    # 地点/天气/年度复盘
│   │       ├── memory_agent.py # 记忆写入 + 文档分析
│   │       ├── social_agent.py # 搭子匹配 + 邀请
│   │       └── plan_agent.py   # 行程规划
│   ├── memory/
│   │   └── service.py          # 记忆检索（n-gram / Embedding）
│   └── services/
│       ├── agent_service.py    # 对话管理，附件处理，答复入口
│       ├── spot_service.py     # 地点 CRUD，照片，AI 打标
│       ├── geo_service.py      # 高德 / Nominatim 双端地理编码
│       ├── match_service.py    # 搭子相似度算法
│       ├── collaboration_service.py  # 共享 / 评论 / @提及
│       ├── itinerary_service.py      # 行程生成 + 共享
│       ├── report_service.py   # PDF 报告生成
│       ├── llm_service.py      # OpenAI 兼容 LLM 封装
│       └── amap_client.py      # 高德 REST API 封装
├── scripts/
│   └── seed_demo.py            # 演示数据初始化脚本
├── data/                       # 运行时数据（已 gitignore，自动创建）
│   ├── travel_map.db           # SQLite 数据库
│   └── uploads/                # 上传的照片
├── .env.example                # 环境变量模板（复制为 .env 后填入 Key）
├── requirements.txt
└── README.md
```

---

## 🔧 常见问题

**Q：启动后地图是空白的 / 显示"AMAP_JS_KEY 未配置"**  
A：填写 `.env` 中的 `AMAP_JS_KEY`（JS API 类型）。未填时地图自动降级为 Leaflet，国内地图样式较简陋但可用。

**Q：地点搜索提示"高德 REST API Key 未配置"**  
A：填写 `.env` 中的 `AMAP_API_KEY`（Web 服务类型）。未填时搜索回退到 OpenStreetMap，国内地点较慢或找不到。

**Q：智能助手提示"未启用 LLM"**  
A：在 `.env` 中设置 `LLM_PROVIDER` 为 `deepseek` / `openai` 等，并填入对应 API Key，重启应用。

**Q：上传 PDF 后助手没有回复**  
A：确认 `pypdf` 已安装（`pip install pypdf`）。展开附件面板确认文件名已显示，说明上传成功，再次发送分析请求即可。

**Q：轨迹回放国外城市显示灰色**  
A：已修复，新版对境外坐标自动切换 Leaflet+ESRI 地图，无需额外配置。

**Q：如何体验多用户协作**  
A：在「协作中心」页面顶部切换用户，可模拟 demo_user、alina 等多个演示账号之间的共享和评论交互。

**Q：seed_demo.py 跑完照片还是没有**  
A：脚本依次尝试 Unsplash → Wikipedia → picsum.photos 三个源。若全部失败则该地点跳过照片，地点数据本身会正常插入。可重新运行 `python scripts/seed_demo.py`（幂等）再次尝试下载。

---

## 🛠️ 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | Streamlit 1.36+，HTML/JS 内嵌组件 |
| 地图 | 高德地图 JS API 2.0（国内），Leaflet 1.9 + ESRI（国际） |
| 数据库 | SQLite（`sqlite3` 标准库，零依赖部署） |
| AI 对话 | OpenAI Python SDK（兼容 DeepSeek / Kimi / 本地 LLM） |
| PDF 生成 | ReportLab |
| PDF 解析 | pypdf |
| 地理编码 | 高德 REST API + Nominatim（OpenStreetMap） |
| 向量检索（可选） | OpenAI text-embedding-3-small |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE) 文件。
