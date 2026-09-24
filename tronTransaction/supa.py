"""
Supabase persistence for TRON transactions.

Uses the existing PostgreSQL connection:
SUPABASE_DB_URL
"""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


load_dotenv()


class TronSupabaseSaver:

    def __init__(self):
        self.supabase_db_url = os.getenv("SUPABASE_DB_URL")

        if not self.supabase_db_url:
            raise ValueError(
                "SUPABASE_DB_URL is missing from environment"
            )

    def _get_connection(self):
        return psycopg2.connect(self.supabase_db_url)

    def _upsert_wallet(
        self,
        cursor,
        address,
        tx_count_delta,
    ):
        """
        Reuse the existing wallets table.

        TRON is stored as chain='TRON'.
        """

        cursor.execute(
            """
            INSERT INTO wallets (
                address,
                chain,
                tx_count,
                first_seen,
                last_seen,
                last_traced_at,
                created_at,
                updated_at
            )
            VALUES (
                %s,
                'TRON',
                %s,
                now(),
                now(),
                now(),
                now(),
                now()
            )
            ON CONFLICT (address) DO UPDATE SET
                tx_count = wallets.tx_count + EXCLUDED.tx_count,
                last_seen = now(),
                last_traced_at = now(),
                updated_at = now()
            """,
            (
                address,
                tx_count_delta,
            ),
        )

    def save_to_supabase(
        self,
        transactions,
        wallet_address,
        case_id=None,
    ):
        """
        Save TRON transactions into the existing
        transactions table.
        """

        if not transactions:
            return {
                "saved": True,
                "inserted": 0,
                "message": "No transactions to save",
            }

        connection = None
        cursor = None

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            # --------------------------------------------------
            # UPDATE / UPSERT SOURCE WALLET
            # --------------------------------------------------

            self._upsert_wallet(
                cursor,
                wallet_address,
                len(transactions),
            )

            # --------------------------------------------------
            # PREPARE TRANSACTION ROWS
            # --------------------------------------------------

            rows = []

            for tx in transactions:

                amount = tx.get("amount")

                if amount is None:
                    amount = "0"

                block_number = tx.get("block_number")

                if block_number is None:
                    block_number = ""

                timestamp = tx.get("timestamp")

                if timestamp is None:
                    timestamp = ""

                rows.append(
                    (
                        case_id,
                        tx.get("tx_hash"),
                        tx.get("from"),
                        tx.get("to"),
                        str(amount),
                        tx.get("hop"),
                        "outward",
                        str(block_number),
                        str(timestamp),
                        "0",
                    )
                )

            # --------------------------------------------------
            # INSERT INTO EXISTING TRANSACTIONS TABLE
            # --------------------------------------------------

            execute_values(
                cursor,
                """
                INSERT INTO transactions (
                    case_id,
                    tx_hash,
                    from_address,
                    to_address,
                    value_wei,
                    hop,
                    direction,
                    block_number,
                    timestamp,
                    is_error
                )
                VALUES %s
                """,
                rows,
            )

            connection.commit()

            return {
                "saved": True,
                "inserted": len(rows),
            }

        except Exception as e:

            if connection:
                connection.rollback()

            return {
                "saved": False,
                "inserted": 0,
                "error": str(e),
            }

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()
