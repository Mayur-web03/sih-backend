import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values


load_dotenv()


class TransactionTracer:

    API_URL = "https://api.etherscan.io/v2/api"

    def __init__(
        self,
        start_address,
        max_hops=2,
        offset=100,
        start_block=0,
        end_block=999999999,
        chain_id="1",
        request_delay=0.2
    ):
        self.api_key = os.getenv("EtherAPI")
        self.start_address = start_address.lower()
        self.max_hops = max_hops
        self.offset = offset
        self.start_block = start_block
        self.end_block = end_block
        self.chain_id = chain_id
        self.request_delay = request_delay

        self.supabase_db_url = os.getenv("SUPABASE_DB_URL")

    # ========================================================
    # GET ALL TRANSACTIONS OF ONE ADDRESS
    # ========================================================

    def _get_transactions(self, address):

        params = {
            "chainid": self.chain_id,
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": self.start_block,
            "endblock": self.end_block,
            "page": 1,
            "offset": self.offset,
            "sort": "asc",
            "apikey": self.api_key
        }

        try:
            response = requests.get(self.API_URL, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Request failed for {address}")
            print(e)
            return []
        except ValueError:
            print(f"Invalid JSON response for {address}")
            return []

        if data.get("status") == "1":
            result = data.get("result", [])
            if isinstance(result, list):
                return result
            return []

        if "No transactions" in str(data.get("message", "")):
            return []

        print(f"API error for {address}:")
        print(data)

        return []

    def _get_inward_transactions(self, address):
        transactions = self._get_transactions(address)
        address = address.lower()
        inward = []
        for tx in transactions:
            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()
            if not tx_from or not tx_to:
                continue
            if tx_to == address and tx_from != address:
                inward.append(tx)
        return inward

    def _get_outward_transactions(self, address):
        transactions = self._get_transactions(address)
        address = address.lower()
        outward = []
        for tx in transactions:
            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()
            if not tx_from or not tx_to:
                continue
            if tx_from == address and tx_to != address:
                outward.append(tx)
        return outward

    def _format_transaction(self, tx, hop, source_address, direction):
        return {
            "hop": hop,
            "direction": direction,
            "from": tx.get("from", "").lower(),
            "to": tx.get("to", "").lower(),
            "value": tx.get("value", "0"),
            "tx_hash": tx.get("hash", ""),
            "block_number": tx.get("blockNumber", ""),
            "timestamp": tx.get("timeStamp", ""),
            "gas_used": tx.get("gasUsed", ""),
            "gas_price": tx.get("gasPrice", ""),
            "is_error": tx.get("isError", ""),
            "source_address": source_address
        }

    def _trace(self, direction):
        all_transactions = []
        visited_addresses = set()
        current_addresses = {self.start_address}

        print("\n" + "=" * 60)
        print(f"{direction.upper()} MULTI-HOP TRACING")
        print("=" * 60)

        for hop in range(1, self.max_hops + 1):
            print("\n" + "-" * 60)
            print(f"HOP {hop}")
            print("-" * 60)
            print(f"Addresses to investigate: {len(current_addresses)}")

            next_addresses = set()

            for address in current_addresses:
                address = address.lower()
                if address in visited_addresses:
                    continue

                print("\nChecking address:")
                print(address)

                if direction == "inward":
                    transactions = self._get_inward_transactions(address)
                else:
                    transactions = self._get_outward_transactions(address)

                print(f"Transactions found: {len(transactions)}")

                visited_addresses.add(address)

                for tx in transactions:
                    tx_from = tx.get("from", "").lower()
                    tx_to = tx.get("to", "").lower()

                    transaction = self._format_transaction(
                        tx=tx, hop=hop, source_address=address, direction=direction
                    )
                    all_transactions.append(transaction)

                    next_address = tx_to if direction == "outward" else tx_from

                    if not next_address:
                        continue
                    if next_address == "0x0000000000000000000000000000000000000000":
                        continue
                    if next_address not in visited_addresses:
                        next_addresses.add(next_address)

                time.sleep(self.request_delay)

            current_addresses = next_addresses
            print(f"\nNew addresses discovered: {len(current_addresses)}")

            if not current_addresses:
                print("\nNo new addresses found.")
                break

        return all_transactions

    def trace_inward(self):
        return self._trace("inward")

    def trace_outward(self):
        return self._trace("outward")

    # ========================================================
    # SAVE RESULTS LOCALLY (unchanged, optional debug artifact)
    # ========================================================

    def save_results(self, transactions, direction):
        os.makedirs("data", exist_ok=True)
        df = pd.DataFrame(transactions)
        filename = f"{self.start_address}_{direction}.csv"
        output_path = os.path.join("data", filename)

        if not df.empty:
            df = df.drop_duplicates(subset=["tx_hash"])
            df.to_csv(output_path, index=False)
        else:
            df.to_csv(output_path, index=False)

        print("\n" + "=" * 60)
        print("SAVED")
        print("=" * 60)
        print(f"Direction: {direction}")
        print(f"Transactions: {len(df)}")
        print(f"File: {output_path}")

        return df

    # ========================================================
    # SUPABASE: GET DATABASE CONNECTION
    # ========================================================

    def _get_supabase_connection(self):
        if not self.supabase_db_url:
            raise ValueError("SUPABASE_DB_URL is missing from .env")
        return psycopg2.connect(self.supabase_db_url)

    # ========================================================
    # SUPABASE: UPSERT WALLET
    # ========================================================

    def _upsert_wallet(self, cursor, address, tx_count_delta):
        cursor.execute(
            """
            INSERT INTO wallets (address, chain, tx_count, first_seen, last_seen, last_traced_at, created_at, updated_at)
            VALUES (%s, 'Ethereum', %s, now(), now(), now(), now(), now())
            ON CONFLICT (address) DO UPDATE SET
                tx_count = wallets.tx_count + EXCLUDED.tx_count,
                last_seen = now(),
                last_traced_at = now(),
                updated_at = now()
            """,
            (address, tx_count_delta),
        )

    # ========================================================
    # SUPABASE: SAVE A BATCH OF TRANSACTIONS (fixed schema)
    # ========================================================

    def save_to_supabase(self, df, direction, case_id=None):
        """
        Persists trace results into the FIXED `wallets` + `transactions` tables.
        Matches exact Supabase columns: case_id, tx_hash, from_address, to_address,
        value_wei, hop, direction, block_number, timestamp, is_error.
        """

        if df is None or df.empty:
            print(f"\nNo {direction} data to upload to Supabase.")
            return

        print("\n" + "=" * 60)
        print("SUPABASE UPLOAD")
        print("=" * 60)
        print(f"Wallet: {self.start_address}")
        print(f"Direction: {direction}")
        print(f"Rows: {len(df)}")

        connection = None
        cursor = None

        try:
            connection = self._get_supabase_connection()
            cursor = connection.cursor()

            self._upsert_wallet(cursor, self.start_address, len(df))

            rows = []
            for _, row in df.iterrows():
                def clean(col):
                    v = row.get(col, None)
                    if pd.isna(v):
                        return None
                    return v

                rows.append((
                    case_id,
                    clean("tx_hash"),
                    clean("from"),
                    clean("to"),
                    clean("value"),
                    clean("hop"),
                    direction,
                    clean("block_number"),
                    clean("timestamp"),
                    clean("is_error"),
                ))

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
                ) VALUES %s
                """,
                rows,
            )

            connection.commit()

            print("\nSupabase upload successful.")
            print(f"Rows inserted: {len(rows)}")

        except Exception as e:
            if connection:
                connection.rollback()
            print("\nSupabase error:")
            print(e)
            raise

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    # ========================================================
    # TRACE + SAVE
    # ========================================================

    def run_inward(self, case_id=None):
        transactions = self.trace_inward()
        df = self.save_results(transactions, "inward")
        self.save_to_supabase(df, "inward", case_id=case_id)
        return df

    def run_outward(self, case_id=None):
        transactions = self.trace_outward()
        df = self.save_results(transactions, "outward")
        self.save_to_supabase(df, "outward", case_id=case_id)
        return df

    def run_both(self, case_id=None):
        print("\nStarting INWARD tracing...")
        inward_df = self.run_inward(case_id=case_id)

        print("\nStarting OUTWARD tracing...")
        outward_df = self.run_outward(case_id=case_id)

        return inward_df, outward_df


if __name__ == "__main__":
    ADDRESS = "0x846943093f519A47734765BEF9EE1136800bEb9C"

    tracer = TransactionTracer(start_address=ADDRESS, max_hops=3, offset=100)
    inward_df, outward_df = tracer.run_both()