import jieba
from FlagEmbedding import BGEM3FlagModel
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
import chromadb

class HybridRetriever:

    def __init__(self, docs: list[str], chroma_path: str, collection_name: str = "manual"):
        self.docs = docs
        
        self.embed_model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
        self.reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length = 512)


        db = chromadb.PersistentClient(path = chroma_path)
        self.collection = db.get_collection(collection_name)


        self.bm25 = BM25Okapi([list(jieba.cut(d))for d in docs])

    def _dense_rank(self, question, top_k = 5):
        q_vec = self.embed_model.encode([question])['dense_vecs']
        res = self.collection.query(query_embeddings=[q_vec[0].tolist()], n_results = top_k)
        return {doc: rank for rank, doc in enumerate(res['documents'][0])}
    
    def _sparse_rank(self, question, top_k = 5):
        scores = self.bm25.get_scores(list(jieba.cut(question)))
        top_idx = sorted(range(len(scores)), key = lambda i : scores[i], reverse = True)[: top_k]
        return {self.docs[i] : rank for rank, i in enumerate(top_idx)}
    
    def _rrf(self, question, top_k = 6, k =60):
        dense = self._dense_rank(question)
        sprase = self._sparse_rank(question)
        scores = {}
        
        for doc in set(dense) | set(sprase):
            s = 0
            if doc in dense: s += 1 /(k + dense[doc])
            if doc in sprase: s += 1 /(k + sprase[doc])
            scores[doc] = s

        return [doc for doc, _ in sorted(scores.items(), key = lambda x : x[1], reverse = True)][:top_k]
    
    def retrieve(self, question: str, top_k: int = 3) -> list[str]:
        coarse = self._rrf(question, top_k = 6)
        pairs = [[question, doc] for doc in coarse]
        scores = self.reranker.predict(pairs)
        ranked = sorted(zip(coarse, scores), key = lambda x : x[1], reverse = True)
        return [doc for doc, _ in ranked[:top_k]]    