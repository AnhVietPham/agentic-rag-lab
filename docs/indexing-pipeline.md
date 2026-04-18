# Indexing Pipeline: `index_papers_to_opensearch.py`

Script này đọc các paper đã được lưu trong **PostgreSQL** và index chúng vào **OpenSearch** để phục vụ hybrid search (vector + BM25).

> Xem thêm: [Tại sao cần cả PostgreSQL lẫn OpenSearch?](./architecture-why-two-databases.md)

---

## Tổng quan flow

```
PostgreSQL (bảng papers)
        │
        │  load Paper rows
        ▼
paper_to_dict()          ← convert ORM → plain dict
        │
        ▼
HybridIndexingService.index_papers_batch()
        │
        ├─► [mỗi paper] delete old chunks (nếu replace_existing=True)
        │
        ├─► TextChunker.chunk_paper()
        │       ├─ Nếu có sections → section-based chunking
        │       └─ Nếu không        → word-window chunking (fallback)
        │
        ├─► JinaEmbeddingsClient.embed_passages()
        │       └─ POST https://api.jina.ai/v1/embeddings
        │          model: jina-embeddings-v3, task: retrieval.passage, dims: 1024
        │
        └─► OpenSearchClient.bulk_index_chunks()
                └─ index: production-agentic-rag-papers-chunks
```

---

## Cách chạy

```bash
# Index tất cả papers trong DB
python scripts/index_papers_to_opensearch.py

# Giới hạn số lượng (lấy mới nhất trước)
python scripts/index_papers_to_opensearch.py --limit 10

# Index 1 paper cụ thể theo arxiv_id
python scripts/index_papers_to_opensearch.py --arxiv-id 2604.00362v1
```

---

## Chi tiết từng bước

### Bước 1 — Load papers từ PostgreSQL

```python
# index_papers_to_opensearch.py
query = session.query(Paper).order_by(Paper.created_at.desc())
if limit:
    query = query.limit(limit)
papers = query.all()
```

- Mặc định lấy **tất cả** papers, sắp xếp mới nhất trước.
- Nếu truyền `--arxiv-id`, chỉ lấy đúng 1 paper đó.
- Sau khi load xong, convert sang `List[dict]` **trước khi đóng session** để tránh lỗi lazy-loading.

**Cấu trúc dict** được truyền xuống các bước sau:

| Field | Nguồn |
|---|---|
| `id` | `str(paper.id)` — UUID |
| `arxiv_id` | `paper.arxiv_id` |
| `title` | `paper.title` |
| `authors` | `paper.authors` — list[str] |
| `abstract` | `paper.abstract` |
| `categories` | `paper.categories` — list[str] |
| `published_date` | `paper.published_date` |
| `raw_text` | `paper.raw_text` — full text của PDF |
| `sections` | `paper.sections` — list[dict] hoặc None |

---

### Bước 2 — Chunking (`TextChunker`)

Config được đọc từ `.env` với prefix `CHUNKING__`:

| Tham số | Default | Ý nghĩa |
|---|---|---|
| `CHUNKING__CHUNK_SIZE` | `600` | Số từ tối đa mỗi chunk |
| `CHUNKING__OVERLAP_SIZE` | `100` | Số từ overlap giữa 2 chunk liền kề |
| `CHUNKING__MIN_CHUNK_SIZE` | `100` | Số từ tối thiểu để tạo chunk |

#### Strategy A: Section-based chunking (ưu tiên)

Được dùng khi paper có `sections` (list các `{title, content}`).

```
header = "{title}\n\nAbstract: {abstract}\n\n"

Với mỗi section:
  - < 100 words  → gom vào buffer, kết hợp thành 1 chunk
  - 100–800 words → 1 chunk riêng: header + "Section: {title}\n\n{content}"
  - > 800 words  → tách bằng word-window, mỗi sub-chunk prepend header
```

Mỗi chunk đều được **prepend header** (title + abstract) để cung cấp context khi retrieval.

#### Strategy B: Word-window chunking (fallback)

Dùng khi không có sections hoặc section-based thất bại.

```
words = raw_text.split()

chunk_0 = words[0 : 600]
chunk_1 = words[500 : 1100]   ← overlap 100 từ với chunk trước
chunk_2 = words[1000 : 1600]
...
```

Mỗi chunk là một `TextChunk` với metadata:

```python
class ChunkMetadata(BaseModel):
    chunk_index: int         # thứ tự chunk trong paper
    start_char: int          # vị trí ký tự bắt đầu (xấp xỉ)
    end_char: int            # vị trí ký tự kết thúc
    word_count: int          # số từ trong chunk
    overlap_with_previous: int
    overlap_with_next: int
    section_title: str | None  # chỉ có khi dùng section-based
```

---

### Bước 3 — Embedding (`JinaEmbeddingsClient`)

```
POST https://api.jina.ai/v1/embeddings
{
  "model": "jina-embeddings-v3",
  "task": "retrieval.passage",
  "dimensions": 1024,
  "input": ["chunk_text_1", "chunk_text_2", ...]
}
```

- Gửi theo **batch 50 chunks** mỗi request để tránh timeout.
- Trả về `List[List[float]]` — mỗi vector có **1024 chiều**.
- API key đọc từ `JINA_API_KEY` trong `.env`.

> **Lưu ý:** Khi query (search), dùng `task: "retrieval.query"` thay vì `"retrieval.passage"`.

---

### Bước 4 — Index vào OpenSearch (`bulk_index_chunks`)

Mỗi document được index vào OpenSearch có cấu trúc:

```json
{
  "arxiv_id": "2604.00362v1",
  "paper_id": "uuid-...",
  "chunk_index": 3,
  "chunk_text": "Section: Introduction\n\n...",
  "chunk_word_count": 487,
  "start_char": 1200,
  "end_char": 4100,
  "section_title": "Introduction",
  "embedding_model": "jina-embeddings-v3",
  "title": "...",
  "authors": "Author A, Author B",
  "abstract": "...",
  "categories": ["cs.AI"],
  "published_date": "2026-04-02T...",
  "embedding": [0.021, -0.043, ...]
}
```

**Index name:** `production-agentic-rag-papers-chunks`
(= `OPENSEARCH__INDEX_NAME` + `OPENSEARCH__CHUNK_INDEX_SUFFIX`)

Config OpenSearch trong `.env`:

| Biến | Default | Ý nghĩa |
|---|---|---|
| `OPENSEARCH__HOST` | `http://localhost:9200` | URL OpenSearch |
| `OPENSEARCH__INDEX_NAME` | `production-agentic-rag-papers` | Base index name |
| `OPENSEARCH__CHUNK_INDEX_SUFFIX` | `chunks` | Suffix → tên index thực tế |
| `OPENSEARCH__VECTOR_DIMENSION` | `1024` | Phải khớp với Jina dims |
| `OPENSEARCH__VECTOR_SPACE_TYPE` | `cosinesimil` | Metric tính khoảng cách vector |

---

### `replace_existing=True` — xử lý duplicate

Script luôn gọi với `replace_existing=True`, nghĩa là:

```
Trước khi index paper X:
  → opensearch_client.delete_paper_chunks(arxiv_id)
  → xóa toàn bộ docs có field arxiv_id == X
  → sau đó index lại từ đầu
```

Điều này đảm bảo chạy lại script nhiều lần không tạo ra duplicate chunks.

---

## Output stats

Sau khi chạy xong, script in ra:

```
Indexing complete:
  Papers processed: 18
  Chunks indexed:   342
  Errors:           0
```

Tương ứng với các field trong dict trả về từ `index_papers_batch()`:

| Field | Ý nghĩa |
|---|---|
| `papers_processed` | Số paper đã xử lý |
| `total_chunks_created` | Tổng chunks tạo ra từ chunker |
| `total_chunks_indexed` | Tổng chunks bulk-index thành công vào OpenSearch |
| `total_embeddings_generated` | Tổng vectors đã gọi Jina API |
| `total_errors` | Số lỗi (chunk level) |

---

## Full pipeline: từ PDF đến OpenSearch

```bash
# Bước 1: Parse PDF → lưu vào PostgreSQL
python scripts/process_local_pdf.py --dir data/arxiv_pdfs

# Bước 2: Load từ PostgreSQL → chunk → embed → index vào OpenSearch
python scripts/index_papers_to_opensearch.py
```

Hai bước này độc lập nhau — có thể chạy lại bước 2 bất cứ lúc nào mà không cần parse lại PDF.
