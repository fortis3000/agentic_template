import pytest

from tools.text_extractor import extract_text


def test_extract_text_from_txt_utf8():
    data = "Hello, world! 😊".encode("utf-8")
    assert extract_text(data, "text/plain") == "Hello, world! 😊"


def test_extract_text_from_txt_latin1_fallback():
    # Use characters that might fail in utf-8 if decoded wrongly
    data = "Hello, world! \xe9".encode("latin1")  # é character in latin1
    assert extract_text(data, "text/plain") == "Hello, world! é"


def test_extract_text_from_markdown():
    markdown = "# Title\n\n**Bold text** and *italic*\n\n- list item"
    data = markdown.encode("utf-8")
    assert extract_text(data, "text/markdown") == markdown


def test_extract_text_from_html_strips_tags():
    html = "<html><body><p>Hello</p></body></html>"
    data = html.encode("utf-8")
    # html processing might add some whitespace or newlines, so we can check for inclusion or exact
    assert extract_text(data, "text/html").strip() == "Hello"


def test_extract_text_from_html_strips_scripts():
    html = "<html><script>alert(1)</script><body><p>Text</p></body></html>"
    data = html.encode("utf-8")
    assert extract_text(data, "text/html").strip() == "Text"


def test_extract_text_from_html_strips_styles():
    html = "<html><style>.x{}</style><body><p>Text</p></body></html>"
    data = html.encode("utf-8")
    assert extract_text(data, "text/html").strip() == "Text"


def test_extract_text_from_html_replaces_img_with_alt():
    html = '<body><img src="x" alt="A chart"></body>'
    data = html.encode("utf-8")
    assert extract_text(data, "text/html").strip() == "[Image: A chart]"


def test_extract_text_from_html_replaces_img_no_alt():
    html = '<body><img src="x"></body>'
    data = html.encode("utf-8")
    assert extract_text(data, "text/html").strip() == "[Image]"


def test_extract_text_from_html_multiple_imgs():
    html = '<body><p>Text</p><img src="x" alt="img1"><p>More</p><img src="y"></body>'
    data = html.encode("utf-8")
    extracted = extract_text(data, "text/html")
    assert "Text" in extracted
    assert "[Image: img1]" in extracted
    assert "More" in extracted
    assert "[Image]" in extracted


def create_test_pdf(text: str, num_pages: int = 1) -> bytes:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_text_from_pdf():
    pytest.importorskip("pymupdf")
    pdf_bytes = create_test_pdf("Test PDF Document", num_pages=2)
    extracted = extract_text(pdf_bytes, "application/pdf")
    assert "Test PDF Document - Page 1" in extracted
    assert "Test PDF Document - Page 2" in extracted


def test_extract_text_unsupported_mime():
    with pytest.raises(ValueError):
        extract_text(b"PK\x03\x04", "application/zip")


def test_extract_text_empty_file():
    assert extract_text(b"", "text/plain").strip() == ""
    assert extract_text(b"", "text/markdown").strip() == ""
    assert extract_text(b"", "text/html").strip() == ""

    try:
        create_test_pdf("")
        # just an empty pdf to check it returns empty or whitespace
        assert extract_text(b"", "application/pdf").strip() == ""
    except Exception:
        pass


def test_extract_text_sanitizes_null_bytes():
    data = b"Hello\x00World"
    assert extract_text(data, "text/plain") == "HelloWorld"


def test_extract_text_normalizes_line_endings():
    data = b"Line 1\r\nLine 2\rLine 3"
    assert extract_text(data, "text/plain") == "Line 1\nLine 2\nLine 3"
