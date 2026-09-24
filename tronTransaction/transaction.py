import os
import time
from decimal import Decimal, InvalidOperation

import base58
import requests
from dotenv import load_dotenv


load_dotenv()


class TronTransactionTracer:
    """
    TRON multi-hop outward transaction tracer.

    Supports:
        - Native TRX transfers
        - TRC-20 token transfers
        - Multiple hops
        - Confirmed transactions
        - TRON Base58 address normalization
        - Pagination through TronGrid fingerprint
        - Duplicate transaction protection
    """

    TRON_BASE_URL = "https://api.trongrid.io"

    def __init__(
        self,
        start_address: str,
        max_hops: int = 5,
        asset_type: str = "all",
        api_page_size: int = 20,
        max_transactions_per_address: int = 200,
        request_delay: float = 0.2,
    ):
        self.api_key = os.getenv("TRON_API_KEY", "")

        self.start_address = self.normalize_tron_address(start_address)

        self.max_hops = max_hops

        asset_type = asset_type.lower().strip()

        if asset_type not in {"trx", "trc20", "all"}:
            raise ValueError(
                "asset_type must be one of: trx, trc20, all"
            )

        self.asset_type = asset_type

        self.api_page_size = min(
            max(int(api_page_size), 1),
            200,
        )

        self.max_transactions_per_address = max(
            int(max_transactions_per_address),
            1,
        )

        self.request_delay = max(
            float(request_delay),
            0,
        )

    # ============================================================
    # ADDRESS HELPERS
    # ============================================================

    @staticmethod
    def tron_hex_to_base58(address_hex: str) -> str:
        """
        Convert TRON hex address:

            41xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

        into Base58Check:

            Txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        """

        if not address_hex:
            return ""

        address_hex = str(address_hex).strip()

        # Already Base58 TRON address
        if address_hex.startswith("T"):
            return address_hex

        try:
            raw = bytes.fromhex(address_hex)
            return base58.b58encode_check(raw).decode()

        except Exception:
            return address_hex

    @classmethod
    def normalize_tron_address(cls, address: str) -> str:
        """
        Return a normalized TRON Base58 address.
        """

        if not address:
            return ""

        address = str(address).strip()

        if address.startswith("T"):
            return address

        return cls.tron_hex_to_base58(address)

    # ============================================================
    # DECIMAL HELPER
    # ============================================================

    @staticmethod
    def safe_decimal(value, default="0") -> Decimal:
        try:
            return Decimal(str(value))

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            return Decimal(default)

    # ============================================================
    # API HEADERS
    # ============================================================

    def _get_tron_headers(self):
        if self.api_key:
            return {
                "TRON-PRO-API-KEY": self.api_key
            }

        return {}

    # ============================================================
    # GENERIC TRONGRID REQUEST
    # ============================================================

    def _tron_get(self, url, params):
        headers = self._get_tron_headers()

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=30,
            )

            response.raise_for_status()

            return response.json()

        except requests.RequestException as exc:
            print(
                f"TRON API request failed: {exc}"
            )
            return None

        except ValueError:
            print(
                "TRON API returned invalid JSON"
            )
            return None

    # ============================================================
    # FETCH TRX OUTWARD TRANSACTIONS
    # ============================================================

    def get_trx_outward_transactions(self, address):
        """
        Fetch confirmed native TRX transactions:

            address -> another address
        """

        address = self.normalize_tron_address(address)

        if not address:
            return []

        url = (
            f"{self.TRON_BASE_URL}"
            f"/v1/accounts/{address}/transactions"
        )

        fingerprint = None
        transactions = []

        page = 1

        while (
            len(transactions)
            < self.max_transactions_per_address
        ):
            params = {
                "only_confirmed": "true",
                "limit": self.api_page_size,
                "order_by": "block_timestamp,asc",
                "only_from": "true",
            }

            if fingerprint:
                params["fingerprint"] = fingerprint

            print(
                f"    TRX page {page} "
                f"for {address}"
            )

            data = self._tron_get(
                url,
                params,
            )

            if not data:
                break

            txs = data.get(
                "data",
                [],
            )

            if not txs:
                break

            stop_fetching = False

            for tx in txs:

                tx_hash = tx.get(
                    "txID",
                    "",
                )

                raw_data = tx.get(
                    "raw_data",
                    {},
                )

                contracts = raw_data.get(
                    "contract",
                    [],
                )

                if not contracts:
                    continue

                for contract in contracts:

                    contract_type = contract.get(
                        "type",
                        "",
                    )

                    if contract_type != "TransferContract":
                        continue

                    parameter = contract.get(
                        "parameter",
                        {},
                    )

                    value = parameter.get(
                        "value",
                        {},
                    )

                    owner_hex = value.get(
                        "owner_address",
                        "",
                    )

                    to_hex = value.get(
                        "to_address",
                        "",
                    )

                    from_address = (
                        self.normalize_tron_address(
                            owner_hex
                        )
                    )

                    to_address = (
                        self.normalize_tron_address(
                            to_hex
                        )
                    )

                    if (
                        from_address.lower()
                        != address.lower()
                    ):
                        continue

                    if not to_address:
                        continue

                    amount_sun = self.safe_decimal(
                        value.get(
                            "amount",
                            0,
                        )
                    )

                    amount_trx = (
                        amount_sun
                        / Decimal("1000000")
                    )

                    transactions.append(
                        {
                            "network": "TRON",
                            "transaction_type": "TRX",
                            "tx_hash": tx_hash,
                            "from": from_address,
                            "to": to_address,
                            "amount": str(amount_trx),
                            "asset": "TRX",
                            "block_number": tx.get(
                                "blockNumber",
                                "",
                            ),
                            "timestamp": raw_data.get(
                                "timestamp",
                                "",
                            ),
                            "contract_type": contract_type,
                            "contract_address": "",
                        }
                    )

                    if (
                        len(transactions)
                        >= self.max_transactions_per_address
                    ):
                        stop_fetching = True
                        break

                if stop_fetching:
                    break

            if (
                len(transactions)
                >= self.max_transactions_per_address
            ):
                break

            fingerprint = (
                data
                .get("meta", {})
                .get("fingerprint")
            )

            if not fingerprint:
                break

            page += 1

            if self.request_delay:
                time.sleep(
                    self.request_delay
                )

        return transactions

    # ============================================================
    # FETCH TRC-20 OUTWARD TRANSACTIONS
    # ============================================================

    def get_trc20_outward_transactions(self, address):
        """
        Fetch confirmed TRC-20 token transfers:

            address -> another address
        """

        address = self.normalize_tron_address(address)

        if not address:
            return []

        url = (
            f"{self.TRON_BASE_URL}"
            f"/v1/accounts/{address}/transactions/trc20"
        )

        fingerprint = None
        transactions = []

        page = 1

        while (
            len(transactions)
            < self.max_transactions_per_address
        ):
            params = {
                "only_confirmed": "true",
                "limit": self.api_page_size,
                "order_by": "block_timestamp,asc",
                "only_from": "true",
            }

            if fingerprint:
                params["fingerprint"] = fingerprint

            print(
                f"    TRC20 page {page} "
                f"for {address}"
            )

            data = self._tron_get(
                url,
                params,
            )

            if not data:
                break

            txs = data.get(
                "data",
                [],
            )

            if not txs:
                break

            stop_fetching = False

            for tx in txs:

                from_address = (
                    self.normalize_tron_address(
                        tx.get(
                            "from",
                            "",
                        )
                    )
                )

                to_address = (
                    self.normalize_tron_address(
                        tx.get(
                            "to",
                            "",
                        )
                    )
                )

                if (
                    from_address.lower()
                    != address.lower()
                ):
                    continue

                if not to_address:
                    continue

                token_info = tx.get(
                    "token_info",
                    {},
                )

                try:
                    decimals = int(
                        token_info.get(
                            "decimals",
                            6,
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                ):
                    decimals = 6

                raw_value = self.safe_decimal(
                    tx.get(
                        "value",
                        0,
                    )
                )

                divisor = (
                    Decimal(10)
                    ** decimals
                )

                token_amount = (
                    raw_value / divisor
                )

                transactions.append(
                    {
                        "network": "TRON",
                        "transaction_type": "TRC20",
                        "tx_hash": tx.get(
                            "transaction_id",
                            "",
                        ),
                        "from": from_address,
                        "to": to_address,
                        "amount": str(
                            token_amount
                        ),
                        "asset": token_info.get(
                            "symbol",
                            "TRC20",
                        ),
                        "block_number": tx.get(
                            "block",
                            "",
                        ),
                        "timestamp": tx.get(
                            "block_timestamp",
                            "",
                        ),
                        "contract_type":
                            "TriggerSmartContract",
                        "contract_address":
                            token_info.get(
                                "address",
                                "",
                            ),
                        "decimals": decimals,
                    }
                )

                if (
                    len(transactions)
                    >= self.max_transactions_per_address
                ):
                    stop_fetching = True
                    break

            if (
                len(transactions)
                >= self.max_transactions_per_address
            ):
                break

            fingerprint = (
                data
                .get("meta", {})
                .get("fingerprint")
            )

            if not fingerprint:
                break

            page += 1

            if self.request_delay:
                time.sleep(
                    self.request_delay
                )

        return transactions

    # ============================================================
    # TRACE ONE ADDRESS
    # ============================================================

    def _get_address_transactions(self, address):
        """
        Fetch the requested asset types for one address.
        """

        transactions = []

        if self.asset_type in {
            "trx",
            "all",
        }:
            transactions.extend(
                self.get_trx_outward_transactions(
                    address
                )
            )

        if self.asset_type in {
            "trc20",
            "all",
        }:
            transactions.extend(
                self.get_trc20_outward_transactions(
                    address
                )
            )

        return transactions

    # ============================================================
    # MULTI-HOP TRACING
    # ============================================================

    def trace(self):
        """
        Trace outward from the starting wallet.

        Example:

            Hop 1:
                A -> B
                A -> C

            Hop 2:
                B -> D
                C -> E
        """

        start_address = (
            self.normalize_tron_address(
                self.start_address
            )
        )

        current_addresses = {
            start_address
        }

        visited_addresses = set()

        seen_transactions = set()

        all_transactions = []

        for hop in range(
            1,
            self.max_hops + 1,
        ):
            print("\n")
            print("=" * 60)
            print(
                f"TRON HOP {hop}"
            )
            print("=" * 60)

            print(
                "Addresses to investigate:",
                len(current_addresses),
            )

            next_addresses = set()

            for address in sorted(
                current_addresses
            ):

                if address in visited_addresses:
                    continue

                visited_addresses.add(
                    address
                )

                print(
                    f"\nChecking TRON address: "
                    f"{address}"
                )

                address_transactions = (
                    self._get_address_transactions(
                        address
                    )
                )

                print(
                    "Transactions found:",
                    len(address_transactions),
                )

                for tx in address_transactions:

                    tx_hash = tx.get(
                        "tx_hash",
                        "",
                    )

                    from_address = (
                        self.normalize_tron_address(
                            tx.get(
                                "from",
                                "",
                            )
                        )
                    )

                    to_address = (
                        self.normalize_tron_address(
                            tx.get(
                                "to",
                                "",
                            )
                        )
                    )

                    asset = tx.get(
                        "asset",
                        "",
                    )

                    amount = tx.get(
                        "amount",
                        "0",
                    )

                    transaction_key = (
                        tx_hash,
                        from_address.lower(),
                        to_address.lower(),
                        asset,
                        str(amount),
                    )

                    if transaction_key in seen_transactions:
                        continue

                    seen_transactions.add(
                        transaction_key
                    )

                    result = {
                        "hop": hop,
                        "source_address": address,
                        "network": "TRON",
                        "transaction_type":
                            tx.get(
                                "transaction_type",
                                "",
                            ),
                        "tx_hash": tx_hash,
                        "from": from_address,
                        "to": to_address,
                        "amount": amount,
                        "asset": asset,
                        "block_number":
                            tx.get(
                                "block_number",
                                "",
                            ),
                        "timestamp":
                            tx.get(
                                "timestamp",
                                "",
                            ),
                        "contract_type":
                            tx.get(
                                "contract_type",
                                "",
                            ),
                        "contract_address":
                            tx.get(
                                "contract_address",
                                "",
                            ),
                        "decimals":
                            tx.get(
                                "decimals",
                                None,
                            ),
                    }

                    all_transactions.append(
                        result
                    )

                    if (
                        to_address
                        and to_address
                        not in visited_addresses
                    ):
                        next_addresses.add(
                            to_address
                        )

                if self.request_delay:
                    time.sleep(
                        self.request_delay
                    )

            current_addresses = (
                next_addresses
            )

            print(
                f"New addresses discovered: "
                f"{len(current_addresses)}"
            )

            if not current_addresses:
                break

        return all_transactions
