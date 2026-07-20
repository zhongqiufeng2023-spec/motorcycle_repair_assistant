"""D10 评估脚本:跑 eval_set.json,产出路由准确率/检索命中率/延迟等指标。

用法:python lab/lab_d10_3_eval.py
说明:直接在进程内 invoke app_graph(不走 HTTP),以便读到 result["contexts"] 算检索命中率。
前置:Neo4j 容器要在跑(compatibility 项要查图);全程 40+ 次 LLM 调用,约 5-15 分钟。
"""
import os, sys, json, time, uuid
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.agents import app_graph
from langgraph.types import Command

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(BASE_DIR, "data", "eval_set.json")
OUT_PATH = os.path.join(BASE_DIR, "data", "eval_results.json")


def run_once(question: str, thread_id: str) -> dict:
    """跑一条问题,返回评估要用的字段。

    返回 {route, contexts, answer, latency, pending}
    - pending=True 表示触发了人工审批(高危项的正确行为);随后自动 resume 'yes' 跑完
    """
    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()
    result = app_graph.invoke(
        {"question": question, "messages": [{"role": "user", "content": question}],
         "contexts": [], "answer": "", "route": "", "decision": None},
        config,
    )
    pending = "__interrupt__" in result
    if pending:                       # 高危挂起:评估时自动放行,好看后续答案
        result = app_graph.invoke(Command(resume="yes"), config)
    latency = time.time() - t0
    return {
        "route": result.get("route", ""),
        "contexts": result.get("contexts", []) or [],
        "answer": result.get("answer", "") or "",
        "latency": latency,
        "pending": pending,
    }


def hit_points(points: list[str], contexts: list[str], answer: str):
    """期望要点是否全部出现在 contexts 或 answer 里。points 为空 → None(N/A,不计入命中率)。
    先去掉所有空白再匹配:规避"7 天"vs"7天"、"DID 520"vs"DID520"这类纯格式差异造成的假阴性。
    (注意:这只治空白,治不了"满了"vs"已满"这种真措辞差异——那要靠 expected_points 写得鲁棒。)
    """
    if not points:
        return None
    blob = "".join((" ".join(contexts) + " " + answer).split())
    return all("".join(p.split()) in blob for p in points)


def _judge(rid: str, category: str, spec: dict, r: dict) -> dict:
    """一条运行结果 → 一条评估记录。spec 是评估集里的条目(或多轮里的一轮)。"""
    return {
        "id": rid,
        "category": category,
        "expected": spec["expected_route"],
        "got": r["route"],
        "route_ok": r["route"] == spec["expected_route"],
        "hit": hit_points(spec.get("expected_points", []), r["contexts"], r["answer"]),
        "latency": round(r["latency"], 2),
        "pending": r["pending"],
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
                r = run_once(turn["input"], tid)
                records.append(_judge(f"{item['id']}#t{i}", item["category"], turn, r))
                print(f"  跑完 {item['id']}#t{i}  [{r['route']}]  {r['latency']:.1f}s")
        else:                                     # 单轮:每条全新 thread_id,互相隔离
            r = run_once(item["input"], uuid.uuid4().hex)
            records.append(_judge(item["id"], item["category"], item, r))
            print(f"  跑完 {item['id']}  [{r['route']}]  {r['latency']:.1f}s")

    # ---------- 明细(路由错的一眼看到错成了什么) ----------
    print("\n===== 明细 =====")
    for rec in records:
        mark = "OK" if rec["route_ok"] else "XX"
        hit = {True: "要点命中", False: "要点未中", None: "----"}[rec["hit"]]
        pend = " <审批>" if rec["pending"] else ""
        print(f"[{mark}] {rec['id']:<18} 期望:{rec['expected']:<18} 实际:{rec['got']:<18} {hit}{pend}  {rec['latency']}s")

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

    highrisk = [r for r in records if r["category"] == "action_highrisk"]
    if highrisk:
        print(f"高危审批触发: {sum(r['pending'] for r in highrisk)}/{len(highrisk)}")

    # 原始记录落盘,便于逐条复盘和 D13 写简历时取数
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n明细已存 {OUT_PATH}")


if __name__ == "__main__":
    main()
