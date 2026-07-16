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

- [ ] **action_node 从占位变成真 ActionAgent(D8 主菜)**
  - 是什么:当前 `action_node` 只返回一句诚实的占位话术。D8 要做:mock 业务工具(查订单/预约/退换货)+ Function Calling 调度 + 高危操作 LangGraph interrupt 人工审核(HITL)+ Reflection 失败自愈重试(≤3 次)。
  - 为什么现在不做:HITL 依赖 checkpointer/interrupt 基础设施,和 D8 是连体工程;拆开做会返工。
  - 顺带修:投诉/转人工话术要与真实能力对齐(现在承诺"已转接人工"但无此机制,D8 用"登记工单"类真动作替代)。

- [ ] **拆出 `models.py` / `schemas.py`**
  - 是什么:把 Pydantic 模型(目前只有 `RouteDecision`)集中到独立文件。
  - 为什么推迟:目前只有一个模型、一个使用者,就近放在 `query_processing.py` 里可读性更好。
  - 什么时候回来:模型多到 3-5 个,或出现跨文件复用时;D9 做 FastAPI 请求/响应模型时会自然触发,和 `config.py` 集中、db 层抽取一起做。

- [ ] **只读的数据库级兜底(Neo4j 只读权限用户)**
  - 是什么:给数据库开一个只有读权限的账号,让数据库本身拒绝写操作,而不只靠应用层关键词扫描。
  - 为什么推迟:应用层 `WRITE_PATTERN` 正则扫描当前已够用。
  - 什么时候回来:项目工程化 / 部署(D9 或 D12)做纵深防御时。

---

> 项目级的长期 TODO 另见 CLAUDE.md 第 8 节(FAQ 增删改查、LLM 客户端解耦、向量库规模化等)。这份文件专收「随做随记」的推迟项。
