import os,re
from dotenv import load_dotenv
from openai import OpenAI
from neo4j import GraphDatabase

load_dotenv()
llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("BASE_URL"))
driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

WRITE_PATTERN = r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DETACH|DROP)\b"
GRAPH_SCHEMA = """
节点(Node):
- Brand: 品牌。属性: name(如 "Kawasaki")
- Model: 车型。属性: name(如 "Ninja 400")
- Part: 配件。属性: name(如 "NGK CPR8EA-9"), category(类别,如 "火花塞"/"机油"/"刹车油"), part_number(配件号)

关系(Relationship):
- (Brand)-[:HAS_MODEL]->(Model): 品牌拥有车型
- (Model)-[c:COMPATIBLE_WITH]->(Part): 车型兼容配件。关系属性: year_from(起始适用年), year_to(结束适用年)

重要规则:
- 判断某年份是否适用,用 c.year_from <= 年份 AND 年份 <= c.year_to
"""

def is_read_only(cypher: str) -> bool:
    return re.search(WRITE_PATTERN, cypher, re.IGNORECASE) is None

def generate_cypher(question: str) -> str:
    prompt = f"""你是 Neo4j 查询专家。根据下面的图谱 schema,把用户问题翻译成一条 Cypher 查询。

    【图谱 Schema】
    {GRAPH_SCHEMA}

    【硬性要求】
    - 只返回一条 Cypher 语句,不要任何解释,不要 markdown 代码块。
    - 只能是只读查询(MATCH/WHERE/RETURN),禁止 CREATE/MERGE/DELETE/SET。

    【用户问题】
    {question}

    Cypher:"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role" : "user", "content" : prompt}],
        temperature = 0,
    )
    text = resp.choices[0].message.content.strip()
    text = text.replace("'''cypher'''","").replace("'''","").strip()
    return text
def safe_run(cypher: str):
    if not is_read_only(cypher):
        return {"ok": False, "error": "拒绝执行:检测到写操作"}
    
    with driver.session() as session:
        try:
            session.run("EXPLAIN"+ " " + cypher).consume()
        except Exception as e:
             return {"ok": False, "error": f"EXPLAIN 校验失败: {e}"}
    
        result = session.run(cypher)
        return {"ok": True, "rows": [dict(r) for r in result]}

def answer_from_graph(question: str, rows: list) -> str:
    # 空结果兜底:查不到就老实说,别编(和 _generate 里"手册没查到"一个思路)
    if not rows:
        return "抱歉,知识图谱里没有查到相关信息。"

    prompt = f"""你是摩托车配件客服。根据下面从知识图谱查到的数据,用自然、简洁的中文回答用户问题。
只依据数据回答,数据里没有的不要编造。

【用户问题】
{question}

【图谱查询结果】
{rows}

【回答】"""
    resp = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()

if __name__ == "__main__":
    tests = [
        "Ninja 400 在 2020 年能用什么火花塞?",
        "NGK CPR8EA-9 这个火花塞还有哪些车型能用?",
    ]
    for q in tests:
        print("=" * 50)
        print("问题:", q)
        cypher = generate_cypher(q)
        print("Cypher:", cypher)
        res = safe_run(cypher)
        if res["ok"]:
            print("答案:", answer_from_graph(q, res["rows"]))
        else:
            print("查询失败:", res["error"])
    driver.close()