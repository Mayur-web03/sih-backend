import random
import string
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from api.schemas import CaseCreate, CaseUpdate, CaseOut
from db import get_dict_cursor, get_connection
from etherTransaction.supa import TransactionTracer

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _generate_case_id() -> str:
    year = datetime.now(timezone.utc).year
    suffix = "".join(random.choices(string.digits, k=4))
    return f"NCRP-{year}-{suffix}"


def _log_timeline(cursor, case_id: str, event_type: str, label: str, wallet_address: str = None):
    cursor.execute(
        """
        INSERT INTO timeline (case_id, wallet_address, event_type, label)
        VALUES (%s, %s, %s, %s)
        """,
        (case_id, wallet_address, event_type, label),
    )


@router.get("", response_model=List[CaseOut])
def list_cases(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    assigned_investigator: Optional[str] = Query(None),
):
    query = "SELECT * FROM cases WHERE 1=1"
    params = []

    if status:
        query += " AND status = %s"
        params.append(status)
    if priority:
        query += " AND priority = %s"
        params.append(priority)
    if assigned_investigator:
        query += " AND assigned_investigator = %s"
        params.append(assigned_investigator)
    if search:
        query += " AND (id ILIKE %s OR complaint_id ILIKE %s OR primary_wallet ILIKE %s OR fraud_type ILIKE %s)"
        like = f"%{search}%"
        params.extend([like, like, like, like])

    query += " ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST"

    with get_dict_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return rows


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str):
    with get_dict_cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return row


@router.post("", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate):
    case_id = payload.id or _generate_case_id()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cases WHERE id = %s", (case_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Case {case_id} already exists")

            cur.execute(
                """
                INSERT INTO cases (
                    id, complaint_id, victim_name, primary_wallet, amount_inr,
                    chain, fraud_type, status, priority, assigned_investigator,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                """,
                (
                    case_id, payload.complaint_id, payload.victim_name, payload.primary_wallet,
                    payload.amount_inr, payload.chain, payload.fraud_type, payload.status,
                    payload.priority, payload.assigned_investigator,
                ),
            )

            # _log_timeline(cur, case_id, "case_created", f"Case {case_id} created", payload.primary_wallet)

        with conn.cursor(cursor_factory=None) as cur2:
            cur2.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
            cols = [d[0] for d in cur2.description]
            row = dict(zip(cols, cur2.fetchone()))

    if payload.auto_trace:
        try:
            tracer = TransactionTracer(
                start_address=payload.primary_wallet,
                max_hops=payload.max_hops,
            )
            tracer.run_both(case_id=case_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Case created but trace failed: {str(e)}",
            )

    return row


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(case_id: str, payload: CaseUpdate):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = ", ".join(f"{k} = %s" for k in fields.keys())
    values = list(fields.values()) + [case_id]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cases WHERE id = %s", (case_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

            cur.execute(
                f"UPDATE cases SET {set_clauses}, updated_at = now() WHERE id = %s",
                values,
            )

            if "status" in fields:
                _log_timeline(cur, case_id, "status_changed", f"Status changed to {fields['status']}")
            if "priority" in fields:
                _log_timeline(cur, case_id, "status_changed", f"Priority changed to {fields['priority']}")
            if "assigned_investigator" in fields:
                _log_timeline(cur, case_id, "status_changed", f"Assigned to {fields['assigned_investigator']}")

        with conn.cursor(cursor_factory=None) as cur2:
            cur2.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
            cols = [d[0] for d in cur2.description]
            row = dict(zip(cols, cur2.fetchone()))

    return row


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cases WHERE id = %s", (case_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
            cur.execute("DELETE FROM cases WHERE id = %s", (case_id,))
    return None