from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "network_monitor.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    interface TEXT NOT NULL,
    bytes_sent_total INTEGER NOT NULL,
    bytes_recv_total INTEGER NOT NULL,
    upload_bytes_per_sec REAL NOT NULL,
    download_bytes_per_sec REAL NOT NULL,
    packets_sent_total INTEGER NOT NULL,
    packets_recv_total INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traffic_timestamp
ON traffic_samples(timestamp);

CREATE INDEX IF NOT EXISTS idx_traffic_interface_timestamp
ON traffic_samples(interface, timestamp);


CREATE TABLE IF NOT EXISTS connection_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    protocol TEXT NOT NULL,
    local_ip TEXT,
    local_port INTEGER,
    remote_ip TEXT,
    remote_port INTEGER,
    status TEXT,
    pid INTEGER,
    process_name TEXT
);

CREATE INDEX IF NOT EXISTS idx_connections_timestamp
ON connection_samples(timestamp);

CREATE INDEX IF NOT EXISTS idx_connections_remote_ip
ON connection_samples(remote_ip);

CREATE INDEX IF NOT EXISTS idx_connections_process_name
ON connection_samples(process_name);
"""


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DB_PATH,
        timeout=10
    )

    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=5000;")
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        connection.commit()