"""In-memory transaction mempool."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from genesis.chain.transaction import Transaction

logger = logging.getLogger(__name__)


class Mempool:
    """Thread-safe in-memory pool of unconfirmed transactions."""

    def __init__(self, max_size: int = 10000) -> None:
        self._max_size = max_size
        self._txs: OrderedDict[str, Transaction] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_transaction(self, tx: Transaction) -> bool:
        """Validate and add a transaction to the mempool.

        Returns True if the transaction was added, False if it was rejected
        (duplicate, full pool, or invalid hash).
        """
        # Basic structural validation
        if not tx.tx_hash or tx.tx_hash != tx.compute_hash():
            logger.debug("Mempool rejected tx with bad hash: %s", tx.tx_hash)
            return False

        if not tx.signature:
            logger.debug("Mempool rejected unsigned tx: %s", tx.tx_hash)
            return False

        with self._lock:
            if tx.tx_hash in self._txs:
                return False
            if len(self._txs) >= self._max_size:
                logger.warning("Mempool full (%d), rejecting tx %s", self._max_size, tx.tx_hash)
                return False
            self._txs[tx.tx_hash] = tx

        return True

    def get_transactions(self, max_count: int = 100) -> list[Transaction]:
        """Return up to *max_count* pending transactions for block inclusion.

        Transactions are returned in insertion order (FIFO).
        """
        with self._lock:
            return list(self._txs.values())[:max_count]

    def remove_transactions(self, tx_hashes: list[str]) -> None:
        """Remove transactions that have been included in a block."""
        with self._lock:
            for h in tx_hashes:
                self._txs.pop(h, None)

    def has_transaction(self, tx_hash: str) -> bool:
        with self._lock:
            return tx_hash in self._txs

    def size(self) -> int:
        with self._lock:
            return len(self._txs)

    def clear(self) -> None:
        with self._lock:
            self._txs.clear()
