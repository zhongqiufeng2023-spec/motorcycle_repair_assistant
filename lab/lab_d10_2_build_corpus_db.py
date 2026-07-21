"""全量重建向量库:手册 chunks + 手写 DOCS → Chroma collection "manual"

跑之前确保 lab_d10_1 已生成 data/manual_chunks.json。
幂等:先删后建,跑几遍结果都一样。
"""
import os, sys, json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.moto_manual import DOCS
from FlagEmbedding import BGEM3FlagModel
import chromadb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_PATH = os.path.join(BASE_DIR, "data", "manual_chunks.json")
CHROMA_PATH = os.path.join(BASE_DIR, "data", "chroma_db")


def main():
    # 1. 合成语料:手册 chunks(已带【来源 P页】前缀)+ 8 条手写中文 DOCS
    #    manual_chunks.json 由 lab_d10_1 切片产出、不入库;缺它就明确报错,不静默降级。
    if not os.path.exists(CHUNKS_PATH):
        raise FileNotFoundError(
            "未找到 data/manual_chunks.json,请先跑切片:python lab/lab_d10_1_ingest.py"
            "(需先把手册 PDF 放进 data/raw_manuals/)"
        )
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    corpus = [c["text"] for c in chunks] + list(DOCS)
    print(f"语料总量 {len(corpus)} 条(手册 {len(chunks)} + 手写 {len(DOCS)})")

    # 2. 先删后建(删不存在的 collection 会抛异常,吞掉即可)
    db = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        db.delete_collection("manual")
        print("旧 collection 已删除")
    except Exception:
        print("无旧 collection,直接新建")
    collection = db.create_collection("manual")

    # 3. 批量编码(整列表一次传入;max_length=512 够 500 字符的 chunk)
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    vecs = model.encode(corpus, batch_size=32, max_length=512)["dense_vecs"]
    print(f"编码完成,shape = {vecs.shape}")   # 自检:必须是 (语料总量, 1024)

    # 4. 入库
    collection.add(
        ids=[str(i) for i in range(len(corpus))],
        documents=corpus,
        embeddings=vecs.tolist(),
    )
    print(f"入库完成,collection 'manual' 现有 {collection.count()} 条")


if __name__ == "__main__":
    main()