import os, re
from dotenv import load_dotenv
from openai import OpenAI
from neo4j import GraphDatabase


class GraphRetriever:
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

    def __init__(self):
        load_dotenv()
        self.llm = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),
                          base_url="https://api.deepseek.com")
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
        )

    def _generate_cypher(self, question: str) -> str:
        prompt = f"""你是 Neo4j 查询专家。根据下面的图谱 schema,把用户问题翻译成一条 Cypher 查询。

        【图谱 Schema】
        {self.GRAPH_SCHEMA}

        【硬性要求】
        - 只返回一条 Cypher 语句,不要任何解释,不要 markdown 代码块。
        - 只能是只读查询(MATCH/WHERE/RETURN),禁止 CREATE/MERGE/DELETE/SET。

        【用户问题】
        {question}

        Cypher:"""
        resp = self.llm.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role" : "user", "content" : prompt}],
            temperature = 0,
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```cypher```","").replace("```","").strip()
        return text

    def _is_read_only(self, cypher: str) -> bool:
        return re.search(self.WRITE_PATTERN, cypher, re.IGNORECASE) is None

    def _run(self, cypher: str) -> dict:
    
        with self.driver.session() as session:
            try:
                session.run("EXPLAIN"+ " " + cypher).consume()
            except Exception as e:
                return {"ok": False, "error": f"EXPLAIN 校验失败: {e}"}
    
            result = session.run(cypher)
            return {"ok": True, "rows": [dict(r) for r in result]}

    def retrieve(self, question: str) -> dict:
        """对外唯一入口:问题 → Cypher → 结构化事实(不生成答案)"""
        cypher = self._generate_cypher(question)
        if not self._is_read_only(cypher):
            return {"ok": False, "cypher": cypher, "error": "拒绝执行:检测到写操作"}
        result = self._run(cypher)
        result["cypher"] = cypher   # 带上 cypher 方便溯源/调试
        return result

    def close(self):
        self.driver.close()


if __name__ == "__main__":
    tests = [
        "Ninja 400 在 2020 年能用什么火花塞?",
        "NGK CPR8EA-9 这个火花塞还有哪些车型能用?",
    ]
    tr = GraphRetriever()
    for q in tests:
        print(tr.retrieve(q))
    
    tr.close()