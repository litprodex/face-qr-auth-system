import sqlite3
from typing import Optional, Dict, Any


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            qr_code TEXT NOT NULL UNIQUE,
            face_encoding TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT NOT NULL,
            result TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    conn.commit()
    conn.close()


def get_user_by_qr(db_path: str, qr_code: str) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE qr_code = ?", (qr_code,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_log(db_path: str, user_id: Optional[int], timestamp, result: str) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (user_id, timestamp, result) VALUES (?, ?, ?)",
        (user_id, timestamp.isoformat(), result),
    )
    conn.commit()
    conn.close()


