import jieba, os , sys
from FlagEmbedding import BGEM3FlagModel
from rank_bm25 import BM25Okapi
import chromadb
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from data.moto_manual import DOCS
from sentence_transformers import CrossEncoder

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16 = True)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db = chromadb.PersistentClient(path = os.path.join(BASE_DIR, "chroma_db"))
collection = db.get_collection("manual")
reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)

tokenized_docs = [list(jieba.cut(d)) for d in DOCS]
bm25 = BM25Okapi(tokenized_docs)

def dense_rank(question, top_k = 5):
    q_vec = model.encode([question])['dense_vecs']
    res = collection.query(query_embeddings = [q_vec[0].tolist()], n_results = top_k)
    docs = res["documents"][0]
    return {doc: rank for rank, doc in enumerate(docs)}

def sparse_rank(question, top_k = 5):
    scores = bm25.get_scores(list(jieba.cut(question)))
    top_idx = sorted(range(len(scores)), key = lambda i : scores[i], reverse = True)[:top_k]
    return {DOCS[i]: rank for rank, i in enumerate(top_idx)}

def rrf_fusion(question, top_k = 3, k = 60):
    dense = dense_rank(question)
    sparse = sparse_rank(question)
    all_docs = set(dense) | set(sparse)

    scores = {}
    for doc in all_docs:
        score = 0
        if doc in dense:
            score += 1/(k + dense[doc])
        if doc in sparse:
            score += 1/(k + sparse[doc])
        scores[doc] = score

    ranked = sorted(scores.items(), key = lambda x : x[1], reverse = True)
    return ranked[:top_k]

def rerank(question, candidates, top_k = 3):
    pairs = [[question, doc] for doc in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates,scores), key = lambda x: x[1], reverse = True)
    return ranked[:top_k]

question = "火花塞CPR8EA-9的电极间隙是多少"
coarse = [doc for doc, _ in rrf_fusion(question, top_k = 6)]
final = rerank(question, coarse)

print(f"问题:{question}\n融合后结果:")
for doc, score in final:
    print(f"  [相关性 {score:.4f}] {doc}")

