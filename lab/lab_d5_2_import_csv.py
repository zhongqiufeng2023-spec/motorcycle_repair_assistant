import os, csv
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
driver = GraphDatabase.driver(
  os.getenv("NEO4J_URI"),
  auth = (os.getenv("NEO4J_USER"),os.getenv("NEO4J_PASSWORD")),
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "parts_compatibility.csv")

def import_row(tx, row):
    tx.run(
        """

        MERGE (b:Brand{name: $brand})
        MERGE (m:Model {name: $model})
        MERGE (p:Part {name: $part_name, category: $part_category})
        SET p.part_number = $part_number
        MERGE (b)-[:HAS_MODEL]->(m)
        MERGE (m)-[c:COMPATIBLE_WITH]->(p)
        SET c.year_from = toInteger($year_from), c.year_to = toInteger($year_to)
        """,
        **row,
    )

with driver.session() as session:
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader :
            session.execute_write(import_row, row)

with driver.session() as session:
    n = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    r = session.run("MATCH ()-[:COMPATIBLE_WITH]->() RETURN count(*) AS c").single()["c"]
    print(f"节点数：{n}，兼容关系数：{r}")

driver.close()
