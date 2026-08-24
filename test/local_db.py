"""
local_db.py — SQLite test database for DataSage backend.

Schema mirrors supabase_table.txt (users + stacks).
All functions return (result, rows_affected) so notebooks can see what was touched.
No app imports — fully standalone.
"""

import sqlite3
import json
import uuid
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = str(Path(__file__).parent / "database" / "datasage_test.db")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id       TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    passcode TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_STACKS = """
CREATE TABLE IF NOT EXISTS stacks (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    ops        TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

_CREATE_IDX = "CREATE INDEX IF NOT EXISTS stacks_user_id_idx ON stacks(user_id);"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _row_to_dict(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    # Deserialize ops JSON string back to list
    if "ops" in d and isinstance(d["ops"], str):
        try:
            d["ops"] = json.loads(d["ops"])
        except json.JSONDecodeError:
            pass
    return d

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_USERS)
        conn.execute(_CREATE_STACKS)
        conn.execute(_CREATE_IDX)
    print(f"Database initialised at: {DB_PATH}")


def reset_db() -> None:
    """Drop and recreate all tables. Destroys all data."""
    with _connect() as conn:
        conn.execute("DROP TABLE IF EXISTS stacks")
        conn.execute("DROP TABLE IF EXISTS users")
        conn.execute(_CREATE_USERS)
        conn.execute(_CREATE_STACKS)
        conn.execute(_CREATE_IDX)
    print("Database reset complete.")


# --- Users ------------------------------------------------------------------

def create_user(username: str, passcode: str) -> Tuple[Dict, int]:
    """
    Insert a new user.
    Returns (user_dict, rows_affected).
    Raises sqlite3.IntegrityError if username already exists.
    """
    new_id = str(uuid.uuid4())
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (id, username, passcode) VALUES (?, ?, ?)",
            (new_id, username, passcode),
        )
        rows = cur.rowcount
        user = dict(conn.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone())
    return user, rows


def get_user(username: str) -> Tuple[Optional[Dict], int]:
    """
    Fetch a user by username.
    Returns (user_dict | None, 1 if found else 0).
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        return None, 0
    return dict(row), 1


def authenticate(username: str, passcode: str) -> Tuple[Optional[Dict], int]:
    """
    Verify credentials.
    Returns (user_dict, 1) on success, (None, 0) on failure.
    """
    user, found = get_user(username)
    if not found or user["passcode"] != passcode:
        return None, 0
    return user, 1


def list_users() -> Tuple[List[Dict], int]:
    """Return all users."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    result = [dict(r) for r in rows]
    return result, len(result)


def delete_user(user_id: str) -> Tuple[None, int]:
    """Delete a user (cascades to their stacks)."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return None, cur.rowcount


# --- Stacks -----------------------------------------------------------------

def list_stacks(user_id: str) -> Tuple[List[Dict], int]:
    """
    List all stacks for a user, newest first.
    Returns (list_of_stack_dicts, count).
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM stacks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    result = [_row_to_dict(r) for r in rows]
    return result, len(result)


def create_stack(user_id: str, name: str, ops: List[Dict]) -> Tuple[Dict, int]:
    """
    Insert a new stack.
    Returns (stack_dict, 1).
    """
    new_id = str(uuid.uuid4())
    ops_json = json.dumps(ops)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO stacks (id, user_id, name, ops) VALUES (?, ?, ?, ?)",
            (new_id, user_id, name, ops_json),
        )
        rows = cur.rowcount
        stack = _row_to_dict(conn.execute("SELECT * FROM stacks WHERE id = ?", (new_id,)).fetchone())
    return stack, rows


def get_stack(stack_id: str) -> Tuple[Optional[Dict], int]:
    """Fetch a single stack by id."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM stacks WHERE id = ?", (stack_id,)).fetchone()
    if row is None:
        return None, 0
    return _row_to_dict(row), 1


def update_stack(stack_id: str, name: str, ops: List[Dict]) -> Tuple[Optional[Dict], int]:
    """
    Update stack name and ops.
    Returns (updated_stack_dict | None, rows_affected).
    """
    ops_json = json.dumps(ops)
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE stacks SET name = ?, ops = ? WHERE id = ?",
            (name, ops_json, stack_id),
        )
        rows = cur.rowcount
        if rows == 0:
            return None, 0
        stack = _row_to_dict(conn.execute("SELECT * FROM stacks WHERE id = ?", (stack_id,)).fetchone())
    return stack, rows


def delete_stack(stack_id: str) -> Tuple[None, int]:
    """
    Delete a stack by id.
    Returns (None, rows_affected).
    """
    with _connect() as conn:
        cur = conn.execute("DELETE FROM stacks WHERE id = ?", (stack_id,))
    return None, cur.rowcount
