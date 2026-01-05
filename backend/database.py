import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4


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
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            name TEXT NOT NULL,
            qr_code TEXT NOT NULL UNIQUE,
            qr_expires_at TEXT NOT NULL,
            face_encoding TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    # Migracja: sprawdź czy kolumny istnieją, jeśli nie - dodaj je
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    
    # Migracja dla first_name
    if "first_name" not in columns:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
            # Wyciągnij first_name z kolumny name (jeśli istnieje) lub ustaw domyślną wartość
            cur.execute("UPDATE users SET first_name = CASE WHEN name IS NOT NULL AND name != '' THEN SUBSTR(name, 1, INSTR(name || ' ', ' ') - 1) ELSE 'Pracownik' END WHERE first_name IS NULL")
        except sqlite3.OperationalError:
            pass
    
    # Migracja dla last_name
    if "last_name" not in columns:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
            # Wyciągnij last_name z kolumny name (jeśli istnieje) lub ustaw domyślną wartość
            cur.execute("UPDATE users SET last_name = CASE WHEN name IS NOT NULL AND name != '' AND INSTR(name, ' ') > 0 THEN SUBSTR(name, INSTR(name, ' ') + 1) ELSE '' END WHERE last_name IS NULL")
        except sqlite3.OperationalError:
            pass
    
    # Migracja dla qr_expires_at
    if "qr_expires_at" not in columns:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN qr_expires_at TEXT")
            # Ustaw domyślną wartość dla istniejących rekordów (np. bardzo odległą datę)
            cur.execute("UPDATE users SET qr_expires_at = '2099-12-31T23:59:59' WHERE qr_expires_at IS NULL")
        except sqlite3.OperationalError:
            pass
    
    # Migracja dla created_at
    if "created_at" not in columns:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            # Ustaw domyślną wartość dla istniejących rekordów (aktualna data)
            default_date = datetime.utcnow().replace(microsecond=0).isoformat()
            cur.execute("UPDATE users SET created_at = ? WHERE created_at IS NULL", (default_date,))
        except sqlite3.OperationalError:
            pass
    
    # Migracja dla updated_at
    if "updated_at" not in columns:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN updated_at TEXT")
            # Ustaw domyślną wartość dla istniejących rekordów (aktualna data)
            default_date = datetime.utcnow().replace(microsecond=0).isoformat()
            cur.execute("UPDATE users SET updated_at = ? WHERE updated_at IS NULL", (default_date,))
        except sqlite3.OperationalError:
            pass

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_qr_code ON users (qr_code)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_qr_expires_at ON users (qr_expires_at)")

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
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_user_id ON events (user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events (status)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL
        );
        """
    )
    # Zapewnij pojedynczy wiersz (id=1). Pusty string oznacza "hasło jeszcze nie ustawione".
    cur.execute("INSERT OR IGNORE INTO admin_settings (id, password_hash) VALUES (1, '')")

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
    if not first_name or not last_name:
        raise ValueError("Imię i nazwisko są wymagane.")
    if not qr_expires_at_iso:
        raise ValueError("Ważność kodu QR jest wymagana.")
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
    cur.execute("SELECT password_hash FROM admin_settings WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row["password_hash"] or None


def set_admin_password_hash(db_path: str, password_hash: str) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE admin_settings SET password_hash = ? WHERE id = 1", (password_hash,))
    conn.commit()
    conn.close()