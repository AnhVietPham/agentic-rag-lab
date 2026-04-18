import asyncio
from pathlib import Path

from src.services.pdf_parser.factory import make_pdf_parser_service


async def main() -> None:
    pdf_parser = make_pdf_parser_service()

    pdf_path = Path("notebooks/week2/data/arxiv_pdfs/2602.21204v1.pdf")

    result = await pdf_parser.parse_pdf(pdf_path)
    print("Parsed PDF content:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())

