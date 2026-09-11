import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv


load_dotenv()


class TransactionTracer:

    API_URL = "https://api.etherscan.io/v2/api"

    def __init__(
        self,
        start_address,
        max_hops=5,
        offset=100,
        start_block=0,
        end_block=999999999,
        chain_id="11155111",
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
            response = requests.get(
                self.API_URL,
                params=params,
                timeout=20
            )

            response.raise_for_status()

            data = response.json()

        except requests.exceptions.RequestException as e:

            print(f"Request failed for {address}")
            print(e)

            return []

        except ValueError:

            print(f"Invalid JSON response for {address}")

            return []

        # ----------------------------------------------------
        # Etherscan response handling
        # ----------------------------------------------------

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

    # ========================================================
    # FILTER INWARD TRANSACTIONS
    # ========================================================

    def _get_inward_transactions(self, address):

        transactions = self._get_transactions(address)

        address = address.lower()

        inward = []

        for tx in transactions:

            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()

            if not tx_from or not tx_to:
                continue

            # Another address -> current address
            if tx_to == address and tx_from != address:

                inward.append(tx)

        return inward

    # ========================================================
    # FILTER OUTWARD TRANSACTIONS
    # ========================================================

    def _get_outward_transactions(self, address):

        transactions = self._get_transactions(address)

        address = address.lower()

        outward = []

        for tx in transactions:

            tx_from = tx.get("from", "").lower()
            tx_to = tx.get("to", "").lower()

            if not tx_from or not tx_to:
                continue

            # Current address -> another address
            if tx_from == address and tx_to != address:

                outward.append(tx)

        return outward

    # ========================================================
    # CREATE STANDARD TRANSACTION RECORD
    # ========================================================

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

    # ========================================================
    # GENERIC MULTI-HOP TRACING
    # ========================================================

    def _trace(self, direction):

        all_transactions = []

        visited_addresses = set()

        current_addresses = {
            self.start_address
        }

        print("\n" + "=" * 60)
        print(f"{direction.upper()} MULTI-HOP TRACING")
        print("=" * 60)

        # ----------------------------------------------------
        # HOP LOOP
        # ----------------------------------------------------

        for hop in range(1, self.max_hops + 1):

            print("\n" + "-" * 60)
            print(f"HOP {hop}")
            print("-" * 60)

            print(
                f"Addresses to investigate: "
                f"{len(current_addresses)}"
            )

            next_addresses = set()

            # ------------------------------------------------
            # Investigate addresses at current hop
            # ------------------------------------------------

            for address in current_addresses:

                address = address.lower()

                if address in visited_addresses:
                    continue

                print(f"\nChecking address:")
                print(address)

                # --------------------------------------------
                # Get correct direction
                # --------------------------------------------

                if direction == "inward":

                    transactions = (
                        self._get_inward_transactions(address)
                    )

                else:

                    transactions = (
                        self._get_outward_transactions(address)
                    )

                print(
                    f"Transactions found: "
                    f"{len(transactions)}"
                )

                # Mark address as visited
                visited_addresses.add(address)

                # --------------------------------------------
                # Process transactions
                # --------------------------------------------

                for tx in transactions:

                    tx_from = tx.get(
                        "from",
                        ""
                    ).lower()

                    tx_to = tx.get(
                        "to",
                        ""
                    ).lower()

                    # ----------------------------------------
                    # Save transaction
                    # ----------------------------------------

                    transaction = self._format_transaction(
                        tx=tx,
                        hop=hop,
                        source_address=address,
                        direction=direction
                    )

                    all_transactions.append(
                        transaction
                    )

                    # ----------------------------------------
                    # Find next address
                    # ----------------------------------------

                    if direction == "outward":

                        next_address = tx_to

                    else:

                        next_address = tx_from

                    # ----------------------------------------
                    # Ignore invalid / zero address
                    # ----------------------------------------

                    if not next_address:
                        continue

                    if next_address == (
                        "0x0000000000000000000000000000000000000000"
                    ):
                        continue

                    # ----------------------------------------
                    # Don't revisit an address
                    # ----------------------------------------

                    if next_address not in visited_addresses:

                        next_addresses.add(
                            next_address
                        )

                time.sleep(
                    self.request_delay
                )

            # ------------------------------------------------
            # Move to next hop
            # ------------------------------------------------

            current_addresses = next_addresses

            print(
                f"\nNew addresses discovered: "
                f"{len(current_addresses)}"
            )

            if not current_addresses:

                print(
                    "\nNo new addresses found."
                )

                break

        return all_transactions

    # ========================================================
    # PUBLIC FUNCTION: INWARD
    # ========================================================

    def trace_inward(self):

        return self._trace("inward")

    # ========================================================
    # PUBLIC FUNCTION: OUTWARD
    # ========================================================

    def trace_outward(self):

        return self._trace("outward")

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    def save_results(self, transactions, direction):

        os.makedirs(
            "data",
            exist_ok=True
        )

        df = pd.DataFrame(transactions)

        filename = (
            f"{self.start_address}_"
            f"{direction}.csv"
        )

        output_path = os.path.join(
            "data",
            filename
        )

        if not df.empty:

            df = df.drop_duplicates(
                subset=["tx_hash"]
            )

            df.to_csv(
                output_path,
                index=False
            )

        else:

            # Still create an empty CSV
            df.to_csv(
                output_path,
                index=False
            )

        print("\n" + "=" * 60)
        print("SAVED")
        print("=" * 60)

        print(f"Direction: {direction}")
        print(f"Transactions: {len(df)}")
        print(f"File: {output_path}")

        return df

    # ========================================================
    # TRACE + SAVE INWARD
    # ========================================================

    def run_inward(self):

        transactions = self.trace_inward()

        return self.save_results(
            transactions,
            "inward"
        )

    # ========================================================
    # TRACE + SAVE OUTWARD
    # ========================================================

    def run_outward(self):

        transactions = self.trace_outward()

        return self.save_results(
            transactions,
            "outward"
        )

    # ========================================================
    # TRACE + SAVE BOTH
    # ========================================================

    def run_both(self):

        print("\nStarting INWARD tracing...")

        inward_df = self.run_inward()

        print("\nStarting OUTWARD tracing...")

        outward_df = self.run_outward()

        return inward_df, outward_df