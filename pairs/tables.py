"""Persistent tables for frozen anonymous pair evidence."""

import sqlite3


def init_pair_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS pair_batches (
            batch_id TEXT PRIMARY KEY NOT NULL,
            roster TEXT NOT NULL,
            seal TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS pair_sources (
            batch_id TEXT NOT NULL REFERENCES pair_batches (batch_id),
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            source_id TEXT NOT NULL,
            members TEXT NOT NULL,
            readings TEXT NOT NULL,
            PRIMARY KEY (batch_id, ordinal),
            UNIQUE (batch_id, source_id)
        )
    ''')
