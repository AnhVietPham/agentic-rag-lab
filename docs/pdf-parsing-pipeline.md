# PDF Parsing Pipeline

Giải thích cơ chế parse file PDF thành dữ liệu có cấu trúc để lưu vào PostgreSQL và index vào OpenSearch.

---

## Tổng quan

Khi bạn có một file PDF (ví dụ `2604.00362v1.pdf`), pipeline sẽ làm 3 việc:

1. **Validate** — kiểm tra file có hợp lệ không (kích thước, định dạng, số trang)
2. **Parse** — dùng thư viện Docling để đọc nội dung PDF, tách thành sections
3. **Trả về** `PdfContent` — object chứa `raw_text` + `sections` có cấu trúc

```
file.pdf
   │
   ▼
PDFParserService.parse_pdf()       ← entry point
   │
   ▼
DoclingParser._validate_pdf()      ← kiểm tra file
   │  ├─ file rỗng?         → PDFValidationError
   │  ├─ file quá lớn?      → PDFValidationError
   │  ├─ không phải PDF?    → PDFValidationError
   │  └─ quá nhiều trang?   → PDFValidationError
   │
   ▼
DoclingParser (Docling library)    ← parse nội dung
   │
   ▼
Tách sections từ doc.texts         ← xây dựng cấu trúc
   │
   ▼
PdfContent                         ← kết quả trả về
   ├─ raw_text: str                (toàn bộ text thuần)
   ├─ sections: List[PaperSection] (text đã tách theo section)
   ├─ figures: []                  (hiện tại luôn rỗng)
   └─ tables:  []                  (hiện tại luôn rỗng)
```

---

## Các file liên quan

| File | Vai trò |
|---|---|
| `src/services/pdf_parser/factory.py` | Tạo `PDFParserService` (cached, singleton) |
| `src/services/pdf_parser/parser.py` | Entry point — `PDFParserService.parse_pdf()` |
| `src/services/pdf_parser/docling.py` | Logic validate + parse thực tế |
| `src/schemas/pdf_parser/models.py` | Định nghĩa `PdfContent`, `PaperSection`, ... |

---

## Bước 1 — Tạo service (`factory.py`)

```python
from src.services.pdf_parser.factory import make_pdf_parser_service

pdf_parser = make_pdf_parser_service()
```

`make_pdf_parser_service()` dùng `@lru_cache` — chỉ tạo 1 lần duy nhất trong suốt vòng đời process. Config đọc từ `.env`:

| Biến | Default | Ý nghĩa |
|---|---|---|
| `PDF_PARSER__MAX_PAGES` | `60` | Số trang tối đa cho phép |
| `PDF_PARSER__MAX_FILE_SIZE_MB` | `20` | Kích thước file tối đa (MB) |
| `PDF_PARSER__DO_OCR` | `false` | Có dùng OCR không (chậm hơn nhiều) |
| `PDF_PARSER__DO_TABLE_STRUCTURE` | `true` | Có phân tích cấu trúc bảng không |

---

## Bước 2 — Validate file (`_validate_pdf`)

Trước khi parse, Docling kiểm tra 4 điều kiện theo thứ tự:

```
1. File có rỗng không?
   stat().st_size == 0 → PDFValidationError("PDF file is empty")

2. File có quá lớn không?
   st_size > max_file_size_bytes → PDFValidationError("PDF file too large: X MB > Y MB")

3. File có đúng định dạng PDF không?
   Đọc 8 bytes đầu, kiểm tra có bắt đầu bằng b"%PDF-" không
   → PDFValidationError("File does not have PDF header")

4. File có quá nhiều trang không?
   Dùng pypdfium2 đếm số trang thực tế
   actual_pages > max_pages → PDFValidationError("PDF has too many pages: 34 > 30")
```

> **Lưu ý quan trọng:** Với lỗi "too large" hoặc "too many pages", `DoclingParser.parse_pdf()` bắt exception và trả về `None` thay vì raise — đây là "skip" có chủ ý. Với các lỗi validate khác (rỗng, không phải PDF), exception được propagate lên.

---

## Bước 3 — Parse nội dung (Docling)

Docling là thư viện AI chuyên đọc tài liệu học thuật (PDF, DOCX, ...). Nó hiểu cấu trúc của paper: title, section headers, body text, bảng, hình.

```python
result = self._converter.convert(str(pdf_path), max_num_pages=self.max_pages)
doc = result.document
```

### Cách tách sections

Docling gán nhãn (`label`) cho từng đoạn text trong PDF:

| Label | Ý nghĩa |
|---|---|
| `"title"` | Tiêu đề chính của paper (level 0) |
| `"section_header"` | Tiêu đề section (Introduction, Methods, ...) (level 1) |
| Các label khác | Nội dung thông thường (body text, caption, ...) |

Code duyệt qua `doc.texts` và gom nội dung theo logic:

```
Gặp "title" hoặc "section_header":
  → Lưu section hiện tại (nếu có nội dung)
  → Bắt đầu section mới với title = element.text

Gặp text thông thường:
  → Append vào content của section hiện tại
```

**Ví dụ kết quả sections cho 1 paper:**

```python
[
  PaperSection(title="Attention Is All You Need", content="...", level=0),
  PaperSection(title="Abstract",                  content="...", level=1),
  PaperSection(title="1 Introduction",            content="...", level=1),
  PaperSection(title="2 Background",              content="...", level=1),
  PaperSection(title="3 Model Architecture",      content="...", level=1),
  ...
]
```

### raw_text

Ngoài sections có cấu trúc, Docling còn export toàn bộ text thuần:

```python
raw_text = doc.export_to_text()
```

`raw_text` là chuỗi text liên tục của toàn bộ PDF, không có cấu trúc — dùng làm fallback khi chunking section-based thất bại.

---

## Bước 4 — Kết quả trả về (`PdfContent`)

```python
class PdfContent(BaseModel):
    sections: List[PaperSection]   # sections đã tách
    figures:  List[PaperFigure]    # luôn [] hiện tại
    tables:   List[PaperTable]     # luôn [] hiện tại
    raw_text: str                  # toàn bộ text thuần
    references: List[str]          # luôn [] hiện tại
    parser_used: ParserType        # luôn "docling"
    metadata: Dict[str, Any]       # {"source": "docling", ...}

class PaperSection(BaseModel):
    title:   str   # tiêu đề section
    content: str   # nội dung section
    level:   int   # 0 = paper title, 1 = section header
```

**Fallback khi Pydantic validation thất bại:** Nếu sections có dữ liệu không hợp lệ, `PdfContent` được tạo lại với `sections=[]` — chỉ giữ `raw_text`. Điều này đảm bảo luôn có kết quả trả về, dù mất cấu trúc.

---

## Exception hierarchy

```
Exception
└── ParsingException
    └── PDFParsingException          ← lỗi parse chung
        └── PDFValidationError       ← lỗi validate (file rỗng, quá lớn, sai định dạng, quá trang)
```

| Exception | Khi nào xảy ra | Xử lý ở caller |
|---|---|---|
| `PDFValidationError` (too large / too many pages) | File hợp lệ nhưng vượt giới hạn | `DoclingParser` bắt → trả `None` → skip |
| `PDFValidationError` (rỗng / sai định dạng) | File thực sự lỗi | Propagate lên → `process_local_pdf` bắt → skip file, tiếp tục |
| `PDFParsingException` | Docling crash khi parse | Propagate lên → `process_local_pdf` bắt → skip file, tiếp tục |

---

## Ví dụ đầy đủ

```python
from pathlib import Path
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.exceptions import PDFParsingException, PDFValidationError

pdf_parser = make_pdf_parser_service()

try:
    pdf_content = await pdf_parser.parse_pdf(Path("data/arxiv_pdfs/2604.00362v1.pdf"))
except PDFValidationError as e:
    print(f"File không hợp lệ: {e}")
except PDFParsingException as e:
    print(f"Parse thất bại: {e}")

if pdf_content:
    print(f"raw_text length : {len(pdf_content.raw_text)} chars")
    print(f"sections        : {len(pdf_content.sections)}")
    for s in pdf_content.sections:
        print(f"  [{s.level}] {s.title[:60]} — {len(s.content)} chars")
```

**Output mẫu:**
```
raw_text length : 48320 chars
sections        : 12
  [0] Attention Is All You Need — 0 chars
  [1] Abstract — 1240 chars
  [1] 1 Introduction — 3820 chars
  [1] 2 Background — 2100 chars
  [1] 3 Model Architecture — 5640 chars
  ...
```

---

## Tại sao dùng Docling thay vì PyPDF2 / pdfplumber?

| | PyPDF2 / pdfplumber | Docling |
|---|---|---|
| **Hiểu cấu trúc** | Chỉ extract text thô | Nhận diện title, section header, bảng, hình |
| **Chất lượng text** | Thường bị lỗi spacing, line break | Tốt hơn với paper học thuật |
| **Bảng** | Không parse được | Có thể parse cấu trúc bảng (nếu bật) |
| **Tốc độ** | Nhanh | Chậm hơn (AI model) |
| **OCR** | Không | Có (nếu bật `DO_OCR=true`) |

Docling phù hợp với arxiv papers vì chúng có cấu trúc nhất quán (LaTeX → PDF) và cần tách sections chính xác để chunking tốt hơn.
