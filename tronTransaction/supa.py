"""
Supabase persistence helpers for TRON transactions.
"""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


class TronSupabaseSaver:
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url:
            raise ValueError("SUPABASE_URL is not configured")

        if not supabase_key:
            raise ValueError("SUPABASE_KEY is not configured")

        self.supabase: Client = create_client(
            supabase_url,
            supabase_key,
        )

    def save_transactions(
        self,
        transactions: List[Dict[str, Any]],
        case_id: Optional[str] = None,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Save TRON trace transactions into the existing
        `transactions` Supabase table.
        """

        if not transactions:
            return {
                "inserted": 0,
                "message": "No TRON transactions to save",
            }

        rows = []

        for tx in transactions:
            row = {
                "case_id": case_id,
                "tx_hash": tx.get("tx_hash"),
                "from_address": tx.get("from"),
                "to_address": tx.get("to"),
                "value_wei": str(tx.get("amount", "")),
                "hop": tx.get("hop"),
                "direction": "outward",
                "block_number": str(tx.get("block_number", "")),
                "timestamp": str(tx.get("timestamp", "")),
                "is_error": "0",
                "wallet_address": wallet_address
                or tx.get("source_address"),
            }

            rows.append(row)

        response = (
            self.supabase
            .table("transactions")
            .insert(rows)
            .execute()
        )

        return {
            "inserted": len(rows),
            "data": response.data,
        }
