import jieba
from rank_bm25 import BM25Okapi
import sys, os 
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from data.moto_manual import DOCS

tokenized_docs = [list(jieba.cut(doc)) for doc in DOCS]


print("第一条只是分词后：")
print(tokenized_docs[0][:15],"...\n")

bm25 = BM25Okapi(tokenized_docs)

def bm25_search(question, top_k = 3):
    tokenized_query =  list(jieba.cut(question))
    scores = bm25.get_scores(tokenized_query)
    top_idx = sorted(range(len(scores)), key = lambda i : scores[i], reverse = True)[:top_k]
    return [(DOCS[i], scores[i]) for i in top_idx]

question = "火花塞CPR8EA-9的电极间隙"
print(f"问题：{question}\n关键词检索结果:")
for doc, score in bm25_search(question):
    print(f"[BM25分{score:.2f}]{doc}")