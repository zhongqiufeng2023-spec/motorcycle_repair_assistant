"""D10 评估脚本:跑 eval_set.json,产出路由准确率/检索命中率/延迟等指标。

用法:python lab/lab_d10_3_eval.py
说明:直接在进程内 invoke app_graph(不走 HTTP),以便读到 result["contexts"] 算检索命中率。
前置:Neo4j 容器 + tool-service(:9000) + Spring Boot(:8080) 都要在跑;全程 40+ 次 LLM 调用,约 5-15 分钟。
"""
import os, sys, json, time, uuid
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.agents import app_graph
from langgraph.types import Command

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(BASE_DIR, "data", "eval_set.json")
OUT_PATH = os.path.join(BASE_DIR, "data", "eval_results.json")


MAX_CLARIFY = 4      # 一条用例最多陪聊几轮澄清;防 LLM 反复追问把评估卡死


def _clarify_text(payload: dict) -> str:
    """把一次澄清追问的 interrupt 载荷拍平成一段文本(问句 + 选项)。
    选项也要收:"约满改约哪天"这类追问,可约日期是【放在 options 里】给出的,
    只收问句会把系统真正给出的信息漏掉。"""
    parts = [payload.get("question") or ""]
    parts += [str(o) for o in (payload.get("options") or [])]
    return " ".join(p for p in parts if p)


def run_once(question: str, thread_id: str, replies: list[str] | None = None) -> dict:
    """跑一条问题,返回评估要用的字段。

    replies = 这条用例【预先写好的用户答话脚本】,按澄清追问出现的顺序逐条喂回。
    为什么不能再用固定的 "yes"(2026-07-26 修):interrupt 现在承载的是【澄清追问】
    (退款已工单化,不再走 interrupt 审批)。系统问"您想约哪一天",喂 "yes" 等于答非所问,
    LLM 只能【再问一次】→ 第二次 interrupt。而老代码只 resume 一次,于是返回值还挂在
    interrupt 上,answer 是空串,hit_points 拿空串去匹配必然判未命中——
    系统做对了(带着可约日期在问),却被评估记成失败。命中率因此是【假的】。

    返回 {route, contexts, answer, latency, clarifies, stuck, unused_replies, ticket_id}
    - clarifies: 系统问出的每一句追问(含选项),要纳入命中判定
    - stuck: 脚本喂完了系统还在问 → 记下最后那句。宁可显式报"卡住",不拿 "yes" 糊弄过去
    """
    replies = list(replies or [])
    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()
    result = app_graph.invoke(
        # 入口重置的字段要与 api.py 的 /chat 保持一致,否则评估跑的和线上跑的不是同一件事
        {"question": question, "session_id": thread_id,
         "messages": [{"role": "user", "content": question}],
         "contexts": [], "answer": "", "route": "", "decision": None, "ticket_id": None},
        config,
    )
    clarifies, stuck = [], None
    while "__interrupt__" in result:        # 是 while 不是 if:一次追问答完可能还有下一次
        payload = result["__interrupt__"][0].value
        clarifies.append(_clarify_text(payload))
        if len(clarifies) > MAX_CLARIFY:
            stuck = f"澄清超过 {MAX_CLARIFY} 轮仍未收敛"
            break
        if not replies:                     # 脚本没写答话:如实记为卡住,不伪造回答
            stuck = payload.get("question")
            break
        result = app_graph.invoke(Command(resume=replies.pop(0)), config)
    latency = time.time() - t0
    return {
        "route": result.get("route", ""),
        "contexts": result.get("contexts", []) or [],
        "answer": result.get("answer", "") or "",
        "latency": latency,
        "clarifies": clarifies,
        "stuck": stuck,
        "unused_replies": len(replies),     # 脚本给多了 = 系统比预期少问,也是信号
        "ticket_id": result.get("ticket_id"),
    }


def hit_points(points: list[str], contexts: list[str], answer: str, clarifies: list[str]):
    """期望要点是否全部出现在 contexts / answer / 澄清追问里。points 为空 → None(N/A,不计入命中率)。
    先去掉所有空白再匹配:规避"7 天"vs"7天"、"DID 520"vs"DID520"这类纯格式差异造成的假阴性。
    (注意:这只治空白,治不了"满了"vs"已满"这种真措辞差异——那要靠 expected_points 写得鲁棒。)

    追问也算命中来源:"这天约满了,改约 19 还是 20?"——可约日期就在【问句本身】里,
    它是系统给出的正确信息,只是恰好长成了一个问句。只认最终 answer 会把它判成漏答。

    代价(写 expected_points 时必须知道):追问文本进了 blob,就可能让用例靠【系统问的话】
    命中,而不是靠【系统做的事】。例:追问里同时报了 07-19 和 07-20,那么把日期写进要点后,
    哪怕 LLM 最终订错了天也照样命中。所以凡是要判"办对了没有"的要点,别写追问里已有的串
    ——那属于子串指标测不了的部分(同 comp-05 的假阳性),得靠看 answer 或 LLM-judge。
    """
    if not points:
        return None
    blob = "".join((" ".join(contexts) + " " + answer + " " + " ".join(clarifies)).split())
    return all("".join(p.split()) in blob for p in points)


def _route_ok(got: str, expected: str) -> bool:
    """路由比对。多意图的 route 形如 "qa/knowledge+action/-",而【段的顺序没有执行语义】
    ——条件边返回列表是并行扇出,两段同一超步一起跑,谁在前纯看 LLM 怎么排 intents。
    所以按【集合】比,不按字符串比;单意图时集合只有一个元素,与原来的字符串相等判定完全等价。"""
    return set(got.split("+")) == set(expected.split("+"))


def _judge(rid: str, category: str, spec: dict, r: dict) -> dict:
    """一条运行结果 → 一条评估记录。spec 是评估集里的条目(或多轮里的一轮)。"""
    return {
        "id": rid,
        "category": category,
        "expected": spec["expected_route"],
        "got": r["route"],
        "route_ok": _route_ok(r["route"], spec["expected_route"]),
        "hit": hit_points(spec.get("expected_points", []), r["contexts"], r["answer"], r["clarifies"]),
        "latency": round(r["latency"], 2),
        "clarifies": r["clarifies"],
        "stuck": r["stuck"],
        "unused_replies": r["unused_replies"],
        "ticket_id": r["ticket_id"],
        "answer": r["answer"],
    }


def main():
    with open(EVAL_PATH, encoding="utf-8") as f:
        items = json.load(f)

    records = []
    for item in items:
        if "turns" in item:                       # 多轮:共用一个 thread_id,历史才接得上
            tid = uuid.uuid4().hex
            for i, turn in enumerate(item["turns"], 1):
                r = run_once(turn["input"], tid, turn.get("resume"))
                records.append(_judge(f"{item['id']}#t{i}", item["category"], turn, r))
                print(f"  跑完 {item['id']}#t{i}  [{r['route']}]  {r['latency']:.1f}s")
        else:                                     # 单轮:每条全新 thread_id,互相隔离
            r = run_once(item["input"], uuid.uuid4().hex, item.get("resume"))
            records.append(_judge(item["id"], item["category"], item, r))
            print(f"  跑完 {item['id']}  [{r['route']}]  {r['latency']:.1f}s")

    # ---------- 明细(路由错的一眼看到错成了什么) ----------
    print("\n===== 明细 =====")
    for rec in records:
        mark = "OK" if rec["route_ok"] else "XX"
        hit = {True: "要点命中", False: "要点未中", None: "----"}[rec["hit"]]
        tag = f" <追问x{len(rec['clarifies'])}>" if rec["clarifies"] else ""
        if rec["stuck"]:
            tag += " <卡在追问:脚本没给答话>"
        if rec["unused_replies"]:
            tag += f" <脚本剩{rec['unused_replies']}条没用上>"
        print(f"[{mark}] {rec['id']:<18} 期望:{rec['expected']:<18} 实际:{rec['got']:<18} {hit}{tag}  {rec['latency']}s")

    # ---------- 汇总 ----------
    total = len(records)
    ok = sum(r["route_ok"] for r in records)
    print("\n===== 汇总 =====")
    print(f"路由准确率: {ok}/{total} = {ok/total:.0%}")

    by_cat = defaultdict(list)
    for rec in records:
        by_cat[rec["category"]].append(rec)
    for cat, rs in sorted(by_cat.items()):
        c_ok = sum(r["route_ok"] for r in rs)
        print(f"  {cat:<22} {c_ok}/{len(rs)}")

    judged = [r for r in records if r["hit"] is not None]
    if judged:
        h = sum(r["hit"] for r in judged)
        print(f"要点命中率: {h}/{len(judged)} = {h/len(judged):.0%}(仅统计带期望要点的项)")

    lats = sorted(r["latency"] for r in records)
    p50 = lats[int(len(lats) * 0.5)]
    p95 = lats[min(int(len(lats) * 0.95), len(lats) - 1)]
    print(f"端到端延迟: P50 {p50:.1f}s / P95 {p95:.1f}s")

    # 澄清追问:触发多少次、有几条卡住(卡住 = 系统在问、脚本没给答话,这条的命中率不可信)
    clar = [r for r in records if r["clarifies"]]
    stuck = [r for r in records if r["stuck"]]
    print(f"澄清追问触发: {len(clar)}/{total} 条,共 {sum(len(r['clarifies']) for r in clar)} 次"
          f";其中卡住 {len(stuck)} 条" + (f" → {[r['id'] for r in stuck]}" if stuck else ""))

    # 高危(退款)现在走【工单化】而非 interrupt 审批:看的是有没有真开出工单号
    highrisk = [r for r in records if r["category"] == "action_highrisk"]
    if highrisk:
        print(f"高危退款开单: {sum(bool(r['ticket_id']) for r in highrisk)}/{len(highrisk)}(退款已工单化,不再走 interrupt)")

    # 原始记录落盘,便于逐条复盘和 D13 写简历时取数
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n明细已存 {OUT_PATH}")


if __name__ == "__main__":
    main()
