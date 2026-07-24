# Motorcycle Repair Assistant 摩托车售后智能助手

基于 LangGraph 的摩托车后市场智能客服 Agent:面向维修保养场景(以川崎 Ninja 400 为起点),覆盖专业问答(混合检索 RAG + 知识图谱)、多 Agent 路由、情绪拦截、业务办理(Function Calling + 人工审核 HITL + Reflection 自愈),并已服务化(FastAPI)、多轮记忆、接入可观测(LangSmith),配自建评估体系。

```
                              ┌─────────────── 检索/知识 ───────────────┐
用户 ──HTTP──► FastAPI          │  HybridRetriever: BGE-M3 + BM25          │
 (/chat        (app/api.py)     │      → RRF 融合 → BGE-reranker 精排      │
  /approve)        │            │  GraphRetriever: Text2Cypher → Neo4j     │
                   ▼            └──────────────────────────────────────────┘
            LangGraph supervisor 图 (app/agents.py)          ▲
              ├─ ①情绪双层拦截  ②FAQ 语义缓存  ③Pydantic 路由 │
              ├─ qa       ── knowledge / compatibility / diagnosis(检索前指代消解改写)
              ├─ action   ── Function Calling 循环 + interrupt 人工审核 + Reflection 自愈
              ├─ chitchat ── 直接回复
              └─ complaint── 安抚 + 登记工单
              State + MemorySaver(按 thread_id 多轮记忆 / 审批暂停-恢复)
                   │
              LangSmith 全链路可观测
```

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

**服务化与多轮记忆**

- FastAPI 后端服务 — `/chat` 对话端点 + `/approve` 商家审批端点,session_id 即 LangGraph thread_id;interrupt 审批以"pending_approval 状态 + 二次请求恢复"的异步模式承载(不占连接等待人工)
- 多轮对话记忆 — State 挂载 `messages` 历史(`add_messages` reducer 追加式合并),checkpointer 按 thread_id 持久化;跨轮上下文使 ActionAgent 无需用户重复订单号即可续办业务
- 同步/异步边界治理 — 请求处理函数走 FastAPI 线程池(同步 def),避免 CPU 密集的 embedding 与阻塞 LLM 调用冻结事件循环
- 序列化边界纪律 — checkpoint 内只存纯数据(dict),Pydantic 模型仅在 LLM 输出边界校验后即脱壳,规避自定义类反序列化风险

**MCP(Model Context Protocol)**

- FastMCP 工具服务器 — 业务工具经 `@mcp.tool` 以 MCP 协议暴露(类型标注自动生成 JSON Schema),业务逻辑与协议外壳分离
- 动态发现 — MCP 客户端运行时经 `tools/list` 发现工具清单并 `tools/call` 调用,工具供给侧可独立演化(lab 验证,主流水线接入在 Roadmap)

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
        │ ②FAQ 语义缓存 └─ action:    业务办理(Function Calling 循环 + interrupt 人工审核 + Reflection 自愈)
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
- 动态路由:FAQ → Pydantic 路由 → 多路分流的完整问答流水线(`app/agents.py` + `app/query_processing.py`)
- 图检索:Neo4j 知识图谱 + Text2Cypher(schema 注入 + 只读 / EXPLAIN 双重护栏)(`app/graph_retriever.py`)
- 双引擎路由:按问题类型在向量检索与图检索间动态选择
- 情绪拦截:BGE-M3 语义匹配 + LLM 指向判断的双层拦截,真投诉优先安抚转人工
- 多 Agent 架构:LangGraph supervisor 模式,QA / Action / chitchat / complaint 四路分流(`app/agents.py`)
- Pydantic:路由决策的结构化输出校验(Literal 枚举 + 解析失败兜底)
- 安全闭环:ActionAgent 业务工具调用 + interrupt 人工审核(HITL)+ Reflection 自愈重试(`app/tools.py` + `app/agents.py`)
- LangSmith:全链路可观测,各路由成本分层可视化
- FastAPI 服务化:`/chat` + `/approve` 端点,审批的"暂停-恢复"经 HTTP 两段式交互完成(`app/api.py`)
- 多轮对话记忆:State 挂载 messages 历史(add_messages reducer),ActionAgent 跨轮续办业务
- 对话式 RAG:qa 检索前用对话历史做指代消解改写(`rewrite_with_history`,"那多久换一次"→"火花塞多久换一次")
- MCP:FastMCP 服务器封装业务工具 + 客户端动态发现(`lab/lab_d9_*.py`)
- 真实语料入库:6 本车主手册 PDF → 逐页提取 + 定长/重叠切块 + 来源前缀 → 1093 块 + 8 内置片段(`lab/lab_d10_1_ingest.py` + `lab/lab_d10_2_build_corpus_db.py`)
- 评估体系:43 条评估集(13 维度)+ 评估脚本,产出路由/命中/延迟/审批指标(`data/eval_set.json` + `lab/lab_d10_3_eval.py`,详见下方「评估结果」)

**二期(生产化)**

- 退款工单化:审批脱离对话线程 —— `request_refund` 开工单(PENDING)而非 interrupt 挂起,对话立刻结束;商家控制台批复后业务系统**无 LLM 确定性执行**,结果轮询回推对话(一次性解决"审批寄生对话线程"引发的僵尸复活 / 商家批复蒸发 / 锁会话 / 端点裸奔四坑)
- Spring Boot 业务系统:订单 / 槽位 / 退款工单入 Postgres,业务规则唯一权威;Service 接口化 + DataSeeder 幂等种子(`business-system/`)
- React 前端:用户聊天窗(含澄清追问 + 工单结果回推)+ 商家审批控制台(`frontend/`)
- MCP 生产化:工具拆成独立进程(`tool-service/`,HTTP :9000),ActionAgent 经 `app/mcp_client.py`(async→sync 桥)动态发现 + 远程调用;系统参数(session_id)对 LLM 隐藏但穿透到底

### 🚧 进行中 / 📋 计划中

- 🚧 用户系统 + 鉴权:登录注册、user_id 身份、角色授权(用户 / 商家),工单绑定 user_id,商家端点鉴权
- 📋 持久化 checkpointer:MemorySaver → Postgres/Redis(重启不丢会话 + 多实例共享);跨会话长期记忆(按 user_id)
- 📋 结果回推升级:轮询 → WebSocket/SSE(实时,免刷新丢 watch)
- 📋 业务规则彻底下沉:7 天退款期校验从 Python 预检下沉 Spring Boot(唯一权威复验)
- 📋 本地模型:Ollama + Qwen2.5-7B,云端 / 本地双后端切换
- 📋 Docker / docker-compose:一键编排全套服务
- 📋 LLM-as-judge:答案质量自动评分(当前命中率用要点匹配)

## 评估结果

自建 43 条评估集(`data/eval_set.json`,覆盖 FAQ 命中/误拦、knowledge、compatibility(含带/不带年份)、diagnosis、chitchat、真投诉 vs 负面词描述故障、action(单工具/复合/高危审批)、多轮指代、多源冲突共 13 个维度;投诉用例刻意不复用检测样例以防数据泄漏),经进程内 `invoke` 直接读取路由与检索上下文计算指标(`lab/lab_d10_3_eval.py`)。

| 指标 | 结果 | 说明 |
|---|---|---|
| 路由准确率 | **~98%** | 46 条评估上全对;集合偏小且 prompt 对其迭代过,诚实报 ~98% 而非满分 |
| 检索要点命中率 | **~97%** | 期望要点出现在检索上下文/答案中的比例 |
| FAQ 拦截 / 误拦 | 命中 **100%** / 误拦 **0** | 办理类措辞不被 FAQ 劫持 |
| 投诉识别 | 召回 **100%** / 对照组误报 **0** | "刹车失灵""异响"等负面词描述故障正确判为 diagnosis |
| 端到端延迟 | P50 **3.9s** / P95 14.4s | 慢尾为 diagnosis(子问题拆解 + HyDE 多次检索) |
| 高危审批触发 | 按需 | 超期退款经工具 description 预检直接拒,无需惊动审批 |

> 评估过程反向发现并修复了 2 个真实缺陷:①图查询 `RETURN` 遗漏车型名导致答案误判"未找到"(修:返回自解释字段);②品牌中英不一致 + "货号"措辞被路由误判(修:schema 中英映射 + 路由锚点判据)。此外暴露的对话式多轮指代缺口,已由检索前改写(`rewrite_with_history`)闭环。

## 项目结构

```
.
├── app/                     # Agent 服务(FastAPI + LangGraph)
│   ├── api.py               # FastAPI:/chat 对话 + /resume 澄清恢复(session_id=thread_id;退款已工单化,无 /approve)
│   ├── agents.py            # 主流水线:LangGraph supervisor 多 Agent(路由 + 检索 + 生成 + HITL + 多轮记忆)
│   ├── mcp_client.py        # MCP 客户端:async fastmcp Client 桥成同步接口 + schema 转换 + 剥系统参数
│   ├── retriever.py         # HybridRetriever:混合检索核心模块
│   ├── query_processing.py  # 查询理解:FAQ 缓存 / 投诉检测 / 路由决策 / HyDE / 拆解
│   └── graph_retriever.py   # GraphRetriever:Text2Cypher 图检索 + 安全护栏
├── tool-service/            # MCP 工具服务(独立进程,HTTP :9000)
│   ├── server.py            # @mcp.tool 薄壳 + HTTP 传输(工具经 MCP 暴露)
│   └── tools.py             # 业务实现层:查订单/预约/退款,经 HTTP 调 Spring Boot
├── business-system/         # 业务系统(Spring Boot + JPA + Postgres):订单/槽位/退款工单 + 状态机
│   └── src/main/java/com/moto/business/   # entity / repository / service(+impl) / controller / dto
├── frontend/                # React 前端(Vite):用户聊天窗 ChatPage + 商家控制台 ConsolePage
├── data/
│   ├── moto_manual.py            # 内置保养知识片段(8 条,兜底语料)
│   ├── parts_compatibility.csv   # 配件兼容数据(品牌 / 车型 / 配件 / 年份区间)
│   ├── eval_set.json             # 评估集(43 条,13 维度)
│   ├── eval_results.json         # 评估运行结果(逐条明细,评估脚本产出)
│   └── raw_manuals/              # 手册 PDF 原件(版权物,不入库;本地自备)
├── lab/                     # 各阶段学习实验脚本(验证通过后沉淀为 app/ 正式模块)
│   ├── lab1_hello.py ~ lab6_graph_agent.py   # 基础:API / 多轮 / Function Calling / agent loop / LangGraph
│   ├── lab_d2_*.py          # embedding / 建库 / 检索 / RAG 问答
│   ├── lab_d3_*.py          # BM25 / 混合检索
│   ├── lab_d4_*.py          # 意图分类 / FAQ 缓存 / HyDE / 子问题拆解
│   ├── lab_d5_*.py          # Neo4j 连接 / CSV 导入 / Text2Cypher
│   ├── lab_d6_1_emotion.py  # 情感模型实测(被数据证伪弃用,记录见 commit)
│   ├── lab_d8_1_interrupt.py # LangGraph interrupt/checkpointer 最小验证
│   ├── lab_d9_1_mcp_server.py / lab_d9_2_mcp_client.py  # MCP 服务器 + 客户端动态发现
│   ├── lab_d10_1_ingest.py  # 手册 PDF → 切片(逐页提取 + 定长/重叠 + 来源前缀)
│   ├── lab_d10_2_build_corpus_db.py  # 切片 + 内置 DOCS → Chroma 向量库(幂等重建)
│   └── lab_d10_3_eval.py    # 评估脚本:跑评估集,产出路由/命中/延迟/审批指标
├── requirements.txt         # 依赖(锁版本)
├── VISION.md                # 产品愿景(骑行全周期助手,分期规划)
├── TODO.md                  # 推迟事项清单(YAGNI 停车场)+ 二期蓝图
└── .env.example             # 环境变量模板
```

## 快速开始

二期后系统是**多进程架构**:前端(Vite)+ Agent 服务(FastAPI)+ 工具服务(MCP)+ 业务系统(Spring Boot)+ 两个数据库(Postgres 业务数据 / Neo4j 配件图谱)。下面分「一次性准备」与「按依赖顺序启动各服务」两步。

### 一次性准备

```bash
# 1. 克隆 + 虚拟环境 + 依赖(Python 侧)
git clone https://github.com/zhongqiufeng2023-spec/motorcycle_repair_assistant.git
cd motorcycle_repair_assistant
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置密钥:复制模板,填入 DeepSeek API key、Neo4j 密码、(可选)LangSmith
cp .env.example .env

# 3. 构建向量库(向量库与手册衍生语料均不入库,须本地构建;首次会下载 BGE-M3 模型)
#    先把车主手册 PDF 放进 data/raw_manuals/(版权物,自备)
python lab/lab_d10_1_ingest.py           # 切片:PDF → data/manual_chunks.json
python lab/lab_d10_2_build_corpus_db.py  # 向量化:切片 + 内置 DOCS → Chroma 向量库
```

### 启动各服务(按依赖顺序)

```bash
# ① Postgres —— 业务数据(订单/槽位/退款工单)的唯一权威库
docker run -d --name moto-postgres -p 5433:5432 \
  -e POSTGRES_USER=moto -e POSTGRES_PASSWORD=moto -e POSTGRES_DB=moto postgres:16
#   (已建过容器则 docker start moto-postgres)

# ② Neo4j —— 配件兼容图谱,并导入数据
docker run -d --name moto-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_neo4j_password_here neo4j:5
python lab/lab_d5_2_import_csv.py

# ③ Spring Boot 业务系统(:8080)—— 订单/槽位查询 + 退款工单状态机(业务规则唯一权威)
#    需 JAVA_HOME 指向 JDK 17;首次可用 mvn 打包,之后跑 jar
cd business-system && java -jar target/business-system-0.0.1.jar   # 或 mvn spring-boot:run
cd ..

# ④ MCP 工具服务(:9000)—— 业务工具经 MCP 独立进程暴露,Agent 远程发现+调用
python tool-service/server.py

# ⑤ FastAPI Agent 服务(:8000)—— 对话/路由/检索;经 MCP 调工具、经 HTTP 调业务系统
uvicorn app.api:app --port 8000
#   /chat    对话(普通问答 / 业务办理;退款开工单并返 ticket_id)
#   /resume  澄清追问的补充回答(Command(resume) 送回挂起的 interrupt)

# ⑥ 前端(:5173)—— 用户聊天窗 + 商家审批控制台(Vite 代理 /api → :8000 与 :8080)
cd frontend && npm install && npm run dev
```

浏览器开 http://localhost:5173 用页面,或开 http://localhost:8000/docs 直接调 API。

```bash
# (可选)命令行跑完整多 Agent 流水线演示 / 单独测图检索 / 跑评估集
python app/agents.py            # 需 tool-service:9000 + Spring Boot:8080 在跑
python app/graph_retriever.py
python lab/lab_d10_3_eval.py    # 产出路由准确率 / 命中率 / 延迟等指标
```

> **不入版本控制、需本地重建的**:向量库 `data/chroma_db/`、手册 PDF `data/raw_manuals/`、切片 `data/manual_chunks.json`、Neo4j 数据、Postgres 数据(Spring Boot 启动时 `DataSeeder` 会自动灌订单/槽位种子)。手册是版权物,请自备 PDF 后跑准备第 3 步;缺语料时程序会明确提示先构建。
>
> **启动契约**:`③④` 必须先于向 Agent 发业务请求——action 路由会经 MCP(:9000)调工具、工具再经 HTTP 调 Spring Boot(:8080),缺一环则业务办理失败(FastAPI 本身可先起,工具清单首个业务请求时才懒加载)。

## 学习日志

本项目采用"边学边建"的方式推进,`lab/` 目录保留了每个能力模块的最小可运行实验,与主应用代码(`app/`)分离——实验验证通过后再沉淀为正式模块。
