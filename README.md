# Motorcycle Repair Assistant 摩托车售后智能助手

基于 RAG + Agent 的摩托车后市场售后问答助手:面向维修保养场景(以川崎 Ninja 400 为起点),回答机油规格、扭矩参数、配件型号等专业问题,目标是逐步演进为多 Agent 架构的完整售后服务系统。

## 项目背景

摩托车售后场景的问题高度专业化:大量精确型号(如火花塞 NGK CPR8EA-9)、扭矩规格(29 N·m)、专有名词,纯语义检索在这类"精确匹配"问题上存在天然盲区,而纯关键词检索又无法理解"机油多久换一次"这类口语化表述。本项目的核心思路是用**混合检索**同时覆盖这两类问题,并在其上逐步构建查询理解、知识图谱、多 Agent 协作等能力。

## 技术栈(当前已实现)

**核心框架与语言**

- Python 3.11 — 项目主语言
- python-dotenv — 环境变量与密钥管理(API key 隔离,不进仓库)

**大模型**

- DeepSeek(deepseek-chat)— 通过 OpenAI 兼容 SDK 调用,负责答案生成
- openai(SDK)— 作为调用 DeepSeek 的客户端

**Agent 编排**

- Function Calling + 自实现 agent loop — 工具调用与多轮对话状态管理
- LangGraph — StateGraph、条件边路由、checkpointer 对话记忆

**检索增强(RAG)— 当前核心模块**

- BGE-M3(BAAI,经 FlagEmbedding 加载)— 稠密向量 embedding,负责语义检索
- ChromaDB — 向量数据库,存储与检索文本 embedding
- BM25(rank-bm25)+ jieba 中文分词 — 稀疏检索,负责精确关键词 / 型号匹配
- RRF(Reciprocal Rank Fusion)— 融合稠密与稀疏两路检索结果(自实现)
- BGE-reranker-v2-m3(经 sentence-transformers CrossEncoder 加载)— 精排,对粗筛结果做交叉编码重排

**查询理解与动态路由(Query Understanding)**

- FAQ 语义缓存 — BGE-M3 向量 + 余弦相似度匹配高频问题,命中直接返回,不消耗 LLM 调用
- 意图分类 — LLM 零样本分类(temperature=0),将问题分流为 chitchat / knowledge / diagnosis 三类,带解析兜底
- HyDE(Hypothetical Document Embeddings)— 生成假设性答案作为检索"诱饵",拉近口语化提问与书面语料的语义距离
- 子问题拆解 — 复合问题拆为独立子问题分别检索再汇总,JSON 解析失败自动降级为单一问题
- 成本分层路由 — 按"FAQ 缓存 → 意图分类 → 按类分流"逐层拦截,每层用最低成本处理能处理的问题,把检索与查询改写留给真正需要的复杂问题

**图检索(知识图谱)**

- Neo4j — 图数据库,存储"品牌→车型→配件"的配件兼容关系,以 Docker 服务化部署,bolt 协议连接
- Text2Cypher — LLM 将自然语言问题翻译为 Cypher 查询,注入图谱 schema 提升准确率
- 查询安全护栏 — 只读强制(正则拦截写操作)+ EXPLAIN 预校验(执行前空跑,校验语法与标签),防止 LLM 生成危险或错误查询

**多 Agent 编排**

- LangGraph supervisor 模式 — StateGraph 共享状态 + 条件边分发,supervisor 统一决策,QA / Action / chitchat / complaint 四类处理单元各司其职
- Pydantic 结构化路由 — supervisor 的路由决策以 Pydantic 模型(Literal 枚举)校验 LLM 输出,拦截字段名拼错、取值越界等"合法 JSON 但语义错误"的输出
- 情绪双层拦截 — 第一层 BGE-M3 对投诉样例做语义匹配(免费、本地),第二层 LLM 判断情绪指向(区分"投诉本店"与"描述故障"),真投诉走安抚话术优先转人工
- 双引擎动态路由 — 按问题类型在向量检索(模糊语义)与图检索(精确兼容关系)间自动选择

**Agent 安全闭环(ActionAgent)**

- Function Calling 业务办理 — ActionAgent 以 ReAct 式循环调度业务工具(查订单/预约保养/申请退款,mock 数据真实接口),轮数上限防失控
- Human-in-the-Loop 人工审核 — 高危操作(退款)执行前经 LangGraph interrupt 暂停,状态存入 checkpointer,商家批准后断点续跑;已驳回操作在本轮内禁止重复申请
- Reflection 自愈 — 工具失败时 LLM 分析错误并生成修复建议回流重试(≤3 次),超限告警转人工;错误信息内置修复线索(可约日期、格式约束),对资金操作保守不猜测
- 工具分层 — 工具实现框架无关(未来可平替为业务系统 HTTP 调用),高危名单随工具声明,审批拦截归编排层执行(声明与执行分离)

**工程实践**

- 分层架构 — 检索层(HybridRetriever)与生成层解耦,检索策略可独立替换而不影响生成
- LangSmith 全链路可观测 — LangGraph 节点自动上报 + wrap_openai 包裹裸 SDK 客户端,每次请求的完整调用树(prompt 原文 / token / 延迟)可视化,各路由的成本分层有据可查
- Git 版本管理

## 架构:混合检索模块(HybridRetriever)

针对纯语义检索在精确型号、专有名词上的盲区,实现**稠密 + 稀疏双路混合检索**:BGE-M3 负责语义召回,BM25 负责关键词精确匹配,通过 RRF 算法融合两路排名结果,再由 BGE-reranker(CrossEncoder 架构)对粗筛候选做精排。采用"粗筛多召回、精排取精"的两段式设计,兼顾召回率与精度。检索层与生成层完全解耦,检索策略的升级(如从单路到混合)对生成层透明。

```
用户问题
   │
   ├──► BGE-M3 稠密检索(语义召回)──┐
   │                                 ├──► RRF 融合(粗筛 top-6)──► BGE-reranker 精排(top-3)──► LLM 生成
   └──► BM25 稀疏检索(关键词匹配)──┘
```

## 架构:查询理解流水线(route_and_answer)

在混合检索之上增加一层**成本分层的查询理解与路由**:核心思想是每一层都用当前最低成本的手段拦截它能处理的问题,把昂贵的检索与查询改写留给真正需要的复杂问题。

```
提问 ──► ① FAQ 语义匹配(最便宜,命中直接返回,不惊动 LLM)
           │ 未命中
           ▼
        ② 意图分类(一次 LLM 调用)
           ├─ chitchat:  直接回复,不检索
           ├─ knowledge: 混合检索 ──────────────────► 生成
           └─ diagnosis: 子问题拆解 + HyDE 改写 ──► 逐个检索、汇总去重 ──► 生成
```

生成层严格基于检索资料回答,资料中没有的信息如实告知,不编造(防幻觉),并返回引用的资料条数(可溯源)。

## 架构:图检索与 Text2Cypher(GraphRetriever)

配件兼容性是典型的"精确关系"问题(某年份某车型兼容哪些配件、某配件还适配哪些车型),用知识图谱表达最自然。图谱以"品牌→车型→配件"三级建模,**年份作为兼容关系上的属性**(`year_from` / `year_to`)——刻意不把年份建成独立节点,避免全局共享的年份节点导致跨车型/跨品牌配件被错误串联。

```
(Brand)──HAS_MODEL──►(Model)──COMPATIBLE_WITH {year_from, year_to}──►(Part)

问题 ─► LLM 生成 Cypher(注入 schema)─► 只读校验 ─► EXPLAIN 预校验 ─► 执行 ─► 结构化事实
```

GraphRetriever 与 HybridRetriever 保持一致:**只负责"检索出事实",不负责生成**,维持检索层与生成层解耦。图检索(精确关系)与向量检索(模糊语义)构成互补的双引擎,后续按问题类型动态路由。

## 架构:LangGraph supervisor 多 Agent(agents.py)

整条流水线以 LangGraph StateGraph 组织:所有节点共享一个 State(问题、路由决策、检索资料、答案、溯源信息),supervisor 节点统一决策,条件边按决策分发。**情绪拦截在最前**(先于 FAQ,保证愤怒用户不会被缓存答案打发),FAQ 命中则由 supervisor 直接给答案不再惊动下游。

```
                        ┌─ complaint: 安抚话术,优先转人工
用户 ─► supervisor ──┼─ chitchat:  直接回复(FAQ 命中也走这里,不再生成)
        │ ①情绪双层拦截 ├─ qa:        knowledge→向量检索 / compatibility→图检索 / diagnosis→拆解+HyDE
        │ ②FAQ 语义缓存 └─ action:    业务办理(占位,HITL 人工审核在 Roadmap)
        │ ③Pydantic 路由
```

路由决策用 Pydantic 模型钉死契约(`target` / `strategy` 均为 Literal 枚举),LLM 输出不合法时兜底走最安全的知识检索路线。相比 if 链,图结构的价值在于 State 可持久化——为后续 checkpointer 对话记忆与 interrupt 人工审核(HITL)铺路。

## 已实现功能 / Roadmap

### ✅ 已完成

- Agent 基础:Function Calling、agent loop、多轮对话状态管理
- LangGraph:StateGraph、条件边、checkpointer 记忆
- 向量检索:BGE-M3 embedding + ChromaDB 向量库
- 混合检索:BGE-M3 + BM25 + RRF 融合 + BGE-reranker 精排(`app/retriever.py`)
- 查询理解:FAQ 语义缓存、意图分类、HyDE、子问题拆解(`app/query_processing.py`)
- 动态路由:FAQ → 意图分类 → 三路分流的完整问答流水线(`app/rag.py`)
- 图检索:Neo4j 知识图谱 + Text2Cypher(schema 注入 + 只读 / EXPLAIN 双重护栏)(`app/graph_retriever.py`)
- 双引擎路由:按问题类型在向量检索与图检索间动态选择
- 情绪拦截:BGE-M3 语义匹配 + LLM 指向判断的双层拦截,真投诉优先安抚转人工
- 多 Agent 架构:LangGraph supervisor 模式,QA / Action / chitchat / complaint 四路分流(`app/agents.py`)
- Pydantic:路由决策的结构化输出校验(Literal 枚举 + 解析失败兜底)
- 安全闭环:ActionAgent 业务工具调用 + interrupt 人工审核(HITL)+ Reflection 自愈重试(`app/tools.py` + `app/agents.py`)
- LangSmith:全链路可观测,各路由成本分层可视化

### 🚧 进行中 / 📋 计划中

- 📋 多轮对话记忆:State 挂载 messages 历史(add_messages),支持澄清追问/slot filling
- 📋 Redis:FAQ 缓存持久化(当前为进程内语义缓存),拦截简单问题不进 LLM
- 📋 MCP(Model Context Protocol):FastMCP 封装工具,agent 动态发现加载
- 📋 FastAPI:流式对话接口
- 📋 评估体系:检索命中率、FAQ 拦截率、延迟、Text2Cypher 成功率,LLM-as-judge
- 📋 本地模型:Ollama + Qwen2.5-7B,云端 / 本地双后端切换
- 📋 Streamlit / Gradio:对话界面
- 📋 Docker / docker-compose:一键部署全套服务

## 项目结构

```
.
├── app/
│   ├── agents.py            # 主流水线:LangGraph supervisor 多 Agent(路由 + 检索 + 生成 + HITL)
│   ├── tools.py             # 业务工具层:mock 工具 + JSON Schema + 高危名单(框架无关)
│   ├── retriever.py         # HybridRetriever:混合检索核心模块
│   ├── query_processing.py  # 查询理解:FAQ 缓存 / 投诉检测 / 路由决策 / HyDE / 拆解
│   └── graph_retriever.py   # GraphRetriever:Text2Cypher 图检索 + 安全护栏
├── data/
│   ├── moto_manual.py            # Ninja 400 保养手册知识片段(示例数据)
│   └── parts_compatibility.csv   # 配件兼容数据(品牌 / 车型 / 配件 / 年份区间)
├── lab/                     # 各阶段学习实验脚本
│   ├── lab1_hello.py        # DeepSeek API 首次调用
│   ├── lab2_chat.py         # 多轮对话
│   ├── lab3_tool.py         # Function Calling
│   ├── lab4_agent.py        # agent loop
│   ├── lab5_graph.py        # LangGraph StateGraph
│   ├── lab5b_router.py      # 条件边路由
│   ├── lab6_graph_agent.py  # LangGraph agent + checkpointer 记忆
│   ├── lab_d2_*.py          # embedding / 建库 / 检索 / RAG 问答
│   ├── lab_d3_*.py          # BM25 / 混合检索
│   ├── lab_d4_*.py          # 意图分类 / FAQ 缓存 / HyDE / 子问题拆解
│   ├── lab_d5_*.py          # Neo4j 连接 / CSV 导入 / Text2Cypher
│   ├── lab_d6_1_emotion.py  # 情感模型实测(该模型已被数据证伪弃用,记录见 commit)
│   └── lab_d8_1_interrupt.py # LangGraph interrupt/checkpointer 最小验证
├── requirements.txt
├── TODO.md                  # 推迟事项清单(YAGNI 停车场)
└── .env.example             # 环境变量模板
```

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/zhongqiufeng2023-spec/motorcycle_repair_assistant.git
cd motorcycle_repair_assistant

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置密钥
# 复制 .env.example 为 .env,填入 DeepSeek API key 与 Neo4j 密码
cp .env.example .env

# 4. 构建向量库(首次运行会下载 BGE-M3 模型)
python lab/lab_d2_2_build_db.py

# 5. 启动 Neo4j 图数据库(Docker),并导入配件兼容数据
docker run -d --name moto-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_neo4j_password_here neo4j:5
python lab/lab_d5_2_import_csv.py

# 6. 运行完整多 Agent 流水线(投诉/闲聊/FAQ/知识/兼容/诊断/业务 全路由演示)
python app/agents.py
python app/graph_retriever.py        # 或单独测图检索:Text2Cypher 配件兼容查询
```

> 注:向量库(`data/chroma_db/`)与 Neo4j 数据均不进版本控制,clone 后通过第 4、5 步在本地重建即可。

## 学习日志

本项目采用"边学边建"的方式推进,`lab/` 目录保留了每个能力模块的最小可运行实验,与主应用代码(`app/`)分离——实验验证通过后再沉淀为正式模块。
