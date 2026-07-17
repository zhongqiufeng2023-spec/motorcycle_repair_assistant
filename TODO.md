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

- [ ] **多轮对话记忆(State 挂 messages 历史)**
  - 是什么:AgentState 加 `messages: Annotated[list, add_messages]`,同一 thread_id 连续对话时 agent 记得上文——"请问退款原因?"用户下一句回答才接得住(澄清追问/slot filling 的地基)。
  - 为什么推迟:D8 已重到爆,且多轮记忆牵动 supervisor/所有节点的消息构造方式,是独立的一块工程。
  - 什么时候回来:D9 做 /chat 端点(session_id=thread_id)时一并做,正好是它的自然形态。

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

- [ ] **checkpoint 反序列化白名单警告(RouteDecision)**
  - 现象:挂上 MemorySaver 后每次读档打警告 "Deserializing unregistered type app.query_processing.RouteDecision from checkpoint. This will be blocked in a future version."
  - 原因:checkpointer 读档要重建自定义类实例,LangGraph 正在收紧为白名单制(防反序列化攻击,同 Java readObject CVE 的思路)。目前仅警告,功能正常。
  - 修法二选一:①按提示把 ('app.query_processing','RouteDecision') 注册进 allowed_msgpack_modules(D9 查文档);②更优:State 里不存富对象——decision 存 model_dump() 的 dict,Pydantic 只在 LLM 边界校验(序列化边界只过数据不过行为,同 Java 的 DTO 纪律)。
  - 什么时候回来:D9 工程化时一并处理。

- [ ] **只读的数据库级兜底(Neo4j 只读权限用户)**
  - 是什么:给数据库开一个只有读权限的账号,让数据库本身拒绝写操作,而不只靠应用层关键词扫描。
  - 为什么推迟:应用层 `WRITE_PATTERN` 正则扫描当前已够用。
  - 什么时候回来:项目工程化 / 部署(D9 或 D12)做纵深防御时。

---

> 项目级的长期 TODO 另见 CLAUDE.md 第 8 节(FAQ 增删改查、LLM 客户端解耦、向量库规模化等)。这份文件专收「随做随记」的推迟项。
