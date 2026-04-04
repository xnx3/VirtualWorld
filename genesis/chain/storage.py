"""SQLite-backed blockchain persistence using direct sqlite3 calls.

The earlier async/threaded sqlite wrappers could stall during real startup in
source and packaged environments. Genesis performs short, local sqlite
operations, so the most reliable option here is to keep the async API surface
but execute the sqlite work synchronously inside those coroutine methods.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY,
    hash TEXT UNIQUE NOT NULL,
    previous_hash TEXT NOT NULL,
    merkle_root TEXT NOT NULL,
    proposer TEXT NOT NULL,
    proposer_public_key TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL,
    timestamp REAL NOT NULL,
    nonce INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_hash TEXT PRIMARY KEY,
    block_height INTEGER REFERENCES blocks(height),
    tx_type TEXT NOT NULL,
    sender TEXT NOT NULL,
    public_key TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL,
    signature TEXT NOT NULL,
    timestamp REAL NOT NULL,
    nonce INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS world_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_block INTEGER
);
"""


class ChainStorage:
    """Async facade over a serialized sqlite3 connection."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database and create tables if they do not exist."""
        if self._db is None:
            self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._initialize_sync()

    def _initialize_sync(self) -> None:
        db = self._ensure_db()
        db.executescript(_SCHEMA_SQL)
        db.commit()
        self._ensure_column_sync("blocks", "proposer_public_key", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_sync("transactions", "public_key", "TEXT NOT NULL DEFAULT ''")
        db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is None:
            return
        db = self._db
        self._db = None
        db.close()

    def _ensure_db(self) -> sqlite3.Connection:
        if self._db is None:
            raise RuntimeError("ChainStorage not initialized; call initialize() first")
        return self._db

    def _ensure_column_sync(self, table: str, column: str, ddl: str) -> None:
        db = self._ensure_db()
        cursor = db.execute(f"PRAGMA table_info({table})")
        rows = cursor.fetchall()
        existing = {str(row[1]) for row in rows}
        if column in existing:
            return
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ------------------------------------------------------------------
    # Block persistence
    # ------------------------------------------------------------------

    async def save_block(self, block: Block) -> None:
        """Persist a block and its transactions."""
        self._save_block_sync(block)

    def _save_block_sync(self, block: Block) -> None:
        db = self._ensure_db()
        db.execute(
            """INSERT OR REPLACE INTO blocks
               (height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                block.index,
                block.hash,
                block.previous_hash,
                block.merkle_root,
                block.proposer,
                block.proposer_public_key,
                block.signature,
                block.timestamp,
                block.nonce,
            ),
        )

        for tx in block.transactions:
            db.execute(
                """INSERT OR REPLACE INTO transactions
                   (tx_hash, block_height, tx_type, sender, public_key, data, signature, timestamp, nonce)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tx.tx_hash,
                    block.index,
                    tx.tx_type.value,
                    tx.sender,
                    tx.public_key,
                    json.dumps(tx.data, sort_keys=True),
                    tx.signature,
                    tx.timestamp,
                    tx.nonce,
                ),
            )

        db.commit()

    def _block_from_row_sync(self, row: tuple[Any, ...], db: sqlite3.Connection) -> Block:
        """Reconstruct a Block from a database row, including its transactions."""
        height, blk_hash, prev_hash, mroot, proposer, proposer_public_key, sig, ts, nonce = row

        cursor = db.execute(
            "SELECT tx_hash, tx_type, sender, public_key, data, signature, timestamp, nonce "
            "FROM transactions WHERE block_height = ? ORDER BY nonce",
            (height,),
        )
        tx_rows = cursor.fetchall()

        transactions: list[Transaction] = []
        for tx_row in tx_rows:
            transactions.append(
                Transaction(
                    tx_hash=tx_row[0],
                    tx_type=TxType(tx_row[1]),
                    sender=tx_row[2],
                    public_key=tx_row[3] or "",
                    data=json.loads(tx_row[4]),
                    signature=tx_row[5],
                    timestamp=tx_row[6],
                    nonce=tx_row[7],
                )
            )

        return Block(
            index=height,
            timestamp=ts,
            previous_hash=prev_hash,
            merkle_root=mroot,
            proposer=proposer,
            proposer_public_key=proposer_public_key or "",
            signature=sig,
            transactions=transactions,
            nonce=nonce,
            hash=blk_hash,
        )

    async def get_block(self, height: int) -> Block | None:
        """Return the block at the given height, or None."""
        return self._get_block_sync(height)

    def _get_block_sync(self, height: int) -> Block | None:
        db = self._ensure_db()
        cursor = db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE height = ?",
            (height,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._block_from_row_sync(row, db)

    async def get_block_by_hash(self, hash: str) -> Block | None:
        """Return the block with the given hash, or None."""
        return self._get_block_by_hash_sync(hash)

    def _get_block_by_hash_sync(self, hash: str) -> Block | None:
        db = self._ensure_db()
        cursor = db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE hash = ?",
            (hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._block_from_row_sync(row, db)

    async def get_latest_block(self) -> Block | None:
        """Return the block at the current chain tip, or None if empty."""
        return self._get_latest_block_sync()

    def _get_latest_block_sync(self) -> Block | None:
        db = self._ensure_db()
        cursor = db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks ORDER BY height DESC LIMIT 1",
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._block_from_row_sync(row, db)

    async def get_chain_height(self) -> int:
        """Return the height of the latest block, or -1 if the chain is empty."""
        return self._get_chain_height_sync()

    def _get_chain_height_sync(self) -> int:
        db = self._ensure_db()
        cursor = db.execute("SELECT MAX(height) FROM blocks")
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return -1
        return int(row[0])

    async def get_blocks_range(self, start: int, end: int) -> list[Block]:
        """Return blocks with height in [start, end] inclusive."""
        return self._get_blocks_range_sync(start, end)

    def _get_blocks_range_sync(self, start: int, end: int) -> list[Block]:
        db = self._ensure_db()
        cursor = db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE height >= ? AND height <= ? ORDER BY height",
            (start, end),
        )
        rows = cursor.fetchall()
        return [self._block_from_row_sync(row, db) for row in rows]

    async def clear_chain(self) -> None:
        """Delete all persisted blocks, transactions, and derived world state."""
        self._clear_chain_sync()

    def _clear_chain_sync(self) -> None:
        db = self._ensure_db()
        db.execute("DELETE FROM transactions")
        db.execute("DELETE FROM blocks")
        db.execute("DELETE FROM world_state")
        db.commit()

    # ------------------------------------------------------------------
    # World state
    # ------------------------------------------------------------------

    async def save_world_state(self, key: str, value: str, block_height: int) -> None:
        """Upsert a world-state key/value pair."""
        self._save_world_state_sync(key, value, block_height)

    def _save_world_state_sync(self, key: str, value: str, block_height: int) -> None:
        db = self._ensure_db()
        db.execute(
            "INSERT OR REPLACE INTO world_state (key, value, updated_at_block) VALUES (?, ?, ?)",
            (key, value, block_height),
        )
        db.commit()

    async def get_world_state(self, key: str) -> str | None:
        """Return the current value for a world-state key, or None."""
        return self._get_world_state_sync(key)

    def _get_world_state_sync(self, key: str) -> str | None:
        db = self._ensure_db()
        cursor = db.execute(
            "SELECT value FROM world_state WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return str(row[0])
