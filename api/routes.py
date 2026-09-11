from fastapi import APIRouter, HTTPException
from api.schemas import TraceRequest, TraceResponse, TraceSummary
from etherTransaction.supa import TransactionTracer

router = APIRouter(prefix="/api")

DEFAULT_MAX_HOPS = 5


@router.get("/config")
def get_config():
    return {"max_hops": DEFAULT_MAX_HOPS}


@router.post("/trace", response_model=TraceResponse)
def trace_wallet(payload: TraceRequest):
    try:
        tracer = TransactionTracer(
            start_address=payload.address,
            max_hops=payload.max_hops,
        )
        inward_df, outward_df = tracer.run_both(case_id=payload.case_id)

        inward_records = inward_df.to_dict(orient="records") if not inward_df.empty else []
        outward_records = outward_df.to_dict(orient="records") if not outward_df.empty else []

        summary = TraceSummary(
            inward_transactions=len(inward_records),
            outward_transactions=len(outward_records),
            total_transactions=len(inward_records) + len(outward_records),
            max_hops=payload.max_hops,
        )

        return TraceResponse(
            address=payload.address,
            summary=summary,
            inward=inward_records,
            outward=outward_records,
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trace failed: {str(e)}")

@router.get("/cases/{case_id}/transactions")
def get_case_transactions(case_id: str):
    from db import get_dict_cursor

    with get_dict_cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM transactions
            WHERE case_id = %s
            ORDER BY timestamp ASC
            """,
            (case_id,),
        )
        return cur.fetchall()
    
@router.get("/health")
def health_check():
    return {"status": "ok"}