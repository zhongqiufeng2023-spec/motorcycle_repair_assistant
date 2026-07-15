import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth = (os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),

)

with driver.session() as session:
  result = session.run("RETURN 1 AS n")
  print("连接成功，返回：",result.single()["n"])

driver.close()