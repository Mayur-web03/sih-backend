import os
import time
from decimal import Decimal, InvalidOperation

import base58
import requests
from dotenv import load_dotenv

load_dotenv()


class TronTransactionTracer:
    """
    TRON multi-hop OUTWARD transaction tracer (TronGrid).

    Supports: native TRX, TRC-20, confirmed txs only, Base58 address
    normalization, fingerprint pagination, duplicate protection.
    """

    TRON_BASE_URL = "https://api.trongrid.io"
    SUN_PER_TRX = Decimal("1000000")

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
        self.max_hops = max(int(max_hops), 1)

        asset_type = asset_type.lower().strip()
        if asset_type not in {"trx", "trc20", "all"}:
            raise ValueError("asset_type must be one of: trx, trc20, all")
        self.asset_type = asset_type

        self.api_page_size = min(max(int(api_page_size), 1), 200)
        self.max_transactions_per_address = max(int(max_transactions_per_address), 1)
        self.request_delay = max(float(request_delay), 0)

    # ---------------- address helpers ----------------

    @staticmethod
    def tron_hex_to_base58(address_hex: str) -> str:
        """41xxxx... (hex) -> Txxxx... (Base58Check)."""
        if not address_hex:
            return ""
        address_hex = str(address_hex).strip()
        if address_hex.startswith("T"):
            return address_hex
        try:
            return base58.b58encode_check(bytes.fromhex(address_hex)).decode()
        except Exception:
            return address_hex

    @classmethod
    def normalize_tron_address(cls, address: str) -> str:
        if not address:
            return ""
        address = str(address).strip()
        if address.startswith("T"):
            return address
        return cls.tron_hex_to_base58(address)

    @staticmethod
    def safe_decimal(value, default="0") -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal(default)

    # ---------------- HTTP ----------------

    def _headers(self):
        return {"TRON-PRO-API-KEY": self.api_key} if self.api_key else {}

    def _tron_get(self, url, params, retries: int = 3):
        for attempt in range(retries):
            try:
                resp = requests.get(
                    url, headers=self._headers(), params=params, timeout=30
                )
                if resp.status_code == 429:  # rate limited
                    print(f"    TRON 429 rate limited, retry {attempt + 1}/{retries}")
                    time.sleep(1.0 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    print(f"    TRON HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                print(f"TRON API request failed: {exc}")
                return None
            except ValueError:
                print("TRON API returned invalid JSON")
                return None
        return None

    # ---------------- generic pagination ----------------

    def _fetch_pages(self, url, address, label, parse):
        results = []
        fingerprint = None
        page = 1

        while len(results) < self.max_transactions_per_address:
            params = {
                "only_confirmed": "true",
                "limit": self.api_page_size,
                "order_by": "block_timestamp,asc",
                "only_from": "true",
            }
            if fingerprint:
                params["fingerprint"] = fingerprint

            print(f"    {label} page {page} for {address}")
            data = self._tron_get(url, params)
            if not data:
                break

            txs = data.get("data") or []
            if not txs:
                break

            for tx in txs:
                for row in parse(tx, address):
                    results.append(row)
                    if len(results) >= self.max_transactions_per_address:
                        return results

            fingerprint = (data.get("meta") or {}).get("fingerprint")
            if not fingerprint:
                break

            page += 1
            if self.request_delay:
                time.sleep(self.request_delay)

        return results

    # ---------------- TRX ----------------

    def _parse_trx(self, tx, address):
        rows = []
        raw_data = tx.get("raw_data") or {}
        for contract in raw_data.get("contract") or []:
            contract_type = contract.get("type", "")
            if contract_type != "TransferContract":
                continue

            value = (contract.get("parameter") or {}).get("value") or {}
            from_addr = self.normalize_tron_address(value.get("owner_address", ""))
            to_addr = self.normalize_tron_address(value.get("to_address", ""))

            if from_addr != address or not to_addr:
                continue

            amount_trx = self.safe_decimal(value.get("amount", 0)) / self.SUN_PER_TRX
            rows.append(
                {
                    "network": "TRON",
                    "transaction_type": "TRX",
                    "tx_hash": tx.get("txID", ""),
                    "from": from_addr,
                    "to": to_addr,
                    "amount": str(amount_trx),
                    "asset": "TRX",
                    "block_number": tx.get("blockNumber", ""),
                    "timestamp": raw_data.get("timestamp", ""),
                    "contract_type": contract_type,
                    "contract_address": "",
                    "decimals": 6,
                }
            )
        return rows

    def get_trx_outward_transactions(self, address):
        address = self.normalize_tron_address(address)
        if not address:
            return []
        url = f"{self.TRON_BASE_URL}/v1/accounts/{address}/transactions"
        return self._fetch_pages(url, address, "TRX", self._parse_trx)

    # ---------------- TRC-20 ----------------

    def _parse_trc20(self, tx, address):
        from_addr = self.normalize_tron_address(tx.get("from", ""))
        to_addr = self.normalize_tron_address(tx.get("to", ""))
        if from_addr != address or not to_addr:
            return []

        token = tx.get("token_info") or {}
        try:
            decimals = int(token.get("decimals", 6))
        except (ValueError, TypeError):
            decimals = 6

        amount = self.safe_decimal(tx.get("value", 0)) / (Decimal(10) ** decimals)

        return [
            {
                "network": "TRON",
                "transaction_type": "TRC20",
                "tx_hash": tx.get("transaction_id", ""),
                "from": from_addr,
                "to": to_addr,
                "amount": str(amount),
                "asset": token.get("symbol", "TRC20"),
                "block_number": tx.get("block", ""),
                "timestamp": tx.get("block_timestamp", ""),
                "contract_type": "TriggerSmartContract",
                "contract_address": token.get("address", ""),
                "decimals": decimals,
            }
        ]

    def get_trc20_outward_transactions(self, address):
        address = self.normalize_tron_address(address)
        if not address:
            return []
        url = f"{self.TRON_BASE_URL}/v1/accounts/{address}/transactions/trc20"
        return self._fetch_pages(url, address, "TRC20", self._parse_trc20)

    # ---------------- one address ----------------

    def _get_address_transactions(self, address):
        txs = []

        print(f"    FETCHING OUTWARD TXS FOR: {address}")
        print(f"    ASSET TYPE: {self.asset_type}")

        if self.asset_type in {"trx", "all"}:
            trx_txs = self.get_trx_outward_transactions(address)
            print(f"    TRX RESULT COUNT: {len(trx_txs)}")
            txs.extend(trx_txs)

        if self.asset_type in {"trc20", "all"}:
            trc20_txs = self.get_trc20_outward_transactions(address)
            print(f"    TRC20 RESULT COUNT: {len(trc20_txs)}")
            txs.extend(trc20_txs)

        print(f"    TOTAL OUTWARD TXS: {len(txs)}")
        return txs

    # ---------------- multi-hop ----------------

    def trace(self):
        """
        Hop 1: source -> B, C
        Hop 2: B -> D, C -> E ... (destination wallets become next hop)
        """
        current_addresses = {self.start_address}
        visited = set()
        seen = set()
        results = []

        for hop in range(1, self.max_hops + 1):
            print(f"\n=== TRON HOP {hop} | addresses: {len(current_addresses)} ===")
            next_addresses = set()

            for address in sorted(current_addresses):
                if address in visited:
                    continue
                visited.add(address)

                for tx in self._get_address_transactions(address):
                    key = (
                        tx["tx_hash"],
                        tx["from"],
                        tx["to"],
                        tx["asset"],
                        str(tx["amount"]),
                    )
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append({**tx, "hop": hop, "source_address": address})

                    if tx["to"] and tx["to"] not in visited:
                        next_addresses.add(tx["to"])

                if self.request_delay:
                    time.sleep(self.request_delay)

            print(f"    NEXT HOP ADDRESSES ({len(next_addresses)}): {sorted(next_addresses)}")

            current_addresses = next_addresses

            if not current_addresses:
                print(f"    NO NEXT ADDRESSES AFTER HOP {hop}")
                break

        print(f"\nTRACE DONE. TOTAL TXS: {len(results)}")
        return results

    # ---------------- graph format for frontend ----------------

    def build_graph(self, transactions):
        """Convert flat tx list -> {nodes, edges} for the graph UI."""
        nodes = {
            self.start_address: {
                "id": self.start_address,
                "address": self.start_address,
                "network": "TRON",
                "hop": 0,
                "is_source": True,
                "is_flagged": False,
            }
        }
        edges = []

        for i, tx in enumerate(transactions):
            for addr in (tx["from"], tx["to"]):
                if addr not in nodes:
                    nodes[addr] = {
                        "id": addr,
                        "address": addr,
                        "network": "TRON",
                        "hop": tx["hop"],
                        "is_source": False,
                        "is_flagged": False,
                    }
            # destination hop = earliest hop it was reached
            if not nodes[tx["to"]]["is_source"]:
                nodes[tx["to"]]["hop"] = min(nodes[tx["to"]]["hop"], tx["hop"])

            edges.append(
                {
                    "id": f'{tx["tx_hash"]}:{i}',
                    "source": tx["from"],
                    "target": tx["to"],
                    "network": "TRON",
                    "asset": tx["asset"],
                    "amount": tx["amount"],
                    "hop": tx["hop"],
                    "tx_hash": tx["tx_hash"],
                    "block_number": tx["block_number"],
                    "timestamp": tx["timestamp"],
                    "contract_type": tx["contract_type"],
                    "contract_address": tx["contract_address"],
                }
            )

        return {"nodes": list(nodes.values()), "edges": edges}
