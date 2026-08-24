import sqlite3
import re
import uuid as _uuid
from pathlib import Path
from contextlib import contextmanager

_DB_PATH = str(Path(__file__).parent.parent.parent / "test" / "database" / "datasage_test.db")

def _adapt_sql(sql: str) -> str:
    sql = sql.replace("%s", "?")
    sql = re.sub(r"::\w+", "", sql)
    return sql

def _split_returning(sql: str):
    match = re.search(r"\bRETURNING\b", sql, re.IGNORECASE)
    if match:
        return sql[: match.start()].strip(), True
    return sql, False

def _extract_table(sql: str) -> str:
    m = re.search(r"(?:INSERT\s+INTO|UPDATE)\s+(\w+)", sql, re.IGNORECASE)
    return m.group(1) if m else None

class _SQLiteDictCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._pending = None

    def execute(self, sql, params=()):
        sql = _adapt_sql(sql)
        sql, has_returning = _split_returning(sql)

        if has_returning:
            table = _extract_table(sql)
            upper = sql.upper().lstrip()

            if upper.startswith("INSERT"):
                new_id = str(_uuid.uuid4())
                sql = re.sub(
                    r"(INSERT\s+INTO\s+\w+\s*\()",
                    r"\g<1>id, ",
                    sql,
                    flags=re.IGNORECASE,
                )
                sql = re.sub(
                    r"(VALUES\s*\()",
                    r"\g<1>?, ",
                    sql,
                    flags=re.IGNORECASE,
                )
                params = (new_id,) + tuple(params)
                self._pending = (table, new_id)
            else:
                self._pending = (table, params[-1] if params else None)

            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql, params)

    def fetchone(self):
        if self._pending:
            table, row_id = self._pending
            self._pending = None
            self._cur.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))

        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return dict(zip(cols, row))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [dict(zip(cols, r)) for r in rows]

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

class _SQLiteConn:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys = ON")

    def cursor(self, cursor_factory=None):
        return _SQLiteDictCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

@contextmanager
def get_db():
    conn = _SQLiteConn(_DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
