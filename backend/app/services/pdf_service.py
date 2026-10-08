import io
import datetime
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors

logger = logging.getLogger(__name__)

class PDFService:
    """Generates personalized PDF certificates using a single predefined template."""

    @staticmethod
    def generate_certificate(
        recipient_name: str,
        event_name: str,
        completion_date: str,
        certificate_id: str,
    ) -> bytes:
        try:
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=landscape(letter))
            width, height = landscape(letter)

            # --- Background ---
            c.setFillColor(colors.HexColor("#F8F8F0"))
            c.rect(0, 0, width, height, fill=1, stroke=0)

            # --- Decorative border ---
            c.setStrokeColor(colors.HexColor("#2C3E50"))
            c.setLineWidth(6)
            c.rect(20, 20, width - 40, height - 40, fill=0, stroke=1)
            c.setStrokeColor(colors.HexColor("#D4AF37"))
            c.setLineWidth(2)
            c.rect(30, 30, width - 60, height - 60, fill=0, stroke=1)

            # --- Title ---
            c.setFont("Helvetica-Bold", 38)
            c.setFillColor(colors.HexColor("#2C3E50"))
            c.drawCentredString(width / 2, height - 100, "CERTIFICATE OF COMPLETION")

            # --- Divider ---
            c.setStrokeColor(colors.HexColor("#D4AF37"))
            c.setLineWidth(1.5)
            c.line(width * 0.2, height - 120, width * 0.8, height - 120)

            # --- Presented to ---
            c.setFont("Helvetica", 16)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawCentredString(width / 2, height - 170, "This certificate is")
            c.drawCentredString(width / 2, height - 195, "presented to")

            # --- Recipient name ---
            c.setFont("Helvetica-Bold", 32)
            c.setFillColor(colors.HexColor("#1A252F"))
            c.drawCentredString(width / 2, height - 250, recipient_name)

            # --- Second divider ---
            c.setStrokeColor(colors.HexColor("#D4AF37"))
            c.setLineWidth(1)
            c.line(width * 0.3, height - 270, width * 0.7, height - 270)

            # --- For completing ---
            c.setFont("Helvetica", 16)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawCentredString(width / 2, height - 310, "for successfully completing")

            # --- Event name ---
            c.setFont("Helvetica-BoldOblique", 26)
            c.setFillColor(colors.HexColor("#2C3E50"))
            c.drawCentredString(width / 2, height - 360, event_name)

            # --- Completion date ---
            c.setFont("Helvetica", 14)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawCentredString(width / 2, height - 420, f"Completion Date: {completion_date}")

            # --- Issued date ---
            issued_date = datetime.date.today().isoformat()
            c.drawCentredString(width / 2, height - 440, f"Issued: {issued_date}")

            # --- Certificate ID ---
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.HexColor("#AAAAAA"))
            c.drawCentredString(width / 2, 50, f"Certificate ID: {certificate_id}")

            c.save()
            buffer.seek(0)
            return buffer.read()
        except Exception as e:
            logger.error(f"Failed to generate PDF for recipient: {recipient_name}. Error: {e}")
            raise RuntimeError(f"PDF generation failed: {e}") from e
