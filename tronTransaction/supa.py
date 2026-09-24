import os
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

    def save_to_supabase(
        self,
        transactions,
        wallet_address,
        case_id=None,
    ):
        if not transactions:
            return {
                "saved": True,
                "inserted": 0,
                "message": "No transactions to save",
            }

        connection = None
        cursor = None

        try:
            # SAME connection method as existing Ethereum code
            connection = psycopg2.connect(
                self.supabase_db_url
            )

            cursor = connection.cursor()

            # ------------------------------------------
            # WALLET
            # ------------------------------------------

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
                    wallet_address,
                    len(transactions),
                ),
            )

            # ------------------------------------------
            # TRANSACTIONS
            # ------------------------------------------

            rows = []

            for tx in transactions:

                rows.append(
                    (
                        case_id,
                        tx.get("tx_hash"),
                        tx.get("from"),
                        tx.get("to"),
                        str(tx.get("amount", "0")),
                        tx.get("hop"),
                        "outward",
                        str(tx.get("block_number", "")),
                        str(tx.get("timestamp", "")),
                        "0",
                    )
                )

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
                "error": str(e),
            }

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()
