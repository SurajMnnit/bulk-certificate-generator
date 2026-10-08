import uuid
import pypdf
import io
import pytest

from app.services.pdf_service import PDFService

def test_pdf_generation_content():
    """Verify that the generated PDF contains the required certificate information."""
    recipient_name = "Jane Doe"
    event_name = "Advanced Python Architecture"
    completion_date = "2026-10-08"
    cert_id = str(uuid.uuid4())

    pdf_bytes = PDFService.generate_certificate(
        recipient_name=recipient_name,
        event_name=event_name,
        completion_date=completion_date,
        certificate_id=cert_id
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    
    # Read the PDF using pypdf to verify text content
    pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(pdf_reader.pages) == 1
    
    page = pdf_reader.pages[0]
    text = page.extract_text()

    assert "CERTIFICATE OF COMPLETION" in text
    assert recipient_name in text
    assert event_name in text
    assert completion_date in text
    assert cert_id in text
    assert "Certificate ID:" in text
    assert "Issued:" in text
    assert "for successfully completing" in text

def test_pdf_generation_handles_errors():
    """Verify that generation raises a RuntimeError on failure."""
    
    # Mocking canvas.Canvas to raise an error
    from unittest.mock import patch
    with patch("app.services.pdf_service.canvas.Canvas", side_effect=Exception("Canvas Error")):
        with pytest.raises(RuntimeError) as exc_info:
            PDFService.generate_certificate(
                recipient_name="Test User",
                event_name="Test Event",
                completion_date="2026-10-08",
                certificate_id=str(uuid.uuid4())
            )
        assert "PDF generation failed: Canvas Error" in str(exc_info.value)
