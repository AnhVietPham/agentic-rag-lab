# Tại sao cần cả PostgreSQL lẫn OpenSearch?

Vì chúng giải quyết **2 bài toán khác nhau** mà không cái nào làm tốt được cả hai.

---

## So sánh vai trò

| | PostgreSQL | OpenSearch |
|---|---|---|
| **Vai trò** | Source of truth — lưu trữ lâu dài | Search engine — tìm kiếm nhanh |
| **Đơn vị lưu** | 1 paper = 1 row | 1 chunk = 1 document |
| **Mạnh ở** | ACID, join, filter chính xác, tracking trạng thái | Semantic search (vector), full-text search (BM25) |
| **Yếu ở** | Không search ngữ nghĩa được | Không phù hợp làm nguồn dữ liệu gốc |
| **Khi nào dùng** | Lưu, update, re-index khi cần | Query lúc user đặt câu hỏi |

---

## Mối quan hệ giữa 2 DB

```
PostgreSQL                          OpenSearch
─────────────────                   ──────────────────────────────────
paper (1 row)          ──►          chunk_0  + embedding vector
  id: uuid                          chunk_1  + embedding vector
  raw_text: ~15,000 từ              chunk_2  + embedding vector
  sections: [...]                   ...
                                    chunk_N  + embedding vector

                                    Mỗi chunk có paper_id → link về Postgres
```

Một paper dài ~15,000 từ không thể embed trực tiếp thành 1 vector — model embedding có giới hạn token và độ chính xác giảm mạnh với văn bản quá dài. Vì vậy paper được **tách thành nhiều chunks nhỏ (~600 từ)**, mỗi chunk có 1 vector riêng.

---

## Flow khi user đặt câu hỏi

```
User: "What are the latest advances in RAG?"
        │
        ▼
embed_query()  →  query vector [1024 dims]
        │
        ▼
OpenSearch hybrid search
  ├─ Vector search  (cosine similarity với embedding)
  └─ BM25 search    (keyword matching)
        │
        ▼
Top-K chunks  (kèm paper_id, chunk_text)
        │
        ▼ (nếu cần full context)
Postgres: SELECT * FROM papers WHERE id = paper_id
        │
        ▼
LLM generates answer
```

---

## Tại sao không dùng chỉ 1 DB?

### Nếu chỉ dùng PostgreSQL

- `WHERE abstract LIKE '%RAG%'` — chỉ tìm được từ khóa chính xác
- Không hiểu được câu hỏi ngữ nghĩa: *"retrieval augmented generation"* ≠ *"RAG"* với Postgres
- Không có BM25, không có vector index

### Nếu chỉ dùng OpenSearch

- Lưu toàn bộ `raw_text` vào mỗi chunk → dữ liệu trùng lặp khổng lồ
- Khi cần thay đổi chunking strategy hoặc embedding model → **mất toàn bộ dữ liệu gốc**
- Không có ACID transactions, không phù hợp để track trạng thái xử lý (`pdf_processed`, `created_at`, ...)

---

## Lợi ích của việc tách biệt

Khi cần thay đổi embedding model (ví dụ từ `jina-embeddings-v3` sang model mới):

```bash
# Xóa toàn bộ OpenSearch index
# Re-index lại từ Postgres — dữ liệu gốc vẫn còn nguyên

python scripts/index_papers_to_opensearch.py
```

Postgres là **nguồn sự thật duy nhất** — OpenSearch chỉ là một **derived view** có thể tái tạo bất cứ lúc nào.
