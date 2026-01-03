import sqlite3
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_table_columns(cur: sqlite3.Cursor, table: str) -> set:
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall() or []
    return {row["name"] for row in rows}


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, column_type: str) -> None:
    """
    SQLite nie wspiera łatwych migracji schematu, ale pozwala dodawać kolumny.
    Ten helper jest bezpieczny dla istniejącej bazy: dodaje kolumnę tylko, gdy jej brakuje.
    """
    cols = _get_table_columns(cur, table)
    if column in cols:
        return
    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()

    # --- USERS / PRACOWNICY ---
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

    # Migracje "pracownicze" (nie wymuszamy NOT NULL, żeby nie psuć istniejących rekordów).
    _ensure_column(cur, "users", "first_name", "TEXT")
    _ensure_column(cur, "users", "last_name", "TEXT")
    _ensure_column(cur, "users", "qr_expires_at", "TEXT")  # ISO string, UTC
    _ensure_column(cur, "users", "created_at", "TEXT")  # ISO string, UTC
    _ensure_column(cur, "users", "updated_at", "TEXT")  # ISO string, UTC

    # --- STARE LOGI (zostawiamy dla kompatybilności) ---
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

    # --- NOWE ZDARZENIA (wejścia/wyjścia + błędy + obraz próby) ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT NOT NULL,
            direction TEXT NOT NULL,
            status TEXT NOT NULL,
            error_code TEXT,
            qr_code TEXT,
            attempt_image_b64 TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    # --- KONFIGURACJA ADMINA (hash hasła) ---
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT
        );
        """
    )
    # Zapewnij pojedynczy wiersz (id=1)
    cur.execute("INSERT OR IGNORE INTO admin_settings (id, password_hash) VALUES (1, NULL)")

    conn.commit()
    conn.close()


def get_user_by_qr(db_path: str, qr_code: str) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE qr_code = ?", (qr_code,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(db_path: str, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_users(db_path: str) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    rows = cur.fetchall() or []
    conn.close()
    return [dict(r) for r in rows]


def create_user(
    db_path: str,
    first_name: str,
    last_name: str,
    face_encoding_json: str,
    qr_expires_at_iso: Optional[str],
    created_at_iso: str,
) -> Tuple[int, str]:
    """
    Tworzy pracownika i generuje kod QR w formacie "EMP:{id}".
    Zwraca (user_id, qr_code_string).
    """
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    full_name = " ".join([p for p in [first_name, last_name] if p]).strip() or "Pracownik"

    tmp_qr = f"TMP:{uuid4().hex}"

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (name, qr_code, face_encoding, first_name, last_name, qr_expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            full_name,
            tmp_qr,
            face_encoding_json,
            first_name,
            last_name,
            qr_expires_at_iso,
            created_at_iso,
            created_at_iso,
        ),
    )
    user_id = int(cur.lastrowid)
    final_qr = f"EMP:{user_id}"
    cur.execute("UPDATE users SET qr_code = ?, updated_at = ? WHERE id = ?", (final_qr, created_at_iso, user_id))
    conn.commit()
    conn.close()
    return user_id, final_qr


def insert_event(
    db_path: str,
    user_id: Optional[int],
    timestamp_iso: str,
    direction: str,
    status: str,
    error_code: Optional[str] = None,
    qr_code: Optional[str] = None,
    attempt_image_b64: Optional[str] = None,
) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO events (user_id, timestamp, direction, status, error_code, qr_code, attempt_image_b64)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, timestamp_iso, direction, status, error_code, qr_code, attempt_image_b64),
    )
    conn.commit()
    conn.close()


def list_events(
    db_path: str,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Zwraca zdarzenia (wejścia/wyjścia) z opcjonalnym filtrem zakresu czasu.
    Uwaga: przechowujemy timestamp jako ISO string, więc porównania tekstowe działają.
    """
    query = """
        SELECT e.*, u.name as user_name
        FROM events e
        LEFT JOIN users u ON u.id = e.user_id
        WHERE 1=1
    """
    params: List[Any] = []

    if start_iso:
        query += " AND e.timestamp >= ?"
        params.append(start_iso)
    if end_iso:
        query += " AND e.timestamp <= ?"
        params.append(end_iso)
    if status:
        query += " AND e.status = ?"
        params.append(status)

    query += " ORDER BY e.timestamp DESC, e.id DESC"

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    rows = cur.fetchall() or []
    conn.close()
    return [dict(r) for r in rows]


def get_event_by_id(db_path: str, event_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.*, u.name as user_name
        FROM events e
        LEFT JOIN users u ON u.id = e.user_id
        WHERE e.id = ?
        """,
        (event_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_admin_password_hash(db_path: str) -> Optional[str]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    # tabela tworzona w init_db, ale db może być "stare" — zabezpieczenie:
    if not _table_exists(cur, "admin_settings"):
        conn.close()
        return None
    cur.execute("SELECT password_hash FROM admin_settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row["password_hash"]


def set_admin_password_hash(db_path: str, password_hash: str) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()
    if not _table_exists(cur, "admin_settings"):
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT
            );
            """
        )
        cur.execute("INSERT OR IGNORE INTO admin_settings (id, password_hash) VALUES (1, NULL)")

    cur.execute("UPDATE admin_settings SET password_hash = ? WHERE id = 1", (password_hash,))
    conn.commit()
    conn.close()


def insert_log(db_path: str, user_id: Optional[int], timestamp, result: str) -> None:
    """
    Legacy API: stare części projektu mogą nadal to wywoływać.
    Zapisujemy do starej tabeli `logs`.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (user_id, timestamp, result) VALUES (?, ?, ?)",
        (user_id, timestamp.isoformat(), result),
    )
    conn.commit()
    conn.close()


