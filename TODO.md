# TODO —— 推迟事项(YAGNI 停车场)

> 这里记的是**当前刻意不做、但以后可能要做**的事。每条都写清:是什么、为什么推迟、什么时候回来做。
> 原则:主线优先,别被这些勾走注意力;真到了该做的节点再翻这份清单。

## D5(图检索)期间推迟的

- [x] **Pydantic 结构化校验** ✅ D6 已落地
  - 在 `RouteDecision`(target/strategy 双字段 Literal 枚举)上启用,`model_validate_json` 解析+校验一步到位,ValidationError 兜底走 qa/knowledge。
  - 后续扩展点:Text2Cypher 的输出、D9 FastAPI 的请求/响应模型。

- [x] **图问题的拆解 / 路由** ✅ D6 已落地
  - `decide_route` 一次 LLM 调用同时决定 target(qa/action/chitchat)与 strategy(knowledge/compatibility/diagnosis),compatibility 走 GraphRetriever。

- [ ] **schema 自动导出**
  - 是什么:用 `CALL db.schema.visualization()` 自动生成图谱 schema 字符串,替代手写。
  - 为什么推迟:当前图小且固定,手写 schema 更清晰,还能顺手把业务规则(如年份区间判断)写进去,自动导出给不了这个。
  - 什么时候回来:节点/关系类型变多、手维护 schema 字符串变累时。

- [ ] **澄清追问 / slot filling(关键信息缺失时反问用户)**
  - 是什么:用户问"Ninja 400 用什么火花塞"没给年份时,反问"请问是哪一年的车?",拿到后再查。
  - 为什么推迟:①当前数据每个"车型+部位"只有一行,不给年份也只返回一个正确答案,缺年份是优雅降级不是 bug;②澄清需要多轮状态 + 暂停/恢复机制,而 LangGraph 的 checkpointer 和 interrupt 天生干这个——现在手搓一套状态管理,到时全得扔。
  - 当前的低成本替代:让 Cypher 一并返回 `year_from`/`year_to`,答案里自报"适用 2018–2023 年款",用户自证,不多花一轮交互。
  - 什么时候回来:D8(LangGraph interrupt 到位)之后;或数据里真出现"同车型同部位、不同年份不同配件"的歧义时。

- [ ] **投诉检测阈值重新校准**
  - 是什么:`detect_complaint` 的 `threshold=0.65` 目前只用 11 条手造样本定的,大概率过拟合。
  - 当前依据:真投诉最低 0.734、中性提问最高 0.558,0.65 两边余量均衡。
  - 什么时候回来:D10 建评估体系时,用几十条真实分布样本重新画分数分布、重定阈值。同时补上召回率/误报率指标。
  - 附注:第一次尝试用 HF 情感模型(uer/roberta-base-finetuned-dianping-chinese)做第一层,实测在本领域完全失效——中性提问"机油多久换一次"负面分 0.991,高于真投诉 0.986,无任何阈值可分。原因是严重分布外(该模型训练于大众点评餐馆评论)。改用 BGE-M3 对投诉样例做语义匹配后分离度良好。

- [ ] **删掉 `classify_intent`(被 `decide_route` 取代后)**
  - 是什么:`decide_route` 一次返回 target+strategy,是 `classify_intent` 的升级版,两者功能重叠。
  - 状态更新(D6 收尾):rag.py 已删,`classify_intent` 在 app/ 内已无使用者,删除条件已满足。暂留一版,下次动 `query_processing.py` 时顺手删。

- [x] **action_node 从占位变成真 ActionAgent** ✅ D8 已落地
  - tools.py(mock 工具+Schema+高危名单)+ Function Calling 循环 + interrupt 审批(denied_tools 防重复申请)+ Reflection(≤3 次,驳回不反思)。
  - 遗留:投诉话术仍承诺"转人工"但无真实机制,待 D9 API 化时对齐(改"登记工单");多轮追问见下一条。

- [x] **多轮对话记忆(State 挂 messages 历史)** ✅ D9 已落地
  - `messages: Annotated[list, add_messages]` + 入口塞用户消息 + `_final()` 统一记账 + `_history()` 翻译层(LangChain 对象→openai dict,滑动窗口 n=10)。
  - 落地范围:**账本五路全记,读者只开通 action**(跨轮续办业务已验证:不重报订单号即可退款)。qa/supervisor 读历史见下面两条新 TODO。

- [ ] **对话式 RAG:qa 路读历史(指代消解改写后再检索)**
  - 是什么:用户先问火花塞再问"那多久换一次?",需先用历史把问题改写成完整问法,再进检索——直接拿指代性问题检索,召回是垃圾。
  - 为什么推迟:独立的一块工程(改写 prompt + 评估改写质量),D9 已满载。
  - 什么时候回来:D10 评估集里放几条多轮指代用例,数据说明损失有多大再决定优先级。

- [ ] **supervisor 路由读历史(裸回复场景)**
  - 是什么:agent 反问"请问订单号?"后用户光回一句"12345",decide_route 没有上下文会迷路(大概率误进 qa)。
  - 什么时候回来:与上一条同批;届时 decide_route 加最近几条历史作路由上下文。

- [ ] **ActionAgent 接入 MCP(工具动态发现进主流水线)**
  - 是什么:action_node 启动时经 MCP 客户端 `tools/list` 发现工具、`tools/call` 调用,替代本地 TOOLS_SCHEMA/TOOL_REGISTRY。
  - 为什么推迟(刻意决策):工具与 Agent 当前**同进程**,MCP 的互操作收益尚不存在;接入需在同步 action 循环里桥接异步客户端,且 D8 验证过的 interrupt/反思链路要全部重测——为不存在的收益付真实复杂度。协议层已在 lab 验证(lab_d9_1 服务器 + lab_d9_2 动态发现)。
  - 什么时候回来:二期 Spring Boot 业务系统独立部署时(工具真正住进另一个进程,HTTP 传输),或 D12 工程化若有余力。

- [ ] **图片型 PDF 的 OCR 接入(650 系手册)**
  - 现象:Ninja 650 保养手册(78 页)与 Z650RS 车主手册(174 页)是扫描件,pypdf 提取 0 页(全被 50 字符过滤器拦下,skipped 计数当场现形)。
  - 方案:①优先找文字型替代版本(明天补货时);②真要吃扫描件就上 OCR(PaddleOCR 中文友好),是独立一摊工程。
  - 什么时候回来:D10 补语料时先试①;②进二期。

- [ ] **手写 DOCS 与官方手册的冲突治理**
  - 现象:DOCS 里"机油容量约 1.8 升"与官方手册 1.6/2.0L 并存,生成层如实呈现冲突并建议以官方为准(行为正确)。
  - 待办:D10 评估集收录"多源冲突"用例;长期需要数据权威级标注(官方手册 > 店家笔记)。

- [ ] **检索按 source 元数据过滤**
  - 是什么:问题里带车型时,Chroma 用 where={"source": ...} 只搜对应手册,精度暴涨(当前靠前缀文本进向量硬扛)。
  - 什么时候回来:D10 评估如果显示跨手册污染显著,立刻做;否则二期。

- [ ] **语料缺失时的降级启动**
  - 现象:agents.py 启动时读 data/manual_chunks.json,新 clone 的仓库没有这个文件(版权物不入库)会直接崩。
  - 修法:try/except 降级为仅 DOCS 启动 + 打警告;README 写清"跑 lab_d10_1/2 重建语料"。
  - 什么时候回来:D12 仓库公开前必须做。

- [ ] **interrupt 与 LLM 同居一节点:重放非确定性风险(复习日实验实锤,2026-07-19)**
  - 实验:s9 退款挂起 → 同 session 插问"查订单12346" → 旧 interrupt 被新一轮作废,但 LLM 从 messages 账本里"复活"退款、产生新 interrupt(payload 的 user_question 已变为新问题,铁证);商家此时 /approve yes → 200 done,但重放时 LLM(temp=0 仍漂移)改走"查单+反问退款原因"路径,未再调 request_refund → interrupt 未被执行,yes 无人消费,**退款未执行且零报错**。
  - 根因:interrupt 的"确定性重放"承诺被重放路径上的 LLM 调用破坏(工作流引擎要求重放代码确定性,LLM 天然不满足)。
  - 修法:①把审批拆进无 LLM 的确定性小节点(工具调用决策先提交 State,审批节点只做 interrupt+执行已锁定调用);②或审批工单化与对话流解耦(二期 Spring Boot 方案,与 /approve 鉴权同批)。另:/chat 对"pending 中插新话"应有明确策略(提示挂起审批存在)。
  - 什么时候回来:二期业务系统设计时;D13 面试讲稿必收此实验(设计实验→证伪预测→发现脆弱性→架构结论,完整方法论闭环)。

- [ ] **/approve 端点鉴权(作者复习日自己发现的真漏洞)**
  - 现象:/approve 无任何认证,用户拿着自己的 session_id 就能自批退款(POST /approve decision=yes),HITL 闸门形同虚设。
  - 辨析:诱导 LLM 说 yes 是打不穿的(approval 的数据源只有 Command(resume),与 LLM 输出通道不相交);真正的洞在端点裸奔。
  - 修法:认证 + 角色授权(商家角色才能调 /approve),用户端/商家端两个受众分离;审批操作留审计日志。
  - 什么时候回来:D12 工程化或二期(Spring Boot 网关做鉴权是自然位置)。

- [ ] **MemorySaver 换持久化 checkpointer**
  - 是什么:当前 checkpoint 在 uvicorn 进程内存里,重启服务=所有会话(含挂起中的审批)蒸发。
  - 什么时候回来:D12 工程化/二期(SqliteSaver 或 RedisSaver,顺带解决多实例部署的会话共享)。

- [ ] **拆出 `models.py` / `schemas.py`**
  - 是什么:把 Pydantic 模型(目前只有 `RouteDecision`)集中到独立文件。
  - 为什么推迟:目前只有一个模型、一个使用者,就近放在 `query_processing.py` 里可读性更好。
  - 什么时候回来:模型多到 3-5 个,或出现跨文件复用时;D9 做 FastAPI 请求/响应模型时会自然触发,和 `config.py` 集中、db 层抽取一起做。

- [ ] **FAQ 误拦截"办理类请求"(加 LLM 意图确认层?)**
  - 现象(D8 实测):"订单12345这个东西我不想要了,退货"(要**办理**退货)被 FAQ 语义匹配劫走,返回了退货**政策**——答非所问,且 action/HITL 流程全被绕过。
  - 根因:语义相似度**认话题不认意图**("我要退货"和"退货政策是什么"话题重合)——与情绪层"认话题不认褒贬"(服务真好 vs 服务真差)是同一盲区的两副面孔。
  - 当前修法(免费):FAQ 样例措辞全部政策问句化("退货政策是什么/怎么退货/退货有什么条件"),删掉与办理语气接近的样例。
  - 未来方案:复用情绪拦截的**双层模式**——FAQ 语义命中后加一层轻量 LLM 判断"问信息 or 要办事",是办事则放行给 decide_route。代价:FAQ 命中从 0 次 LLM 变 1 次(仍比全链路便宜)。折中:仅在相似度模糊带(如 0.75-0.85)触发确认,高分段直接放行。
  - 什么时候回来:D10 评估集必须包含"FAQ 误拦率"指标;数据说明误拦真实存在再上这层,别拍脑袋加。

- [x] **checkpoint 反序列化白名单警告(RouteDecision)** ✅ D9 已修
  - 采用方案②:State 不存富对象——decision 经 `model_dump()` 脱壳成 dict 再入 State,Pydantic 只在 LLM 输出边界校验(序列化边界只过数据不过行为,同 Java 的 DTO 纪律)。警告消除。
  - 同批完成:投诉话术与真实能力对齐("转接人工"→"登记工单,人工客服尽快跟进")。

- [ ] **只读的数据库级兜底(Neo4j 只读权限用户)**
  - 是什么:给数据库开一个只有读权限的账号,让数据库本身拒绝写操作,而不只靠应用层关键词扫描。
  - 为什么推迟:应用层 `WRITE_PATTERN` 正则扫描当前已够用。
  - 什么时候回来:项目工程化 / 部署(D9 或 D12)做纵深防御时。

---

> 项目级的长期 TODO 另见 CLAUDE.md 第 8 节(FAQ 增删改查、LLM 客户端解耦、向量库规模化等)。这份文件专收「随做随记」的推迟项。
