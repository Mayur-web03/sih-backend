from fastapi import APIRouter, HTTPException

from api.schemas import (
    TraceRequest,
    TraceResponse,
    TraceSummary,
    TronTraceRequest,
)
from etherTransaction.supa import TransactionTracer
from tronTransaction.transaction import TronTransactionTracer
from tronTransaction.supa import TronSupabaseSaver

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


@router.post("/trace/tron")
def trace_tron_wallet(payload: TronTraceRequest):
    try:
        tracer = TronTransactionTracer(
            start_address=payload.address,
            max_hops=payload.max_hops,
            asset_type=payload.asset_type,
            max_transactions_per_address=100,  # keeps request under Render timeout
        )

        transactions = tracer.trace()
        graph = tracer.build_graph(transactions)

        # Save to existing Supabase PostgreSQL database.
        # A save failure is reported in the response but does not lose the trace.
        try:
            saver = TronSupabaseSaver()
            save_result = saver.save_to_supabase(
                transactions=transactions,
                wallet_address=payload.address,
                case_id=payload.case_id,
            )
        except Exception as save_err:
            print(f"[WARN] TRON Supabase save failed: {save_err}")
            save_result = {"saved": False, "error": str(save_err)}

        addresses = {payload.address}
        for tx in transactions:
            if tx.get("from"):
                addresses.add(tx["from"])
            if tx.get("to"):
                addresses.add(tx["to"])

        return {
            "source": {
                "address": payload.address,
                "network": "TRON",
            },
            "nodes": graph["nodes"],
            "edges": graph["edges"],
            "summary": {
                "total_transactions": len(transactions),
                "total_addresses": len(addresses),
                "max_hops": payload.max_hops,
            },
            "supabase": save_result,
            "transactions": transactions,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TRON trace failed: {str(e)}")


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
