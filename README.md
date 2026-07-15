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

**工程实践**

- 分层架构 — 检索层(HybridRetriever)与生成层解耦,检索策略可独立替换而不影响生成
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

## 已实现功能 / Roadmap

### ✅ 已完成

- Agent 基础:Function Calling、agent loop、多轮对话状态管理
- LangGraph:StateGraph、条件边、checkpointer 记忆
- 向量检索:BGE-M3 embedding + ChromaDB 向量库
- 混合检索:BGE-M3 + BM25 + RRF 融合 + BGE-reranker 精排(`app/retriever.py`)
- 查询理解:FAQ 语义缓存、意图分类、HyDE、子问题拆解(`app/query_processing.py`)
- 动态路由:FAQ → 意图分类 → 三路分流的完整问答流水线(`app/rag.py`)

### 🚧 进行中 / 📋 计划中

- 📋 Redis:FAQ 缓存持久化(当前为进程内语义缓存),拦截简单问题不进 LLM
- 📋 Neo4j:图数据库,配件兼容性查询(品牌→车型→年份→配件),Text2Cypher 动态生成 + EXPLAIN 预校验
- 📋 双引擎路由:按问题类型在向量检索与图检索间动态选择
- 📋 多 Agent 架构(LangGraph):supervisor 模式,情绪检测 + 意图路由,QAAgent / ActionAgent 分流
- 📋 情绪拦截:轻量情感模型 + LLM 双层判断
- 📋 安全闭环:ActionAgent 工具调用、高危操作 human-in-the-loop 人工审核(LangGraph interrupt)、Reflection 自愈重试
- 📋 MCP(Model Context Protocol):FastMCP 封装工具,agent 动态发现加载
- 📋 FastAPI:流式对话接口
- 📋 评估体系:检索命中率、FAQ 拦截率、延迟、Text2Cypher 成功率,LLM-as-judge
- 📋 Pydantic:结构化输出校验(贯穿各模块)
- 📋 本地模型:Ollama + Qwen2.5-7B,云端 / 本地双后端切换
- 📋 Streamlit / Gradio:对话界面
- 📋 Docker / docker-compose:一键部署全套服务

## 项目结构

```
.
├── app/
│   ├── retriever.py         # HybridRetriever:混合检索核心模块
│   ├── query_processing.py  # 查询理解:FAQ 语义缓存 / 意图分类 / HyDE / 子问题拆解
│   └── rag.py               # 主流程:route_and_answer 动态路由 + 生成
├── data/
│   └── moto_manual.py       # Ninja 400 保养手册知识片段(示例数据)
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
│   └── lab_d4_*.py          # 意图分类 / FAQ 缓存 / HyDE / 子问题拆解
├── requirements.txt
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

# 3. 配置 API key
# 复制 .env.example 为 .env,填入你的 DeepSeek API key
cp .env.example .env

# 4. 构建向量库(首次运行会下载 BGE-M3 模型)
python lab/lab_d2_2_build_db.py

# 5. 运行完整问答流水线(FAQ / 闲聊 / 知识问答 / 故障诊断四类路由演示)
python app/rag.py
```

> 注:向量库(`data/chroma_db/`)不进版本控制,clone 后通过第 4 步在本地重建即可。

## 学习日志

本项目采用"边学边建"的方式推进,`lab/` 目录保留了每个能力模块的最小可运行实验,与主应用代码(`app/`)分离——实验验证通过后再沉淀为正式模块。
