import os, re
from dotenv import load_dotenv
from openai import OpenAI
from neo4j import GraphDatabase
from langsmith.wrappers import wrap_openai

class GraphRetriever:
    WRITE_PATTERN = r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DETACH|DROP)\b"

    GRAPH_SCHEMA = """
    节点(Node):
    - Brand: 品牌。属性: name(如 "Kawasaki")
    - Model: 车型。属性: name(如 "Ninja 400")
    - Part: 配件。属性: name(如 "NGK CPR8EA-9"), category(类别,如 "火花塞"/"机油"), part_number

    关系(Relationship):
    - (Brand)-[:HAS_MODEL]->(Model): 品牌拥有车型
    - (Model)-[:COMPATIBLE_WITH]->(Part): 车型兼容配件
      该关系带属性: year_from(起始适用年), year_to(结束适用年)

    重要规则:
    - 要读取或过滤 year_from / year_to,必须先在模式中给这条关系绑定变量,
      例如写成 -[c:COMPATIBLE_WITH]- 或 <-[c:COMPATIBLE_WITH]-,之后才能用 c.year_from。
      不绑定就直接引用 c 会报 "Variable c not defined"。
    - 判断某年份是否适用:c.year_from <= 年份 AND 年份 <= c.year_to
    - 查询配件时尽量一并返回 c.year_from 和 c.year_to,以便告知用户适用年款。
    - 品牌名在图中一律用英文存储:Honda / Yamaha / Kawasaki / Suzuki / KTM。
      用户若用中文(本田/雅马哈/川崎/铃木/KTM),必须翻译成英文再匹配,例如 本田→Honda。
      车型名保持原样(如 MT-07、CB400、Ninja 400)。
    - RETURN 必须让每行结果"自解释":正向查询要带上车型名 m.name,反向查询要带上 b.name 和 m.name。
      否则答案层只拿到孤立的配件数据(如"DID 520 链条"),无法确认是哪辆车的,会误判成"没查到"。

    示例(正向查询,RETURN 带 m.name 让结果自解释):
    问:Yamaha MT-07 的链条用哪款?
    Cypher:MATCH (b:Brand {name:'Yamaha'})-[:HAS_MODEL]->(m:Model {name:'MT-07'})-[c:COMPATIBLE_WITH]->(p:Part {category:'链条'})
           RETURN m.name, p.name, p.part_number, c.year_from, c.year_to

    示例(反向查询,注意关系上绑定了 c):
    问:NGK CPR8EA-9 还能装哪些车?
    Cypher:MATCH (p:Part {name:'NGK CPR8EA-9'})<-[c:COMPATIBLE_WITH]-(m:Model)<-[:HAS_MODEL]-(b:Brand)
           RETURN b.name, m.name, c.year_from, c.year_to
    """

    def __init__(self):
        load_dotenv()
        self.llm = wrap_openai(OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),
                          base_url=os.getenv("BASE_URL")))
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