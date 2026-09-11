from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from db import get_dict_cursor

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _pdf_response(buffer: BytesIO, filename: str):
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get("/{case_id}/pdf")
def download_case_report(case_id: str):
    with get_dict_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
        case = cur.fetchone()

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        cur.execute(
            """
            SELECT *
            FROM transactions
            WHERE case_id = %s
            ORDER BY hop ASC, timestamp ASC
            """,
            (case_id,),
        )
        transactions = cur.fetchall()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(45, y, "CryptoTrace Investigation Report")
    y -= 35

    pdf.setFont("Helvetica", 10)

    fields = [
        ("Case ID", case["id"]),
        ("Complaint ID", case.get("complaint_id")),
        ("Primary Wallet", case.get("primary_wallet")),
        ("Chain", case.get("chain")),
        ("Fraud Type", case.get("fraud_type")),
        ("Status", case.get("status")),
        ("Priority", case.get("priority")),
        ("Risk Score", case.get("risk_score")),
        ("Created At", case.get("created_at")),
    ]

    for label, value in fields:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(45, y, f"{label}:")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(145, y, str(value or "—")[:100])
        y -= 16

    y -= 10

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(45, y, f"Chain-of-Custody Evidence ({len(transactions)} transactions)")
    y -= 25

    pdf.setFont("Helvetica", 7)

    for tx in transactions:
        if y < 55:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 7)

        line = (
            f"Hop {tx.get('hop', '—')} | "
            f"{str(tx.get('direction') or '—')} | "
            f"{str(tx.get('from_address') or '—')[:18]} → "
            f"{str(tx.get('to_address') or '—')[:18]} | "
            f"Tx: {str(tx.get('tx_hash') or '—')[:22]} | "
            f"Block: {tx.get('block_number') or '—'}"
        )

        pdf.drawString(45, y, line)
        y -= 12

    pdf.save()

    return _pdf_response(
        buffer,
        f"{case_id}-investigation-report.pdf",
    )