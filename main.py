import asyncio
import json
import pandas as pd

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from etherTransaction.supa import TransactionTracer
from api.routes import router
from api.cases import router as cases_router
from api.reports import router as reports_router
from api.freeze_requests import router as freeze_requests_router

app = FastAPI(title="CipherWatch API")

# Add CORS Middleware to allow requests from frontend development servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(router)
app.include_router(cases_router)
app.include_router(reports_router)
app.include_router(freeze_requests_router)


def sse(message: str, event_type: str) -> str:
    payload = json.dumps({"type": event_type, "message": message})
    return f"data: {payload}\n\n"


@app.get("/")
def root():
    return {"message": "CipherWatch backend running"}


@app.get("/api/trace/stream")
async def trace_stream(
    address: str = Query(...),
    max_hops: int = Query(5),
    case_id: str | None = Query(None),
):
    async def event_generator():
        try:
            yield sse(f"Validating address {address}...", "log")
            await asyncio.sleep(0.1)

            yield sse("Connecting to Etherscan API...", "log")

            tracer = TransactionTracer(start_address=address, max_hops=max_hops)

            yield sse(f"Starting inward trace (max_hops={max_hops})...", "log")
            inward = await asyncio.to_thread(tracer.trace_inward)
            yield sse(f"Inward trace complete: {len(inward)} transactions found", "progress")

            yield sse("Starting outward trace...", "log")
            outward = await asyncio.to_thread(tracer.trace_outward)
            yield sse(f"Outward trace complete: {len(outward)} transactions found", "progress")

            yield sse("Storing results in Supabase...", "log")

            await asyncio.to_thread(tracer.save_to_supabase, pd.DataFrame(inward), "inward", case_id)
            await asyncio.to_thread(tracer.save_to_supabase, pd.DataFrame(outward), "outward", case_id)

            result = {
                "address": address,
                "summary": {
                    "inward_transactions": len(inward),
                    "outward_transactions": len(outward),
                    "total_transactions": len(inward) + len(outward),
                    "max_hops": max_hops,
                },
                "inward": inward,
                "outward": outward,
            }
            yield sse(json.dumps(result), "done")

        except Exception as e:
            yield sse(str(e), "error")

    return StreamingResponse(event_generator(), media_type="text/event-stream")