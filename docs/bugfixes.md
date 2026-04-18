# Bug Fixes Log

---

## [BUG-001] `text_chunker.py` — 4 lỗi trong `TextChunker`

**File:** `src/services/indexing/text_chunker.py`

### Lỗi 1: `_is_duplicate_section` — sai signature

**Triệu chứng:**
```
Section-based chunking failed for 1912.03558v3:
TextChunker._is_duplicate_section() missing 1 required positional argument: 'abstract_words'
Using traditional word-based chunking for 1912.03558v3
```

**Nguyên nhân:** Method được định nghĩa với 3 params `(self, content, abstract, abstract_words)` nhưng caller ở `_filter_sections` chỉ truyền 2 args `(content_str, abstract_words)`. Param `abstract: str` thừa và không được dùng.

```python
# Trước (sai)
def _is_duplicate_section(self, content: str, abstract: str, abstract_words: set) -> bool:
    content_lower = content.lower().strip()
    abstract_lower = abstract.lower().strip()  # dùng abstract nhưng không cần thiết
    ...

# Caller truyền
if self._is_duplicate_section(content_str, abstract_words):  # thiếu 1 arg
```

**Fix:** Bỏ param `abstract: str` thừa khỏi signature.

```python
# Sau (đúng)
def _is_duplicate_section(self, content: str, abstract_words: set) -> bool:
    content_lower = content.lower().strip()
    content_words = set(content_lower.split())
    ...
```

---

### Lỗi 2: `_chunk_by_sections` — `enumerate[...]` syntax sai

**Nguyên nhân:** Python không hỗ trợ subscript `[]` trên `enumerate`. Đây là syntax của generic type hint, không phải cách gọi hàm.

```python
# Trước (sai — TypeError khi chạy)
for i, (section_title, section_content) in enumerate[tuple[str, str]](section_items):

# Sau (đúng)
for i, (section_title, section_content) in enumerate(section_items):
```

---

### Lỗi 3: `_create_section_chunk` — `word_count` dùng sai biến

**Nguyên nhân:** `chunk_index` là `int`, không có method `.split()`. Đúng ra phải dùng `chunk_text`.

```python
# Trước (sai — AttributeError: 'int' object has no attribute 'split')
word_count=len(chunk_index.split()),

# Sau (đúng)
word_count=len(chunk_text.split()),
```

---

### Lỗi 4: `chunk_text` — `_reconstruct_text` được gọi với 2 args

**Nguyên nhân:** `_reconstruct_text(self, words)` chỉ nhận 1 param nhưng được gọi với 2 args `(words, text)`.

```python
# Trước (sai — TypeError: takes 2 positional arguments but 3 were given)
text=self._reconstruct_text(words, text),

# Sau (đúng)
text=self._reconstruct_text(words),
```

---

### Tác động

Khi tất cả 4 lỗi trên tồn tại đồng thời, `_chunk_by_sections` luôn raise exception → toàn bộ paper bị fallback sang **word-window chunking** thay vì section-based chunking. Chất lượng retrieval bị ảnh hưởng vì mất context header (title + abstract) ở mỗi chunk.

---

## [BUG-002] `process_local_pdf.py` — NUL bytes trong PDF text

**File:** `scripts/process_local_pdf.py`

**Triệu chứng:**
```
ValueError: A string literal cannot contain NUL (0x00) characters.
```

**Nguyên nhân:** Một số PDF bị corrupt hoặc có encoding đặc biệt khiến PDF parser trả về text chứa ký tự `\x00` (NUL byte). PostgreSQL từ chối lưu string có NUL byte.

**Fix:** Thêm hàm `_sanitize()` strip toàn bộ `\x00` trước khi tạo `Paper` object, áp dụng cho `raw_text`, `title`, `abstract` và từng `title`/`content` trong `sections`.

```python
def _sanitize(text: str) -> str:
    """Remove NUL bytes that PostgreSQL rejects."""
    return text.replace("\x00", "")

# Áp dụng trước khi lưu
raw_text = _sanitize(pdf_content.raw_text)
sections = [
    {"title": _sanitize(s.title), "content": _sanitize(s.content)}
    for s in pdf_content.sections
]
```

**Lưu ý:** Lỗi này chỉ xuất hiện với một số PDF nhất định (thường là file scan hoặc PDF được tạo từ tool có lỗi encoding). Các PDF bình thường không bị ảnh hưởng.

---

## [BUG-004] `process_local_pdf.py` — PDF quá trang crash cả script

**Files:** `scripts/process_local_pdf.py`, `.env`

**Triệu chứng:**
```
Error validating PDF: PDF has too many pages: 34 > 30
Docling parsing returned no result for 2604.02276v1.pdf
PDFParsingException: Docling parsing returned no result for 2604.02276v1.pdf
```

**Nguyên nhân:** 2 vấn đề kết hợp:
1. `PDF_PARSER__MAX_PAGES=30` quá thấp — nhiều arxiv paper có 30–60 trang
2. `process_local_pdf` không catch `PDFParsingException` / `PDFValidationError` → exception propagate lên `process_directory` → crash toàn bộ script, bỏ qua tất cả file còn lại

**Fix 1 — Tăng giới hạn trang trong `.env`:**
```diff
- PDF_PARSER__MAX_PAGES=30
+ PDF_PARSER__MAX_PAGES=60
```

**Fix 2 — Catch exception trong `process_local_pdf`, skip file lỗi thay vì crash:**
```python
try:
    pdf_content = await pdf_parser.parse_pdf(path)
except PDFValidationError as e:
    print(f"[{arxiv_id}] Validation error (skipping): {e}")
    return False
except PDFParsingException as e:
    print(f"[{arxiv_id}] Parsing error (skipping): {e}")
    return False
```

**Kết quả:** Script tiếp tục xử lý các file còn lại thay vì dừng hẳn khi gặp 1 file lỗi.

---

## [BUG-003] Jina API — 429 Too Many Requests

**File:** `src/services/embeddings/jina_client.py` (gián tiếp qua `index_papers_to_opensearch.py`)

**Triệu chứng:**
```
Error embedding passages: Client error '429 Too Many Requests'
for url 'https://api.jina.ai/v1/embeddings'
Error indexing paper 1912.03558v3: Client error '429 Too Many Requests'
```

**Nguyên nhân:** Jina API có rate limit. Khi index nhiều paper liên tiếp, số lượng request vượt quá giới hạn cho phép của plan hiện tại.

**Fix:** Thêm method `_post_with_retry` với exponential backoff vào `JinaEmbeddingsClient`. Đồng thời giảm `batch_size` mặc định từ `100` xuống `50`.

```python
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds

async def _post_with_retry(self, url: str, payload: dict) -> httpx.Response:
    for attempt in range(_MAX_RETRIES):
        response = await self.client.post(url, headers=self.headers, json=payload)
        if response.status_code == 429:
            wait = _RETRY_BASE_DELAY * (2 ** attempt)  # 2, 4, 8, 16, 32s
            logger.warning(f"Rate limited (attempt {attempt + 1}/{_MAX_RETRIES}). Retrying in {wait:.0f}s...")
            await asyncio.sleep(wait)
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response
```

`embed_passages` và `embed_query` đều dùng `_post_with_retry` thay vì gọi `self.client.post` trực tiếp.
