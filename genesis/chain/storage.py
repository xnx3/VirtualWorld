"""SQLite-backed blockchain persistence using aiosqlite."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

from genesis.chain.block import Block
from genesis.chain.transaction import Transaction, TxType

logger = logging.getLogger(__name__)

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
    """Async SQLite storage for the blockchain."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database and create tables if they do not exist."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()
        await self._ensure_column("blocks", "proposer_public_key", "TEXT NOT NULL DEFAULT ''")
        await self._ensure_column("transactions", "public_key", "TEXT NOT NULL DEFAULT ''")
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("ChainStorage not initialized; call initialize() first")
        return self._db

    async def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        db = self._ensure_db()
        cursor = await db.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        existing = {str(row[1]) for row in rows}
        if column in existing:
            return
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ------------------------------------------------------------------
    # Block persistence
    # ------------------------------------------------------------------

    async def save_block(self, block: Block) -> None:
        """Persist a block and its transactions."""
        db = self._ensure_db()

        await db.execute(
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
            await db.execute(
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

        await db.commit()

    async def _block_from_row(self, row: aiosqlite.Row, db: aiosqlite.Connection) -> Block:
        """Reconstruct a Block from a database row, including its transactions."""
        height, blk_hash, prev_hash, mroot, proposer, proposer_public_key, sig, ts, nonce = row

        cursor = await db.execute(
            "SELECT tx_hash, tx_type, sender, public_key, data, signature, timestamp, nonce "
            "FROM transactions WHERE block_height = ? ORDER BY nonce",
            (height,),
        )
        tx_rows = await cursor.fetchall()

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
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE height = ?",
            (height,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return await self._block_from_row(row, db)

    async def get_block_by_hash(self, hash: str) -> Block | None:
        """Return the block with the given hash, or None."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE hash = ?",
            (hash,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return await self._block_from_row(row, db)

    async def get_latest_block(self) -> Block | None:
        """Return the block at the current chain tip, or None if empty."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks ORDER BY height DESC LIMIT 1",
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return await self._block_from_row(row, db)

    async def get_chain_height(self) -> int:
        """Return the height of the latest block, or -1 if the chain is empty."""
        db = self._ensure_db()
        cursor = await db.execute("SELECT MAX(height) FROM blocks")
        row = await cursor.fetchone()
        if row is None or row[0] is None:
            return -1
        return int(row[0])

    async def get_blocks_range(self, start: int, end: int) -> list[Block]:
        """Return blocks with height in [start, end] inclusive."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT height, hash, previous_hash, merkle_root, proposer, proposer_public_key, signature, timestamp, nonce "
            "FROM blocks WHERE height >= ? AND height <= ? ORDER BY height",
            (start, end),
        )
        rows = await cursor.fetchall()
        blocks: list[Block] = []
        for row in rows:
            blocks.append(await self._block_from_row(row, db))
        return blocks

    # ------------------------------------------------------------------
    # World state
    # ------------------------------------------------------------------

    async def save_world_state(self, key: str, value: str, block_height: int) -> None:
        """Upsert a world-state key/value pair."""
        db = self._ensure_db()
        await db.execute(
            "INSERT OR REPLACE INTO world_state (key, value, updated_at_block) VALUES (?, ?, ?)",
            (key, value, block_height),
        )
        await db.commit()

    async def get_world_state(self, key: str) -> str | None:
        """Return the current value for a world-state key, or None."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT value FROM world_state WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return str(row[0])
