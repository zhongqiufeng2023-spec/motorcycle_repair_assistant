import os, json
from pypdf import PdfReader
import pdfplumber

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "raw_manuals")
OUT_PATH = os.path.join(BASE_DIR, "data", "manual_chunks.json")


def build_section_map(pdf_path: str) -> dict[int, str]:
    """读 PDF 书签大纲(outline),产出 {页号(1-based): 章节路径}。
    章节路径形如 'MAINTENANCE AND ADJUSTMENT › Engine Oil'(父级书签用 › 拼)。
    书签只标每节的【起始页】,中间页用"最近生效的那一节"回填。
    没有大纲的 PDF → 全部标 '(未分节)',优雅退化。
    """
    reader = PdfReader(pdf_path)
    total = len(reader.pages)

    # 1) 展平大纲 → [(起始页, 章节路径)]。
    #    pypdf 用"嵌套 list"表示子书签:某个 list 紧跟在它的父书签之后。
    starts: list[tuple[int, str]] = []

    def walk(items, trail):
        last_title = None                     # 记住上一个书签,好认它的子列表的父亲
        for it in items:
            if isinstance(it, list):          # 子书签群 → 父亲是 last_title
                walk(it, trail + ([last_title] if last_title else []))
            else:
                try:
                    pn = reader.get_destination_page_number(it) + 1   # 0-based → 1-based
                except Exception:
                    continue                  # 个别书签目标解析不了,跳过
                title = str(it.title)
                starts.append((pn, " › ".join(trail + [title])))
                last_title = title

    try:
        walk(reader.outline, [])
    except Exception:
        pass                                  # 没大纲/读不了 → starts 为空,下面全标未分节

    # 2) 把"起始页"展开成"每页归属":排序后,相邻两个起点之间的页都归前者。
    starts.sort(key=lambda x: x[0])           # 稳定排序:同页多书签保持大纲顺序,最后一个(最深)胜出
    page_section: dict[int, str] = {}
    for idx, (pn, path) in enumerate(starts):
        next_pn = starts[idx + 1][0] if idx + 1 < len(starts) else total + 1
        # 近似:一页只归一节。若某节从页中间才起(情况B),整页归后者、前半段会误贴;
        # 当前语料章节多从页顶起,未咬人。字符级修法见 TODO.md「章节切分的页级近似」。
        for p in range(pn, next_pn):
            page_section[p] = path            # 同页多书签→空区间自动让最深/最后那节胜出
    for p in range(1, total + 1):
        page_section.setdefault(p, "(未分节)")  # 大纲之前的封面/目录页兜底
    return page_section

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


def _table_to_text(table, min_rows: int = 3, min_cols: int = 3, min_fill: float = 0.4) -> str | None:
    """extract_tables() 抓到的一张表 → 文本(每行单元格用 | 拼);判废返回 None。
    阈值由实测定:MT-07 好表非空率 57-71%、CBR 抽不到勾选的废表仅 16%、误报表≤2 列;
    行≥3 且 列≥3 且 非空率≥0.4 一刀切掉误报与抽不全的废表。"""
    rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in table]
    n_cols = max((len(r) for r in rows), default=0)
    total = sum(len(r) for r in rows)
    filled = sum(1 for r in rows for c in r if c)
    if len(rows) < min_rows or n_cols < min_cols or total == 0 or filled / total < min_fill:
        return None
    return "\n".join(" | ".join(r) for r in rows if any(r))


def process_pdf(pdf_path: str, source: str, chunk_size: int = 500, overlap: int = 100, x_tol: float = 1.5) -> list[dict]:
    """章节感知切分:pdfplumber 提正文按章节切窗 + build_section_map 打章节戳;
    有框线的好表(_table_to_text 过滤后)整表原子成块、不切窗。
    产出 [{"text": 带身份前缀的块, "page": 页, "source": 来源, "section": 章节路径}, ...]。
    """
    section_of = build_section_map(pdf_path)      # {页号: 章节路径},已实现,直接查表
    chunks: list[dict] = []
    step = chunk_size - overlap  
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):   # i 从 1 开始,与 section_of 页号对齐
            section = section_of[i]
            prefix = f"【{source} P{i} · {section}】"
            # 先抓有框线好表:命中就整表原子成块(不切窗),并跳过本页散文避免重复
            # text_x_tolerance=x_tol:让单元格内文字也吃 1.5 档,否则 Ninja 那种紧字距表会粘死
            raw_tables = page.extract_tables(table_settings={"text_x_tolerance": x_tol, "text_y_tolerance": x_tol})
            tables = [t for t in (_table_to_text(tb) for tb in raw_tables) if t]
            if tables:
                for tbl in tables:
                    chunks.append({"text": prefix + "【表格】\n" + tbl,
                                   "page": i, "source": source, "section": section})
                continue                          # 本页以表格为准,不再切散文(footnote 少量丢失,记 TODO)
            text = (page.extract_text(x_tolerance=x_tol) or "").strip()   # x_tol=1.5:拆开粘连词/型号/尺寸(默认会把 NGK LMAR9G、0.7-0.8mm 粘死)
            if len(text) < 50:                    # 沿用空页过滤(扫描件/空白页跳过)
                continue
            for start in range(0, len(text), step):
                piece = text[start:start + chunk_size]
                if start > 0 and len(piece) <= overlap:
                    break
                chunks.append({
                    "text":    prefix + piece,
                    "page":    i,
                    "source":  source,
                    "section": section,
                })                
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
    # 开发期输出到 v2,不覆盖线上 manual_chunks.json(作者定的"不急重建库";验证满意后再改名+重建库)
    OUT_V2 = os.path.join(BASE_DIR, "data", "manual_chunks_v2.json")
    all_chunks = []
    for filename, source in MANIFEST.items():
        chunks = process_pdf(os.path.join(PDF_DIR, filename), source)   # 章节感知 + pdfplumber(x_tol=1.5)
        all_chunks.extend(chunks)
        n_pages = len(set(c["page"] for c in chunks))                   # 出了块的页数(扫描件=0)
        print(f"  {source}: {n_pages} 页有效 → {len(chunks)} 块")

    with open(OUT_V2, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)
    print(f"共 {len(all_chunks)} 块 → {OUT_V2}")