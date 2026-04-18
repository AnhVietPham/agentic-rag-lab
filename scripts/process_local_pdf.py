import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
from uuid import uuid4

from src.db.factory import make_database
from src.exceptions import PDFParsingException, PDFValidationError
from src.models.paper import Paper
from src.services.pdf_parser.factory import make_pdf_parser_service


def _sanitize(text: str) -> str:
    """Remove NUL bytes that PostgreSQL rejects."""
    return text.replace("\x00", "")


async def process_local_pdf(pdf_path: Path, arxiv_id: str | None = None) -> bool:
    path = Path(pdf_path)
    if not path.exists():
        print(f"File not found: {path}")
        return False

    if not arxiv_id:
        arxiv_id = path.stem

    pdf_parser = make_pdf_parser_service()
    try:
        pdf_content = await pdf_parser.parse_pdf(path)
    except PDFValidationError as e:
        print(f"[{arxiv_id}] Validation error (skipping): {e}")
        return False
    except PDFParsingException as e:
        print(f"[{arxiv_id}] Parsing error (skipping): {e}")
        return False

    if not pdf_content or not pdf_content.raw_text:
        print(f"[{arxiv_id}] PDF parsing failed or no text extracted")
        return False

    now = datetime.now(timezone.utc)
    raw_text = _sanitize(pdf_content.raw_text)
    sections = [
        {"title": _sanitize(s.title), "content": _sanitize(s.content)}
        for s in pdf_content.sections
    ]

    paper = Paper(
        id=uuid4(),
        arxiv_id=arxiv_id,
        title=raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
        authors=["Unknown"],
        abstract=raw_text[:500] + "..." if len(raw_text) > 500 else raw_text,
        categories=["cs.AI"],
        published_date=now,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        raw_text=raw_text,
        sections=sections if sections else None,
        pdf_processed=True,
        pdf_processing_data=now,
    )

    database = make_database()
    database.startup()

    with database.get_session() as session:
        existing = session.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
        if existing:
            print(f"[{arxiv_id}] Already exists in DB, skipping.")
            return True
        session.add(paper)
        session.commit()

    print(f"[{arxiv_id}] Stored to database.")
    return True


async def process_directory(directory: Path) -> dict:
    pdf_files = sorted(directory.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in: {directory}")
        return {"total": 0, "success": 0, "failed": 0}

    print(f"Found {len(pdf_files)} PDF(s) in {directory}\n")
    success, failed = 0, 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Processing: {pdf_path.name}")
        ok = await process_local_pdf(pdf_path)
        if ok:
            success += 1
        else:
            failed += 1

    return {"total": len(pdf_files), "success": success, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="Process local PDF(s) into PostgreSQL")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Path to a single PDF file")
    group.add_argument("--dir", type=str, help="Path to a directory of PDF files")
    parser.add_argument("--arxiv-id", type=str, default=None, help="Override arxiv_id (only for --file)")
    args = parser.parse_args()

    if args.dir:
        directory = Path(args.dir)
        if not directory.is_dir():
            print(f"Not a valid directory: {directory}")
            sys.exit(1)
        stats = asyncio.run(process_directory(directory))
        print(f"\nDone. Total: {stats['total']} | Success: {stats['success']} | Failed: {stats['failed']}")
    else:
        ok = asyncio.run(process_local_pdf(Path(args.file), args.arxiv_id))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
  
