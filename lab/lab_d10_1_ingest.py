import os, json
from pypdf import PdfReader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "raw_manuals")
OUT_PATH = os.path.join(BASE_DIR, "data", "manual_chunks.json")

def extract_pages(pdf_path: str) -> list[dict]:
    reader = PdfReader(pdf_path)
    pages = []
    skipped = 0
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if len(text) < 50:
            skipped += 1
            continue
        pages.append({"page" : i, "text" : text})
    print(f"提取 {len(pages)} 页,跳过 {skipped} 页(空白/过短)")
    return pages

def chunk_pages(pages: list[dict], source: str, chunk_size: int = 500, overlap: int = 100) -> list[dict]:
    step = chunk_size - overlap          # 窗口每次往前滑多远
    chunks = []
    for p in pages:
        text = p["text"]
        for start in range(0, len(text), step):
            piece = text[start:start + chunk_size]
            if start > 0 and len(piece) <= overlap:
                break                    # 尾巴已完整躺在上一块里,不必再存
            chunks.append({"text": piece, "page": p["page"], "source": source})
    return chunks

if __name__ == "__main__":
    MANIFEST = {
        "kawasaki_ninja400_om.pdf":         "Kawasaki Ninja 400 车主手册",
        "kawasaki_ninja400_om_ktech.pdf":   "Kawasaki Ninja 400 车主手册(第2版)",
        "kawasaki_ninja650_2023_maint.pdf": "Kawasaki Ninja 650 保养手册",
        "kawasaki_z650rs_2022_om.pdf":      "Kawasaki Z650RS 车主手册",
        "yamaha_mt07_2021_om.pdf":          "Yamaha MT-07 车主手册",
        "honda_cbr650r_2022_om.pdf":        "Honda CBR650R 车主手册",
    }
    all_chunks = []
    for filename, source in MANIFEST.items():
        pages = extract_pages(os.path.join(PDF_DIR, filename))
        chunks = chunk_pages(pages, source=source)
        for c in chunks:
            c["text"] = f"【{source} P{c['page']}】{c['text']}"   # 身份烙进正文,进向量本身
        all_chunks.extend(chunks)
        print(f"  {source}: {len(pages)} 页 → {len(chunks)} 块")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)
    print(f"共 {len(all_chunks)} 块 → {OUT_PATH}")