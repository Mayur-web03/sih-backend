from io import BytesIO
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from db import get_connection, get_dict_cursor

router = APIRouter(
    prefix="/api/freeze-requests",
    tags=["freeze-requests"],
)


class FreezeRequestCreate(BaseModel):
    case_id: str
    reason: str
    triggered_by: str = "investigator"


class FreezeRequestAction(BaseModel):
    actor: str = "investigator"


class FreezeRequestReject(BaseModel):
    actor: str = "investigator"
    reason: str


class FreezeRequestExecute(BaseModel):
    actor: str = "investigator"
    execution_reference: str
    execution_details: Optional[str] = None


# ---------------------------------------------------------------------------
# Create (existing endpoint — now inserts as 'Pending' + writes an audit row)
# ---------------------------------------------------------------------------
@router.post("")
def create_freeze_request(payload: FreezeRequestCreate):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, primary_wallet, chain, complaint_id, risk_score
                FROM cases
                WHERE id = %s
                """,
                (payload.case_id,),
            )
            case = cur.fetchone()

            if not case:
                raise HTTPException(
                    status_code=404,
                    detail="Case not found",
                )

            wallet_address = case[1]
            chain = case[2]
            complaint_id = case[3]
            risk_score = case[4]

            cur.execute(
                """
                INSERT INTO freeze_requests (
                    wallet_address,
                    case_id,
                    reason,
                    triggered_by,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, now())
                RETURNING id, created_at
                """,
                (
                    wallet_address,
                    payload.case_id,
                    payload.reason,
                    payload.triggered_by,
                    "Pending",
                ),
            )

            request_row = cur.fetchone()
            request_id = request_row[0]
            created_at = request_row[1]

            cur.execute(
                """
                INSERT INTO freeze_request_audit (
                    request_id,
                    case_id,
                    action,
                    previous_status,
                    new_status,
                    actor,
                    details
                )
                VALUES (
                    %s, %s, 'created', NULL, 'Pending', %s,
                    'Freeze request created from investigation'
                )
                """,
                (
                    request_id,
                    payload.case_id,
                    payload.triggered_by,
                ),
            )

        conn.commit()

    return {
        "id": request_id,
        "case_id": payload.case_id,
        "wallet_address": wallet_address,
        "reason": payload.reason,
        "triggered_by": payload.triggered_by,
        "status": "Pending",
        "created_at": created_at,
        "chain": chain,
        "complaint_id": complaint_id,
        "risk_score": risk_score,
    }


# ---------------------------------------------------------------------------
# List all freeze requests for a case
# ---------------------------------------------------------------------------
@router.get("/cases/{case_id}")
def list_case_freeze_requests(case_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    fr.id,
                    fr.wallet_address,
                    fr.case_id,
                    fr.reason,
                    fr.triggered_by,
                    fr.status,
                    fr.created_at,
                    fr.updated_at,
                    fr.reviewed_by,
                    fr.reviewed_at,
                    fr.rejection_reason,
                    fr.execution_reference,
                    fr.execution_details,
                    c.chain,
                    c.complaint_id,
                    c.risk_score
                FROM freeze_requests fr
                JOIN cases c ON c.id = fr.case_id
                WHERE fr.case_id = %s
                ORDER BY fr.created_at DESC
                """,
                (case_id,),
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "wallet_address": row[1],
            "case_id": row[2],
            "reason": row[3],
            "triggered_by": row[4],
            "status": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "reviewed_by": row[8],
            "reviewed_at": row[9],
            "rejection_reason": row[10],
            "execution_reference": row[11],
            "execution_details": row[12],
            "chain": row[13],
            "complaint_id": row[14],
            "risk_score": row[15],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Pending -> Under Review
# ---------------------------------------------------------------------------
@router.patch("/{request_id}/review")
def move_to_review(request_id: int, payload: FreezeRequestAction):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, status
                FROM freeze_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )

            request = cur.fetchone()

            if not request:
                raise HTTPException(
                    status_code=404,
                    detail="Freeze request not found",
                )

            if request[2] != "Pending":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot move request from {request[2]} to Under Review",
                )

            cur.execute(
                """
                UPDATE freeze_requests
                SET status = 'Under Review', updated_at = now()
                WHERE id = %s
                """,
                (request_id,),
            )

            cur.execute(
                """
                INSERT INTO freeze_request_audit (
                    request_id, case_id, action,
                    previous_status, new_status, actor
                )
                VALUES (%s, %s, 'moved_to_review', 'Pending', 'Under Review', %s)
                """,
                (request_id, request[1], payload.actor),
            )

        conn.commit()

    return {"id": request_id, "status": "Under Review"}


# ---------------------------------------------------------------------------
# Under Review -> Approved
# ---------------------------------------------------------------------------
@router.patch("/{request_id}/approve")
def approve_freeze_request(request_id: int, payload: FreezeRequestAction):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, status
                FROM freeze_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )

            request = cur.fetchone()

            if not request:
                raise HTTPException(
                    status_code=404,
                    detail="Freeze request not found",
                )

            if request[2] != "Under Review":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot approve request from {request[2]}",
                )

            cur.execute(
                """
                UPDATE freeze_requests
                SET status = 'Approved', reviewed_by = %s, reviewed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (payload.actor, request_id),
            )

            cur.execute(
                """
                INSERT INTO freeze_request_audit (
                    request_id, case_id, action,
                    previous_status, new_status, actor
                )
                VALUES (%s, %s, 'approved', 'Under Review', 'Approved', %s)
                """,
                (request_id, request[1], payload.actor),
            )

        conn.commit()

    return {"id": request_id, "status": "Approved"}


# ---------------------------------------------------------------------------
# Under Review -> Rejected
# ---------------------------------------------------------------------------
@router.patch("/{request_id}/reject")
def reject_freeze_request(request_id: int, payload: FreezeRequestReject):
    reason = payload.reason.strip()

    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, status
                FROM freeze_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )

            request = cur.fetchone()

            if not request:
                raise HTTPException(
                    status_code=404,
                    detail="Freeze request not found",
                )

            if request[2] != "Under Review":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot reject request from {request[2]}",
                )

            cur.execute(
                """
                UPDATE freeze_requests
                SET status = 'Rejected', reviewed_by = %s, reviewed_at = now(),
                    rejection_reason = %s, updated_at = now()
                WHERE id = %s
                """,
                (payload.actor, reason, request_id),
            )

            cur.execute(
                """
                INSERT INTO freeze_request_audit (
                    request_id, case_id, action,
                    previous_status, new_status, actor, reason
                )
                VALUES (%s, %s, 'rejected', 'Under Review', 'Rejected', %s, %s)
                """,
                (request_id, request[1], payload.actor, reason),
            )

        conn.commit()

    return {"id": request_id, "status": "Rejected", "rejection_reason": reason}


# ---------------------------------------------------------------------------
# Approved -> Executed
# ---------------------------------------------------------------------------
@router.patch("/{request_id}/execute")
def execute_freeze_request(request_id: int, payload: FreezeRequestExecute):
    execution_reference = payload.execution_reference.strip()

    if not execution_reference:
        raise HTTPException(status_code=400, detail="Execution reference is required")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, status
                FROM freeze_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )

            request = cur.fetchone()

            if not request:
                raise HTTPException(
                    status_code=404,
                    detail="Freeze request not found",
                )

            if request[2] != "Approved":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot execute request from {request[2]}",
                )

            cur.execute(
                """
                UPDATE freeze_requests
                SET status = 'Executed', execution_reference = %s,
                    execution_details = %s, updated_at = now()
                WHERE id = %s
                """,
                (execution_reference, payload.execution_details, request_id),
            )

            cur.execute(
                """
                INSERT INTO freeze_request_audit (
                    request_id, case_id, action,
                    previous_status, new_status, actor, details
                )
                VALUES (%s, %s, 'executed', 'Approved', 'Executed', %s, %s)
                """,
                (
                    request_id,
                    request[1],
                    payload.actor,
                    f"Execution reference: {execution_reference}",
                ),
            )

        conn.commit()

    return {
        "id": request_id,
        "status": "Executed",
        "execution_reference": execution_reference,
    }


# ---------------------------------------------------------------------------
# Audit trail for one request
# ---------------------------------------------------------------------------
@router.get("/{request_id}/audit")
def get_freeze_request_audit(request_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, request_id, case_id, action,
                    previous_status, new_status, actor,
                    reason, details, created_at
                FROM freeze_request_audit
                WHERE request_id = %s
                ORDER BY created_at ASC
                """,
                (request_id,),
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "request_id": row[1],
            "case_id": row[2],
            "action": row[3],
            "previous_status": row[4],
            "new_status": row[5],
            "actor": row[6],
            "reason": row[7],
            "details": row[8],
            "created_at": row[9],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Existing PDF endpoint — untouched
# ---------------------------------------------------------------------------
@router.get("/{request_id}/pdf")
def download_freeze_request_pdf(request_id: int):
    with get_dict_cursor() as cur:
        cur.execute(
            """
            SELECT
                fr.*,
                c.complaint_id,
                c.primary_wallet,
                c.chain,
                c.fraud_type,
                c.risk_score
            FROM freeze_requests fr
            LEFT JOIN cases c ON c.id = fr.case_id
            WHERE fr.id = %s
            """,
            (request_id,),
        )

        request = cur.fetchone()

        if not request:
            raise HTTPException(
                status_code=404,
                detail="Freeze request not found",
            )

        cur.execute(
            """
            SELECT COUNT(*) AS transaction_count
            FROM transactions
            WHERE case_id = %s
            """,
            (request["case_id"],),
        )

        evidence = cur.fetchone()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4
    y = height - 55

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(45, y, "Asset Freeze Request")

    y -= 35
    pdf.setFont("Helvetica", 10)

    fields = [
        ("Request ID", request["id"]),
        ("Case ID", request.get("case_id")),
        ("Complaint ID", request.get("complaint_id")),
        ("Wallet Address", request.get("wallet_address")),
        ("Chain", request.get("chain")),
        ("Fraud Type", request.get("fraud_type")),
        ("Risk Score", request.get("risk_score")),
        ("Evidence Transactions", evidence["transaction_count"]),
        ("Status", request.get("status")),
        ("Triggered By", request.get("triggered_by")),
        ("Created At", request.get("created_at")),
    ]

    for label, value in fields:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(45, y, f"{label}:")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(150, y, str(value or "—")[:100])
        y -= 18

    y -= 10

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(45, y, "Reason")

    y -= 18
    pdf.setFont("Helvetica", 9)

    reason = request.get("reason") or "—"

    for line in reason.splitlines():
        pdf.drawString(45, y, line[:110])
        y -= 14

    y -= 20

    pdf.setFont("Helvetica", 8)
    pdf.drawString(
        45,
        y,
        "Generated from CryptoTrace case and persisted blockchain evidence.",
    )

    pdf.save()

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="freeze-request-{request_id}.pdf"'
        },
    )