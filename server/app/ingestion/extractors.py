"""Text extraction for website and uploaded document formats."""

from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


def extract_html(value: str) -> tuple[str, str]:
    """Extract a title and visible main text from HTML."""

    soup = BeautifulSoup(value, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Web document"
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    return title, soup.get_text("\n", strip=True)


def extract_upload(filename: str, media_type: str, value: bytes) -> str:
    """Extract UTF-8 text from supported TXT, PDF, and DOCX uploads."""

    suffix = Path(filename).suffix.casefold()
    if suffix == ".txt" or media_type.startswith("text/plain"):
        return value.decode("utf-8-sig")
    if suffix == ".pdf" or media_type == "application/pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(value)).pages)
    if suffix == ".docx" or "wordprocessingml" in media_type:
        return "\n".join(paragraph.text for paragraph in Document(BytesIO(value)).paragraphs)
    raise ValueError("Only TXT, PDF, and DOCX uploads are supported")
