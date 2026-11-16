"""MySQL persistence for the Smart Helmet Detection Streamlit app.

Configure connection values in .streamlit/secrets.toml or environment variables.
Never commit credentials to GitHub.
"""

import os

import mysql.connector
import pandas as pd
import streamlit as st


def _read_config():
    cfg = {}
    try:
        section = st.secrets.get("mysql", {})
        cfg = {
            "host": section.get("host"),
            "port": section.get("port", 3306),
            "user": section.get("user"),
            "password": section.get("password"),
            "database": section.get("database", "smart_helmet_db"),
        }
    except Exception:
        cfg = {}

    for key in ("host", "port", "user", "password", "database"):
        env_name = f"MYSQL_{key.upper()}"
        if os.getenv(env_name):
            cfg[key] = os.getenv(env_name)

    required = ("host", "user", "password", "database")
    if not all(cfg.get(k) for k in required):
        return None
    cfg["port"] = int(cfg.get("port") or 3306)
    return cfg


def is_configured():
    return _read_config() is not None


def get_connection():
    cfg = _read_config()
    if not cfg:
        raise RuntimeError(
            "MySQL is not configured. Add a [mysql] section to .streamlit/secrets.toml "
            "or set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD and MYSQL_DATABASE."
        )
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        connection_timeout=10,
    )


def init_db():
    """Create the table if needed and upgrade the earlier simple table safely."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS detection_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            detection_status VARCHAR(50) NULL,
            confidence FLOAT NULL,
            ignition_status VARCHAR(20) NULL,
            detection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR(50) NULL,
            helmet_detections INT NULL,
            no_helmet_detections INT NULL,
            status VARCHAR(50) NULL,
            avg_confidence FLOAT NULL
        )
        """
    )
    cur.execute("SHOW COLUMNS FROM detection_history")
    existing = {row[0] for row in cur.fetchall()}
    additions = {
        "source": "VARCHAR(50) NULL",
        "helmet_detections": "INT NULL",
        "no_helmet_detections": "INT NULL",
        "status": "VARCHAR(50) NULL",
        "avg_confidence": "FLOAT NULL",
    }
    for column, definition in additions.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE detection_history ADD COLUMN {column} {definition}")
    conn.commit()
    cur.close()
    conn.close()


def save_detection(source, helmets, no_helmets, status, ignition, avg_confidence=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO detection_history
        (detection_status, confidence, ignition_status, source,
         helmet_detections, no_helmet_detections, status, avg_confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            status,
            avg_confidence,
            ignition,
            source,
            int(helmets),
            int(no_helmets),
            status,
            avg_confidence,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()


def fetch_history():
    conn = get_connection()
    try:
        df = pd.read_sql(
            """
            SELECT
                DATE_FORMAT(detection_time, '%Y-%m-%d %H:%i:%s') AS timestamp,
                COALESCE(source, 'legacy') AS source,
                COALESCE(helmet_detections, 0) AS helmet_detections,
                COALESCE(no_helmet_detections, 0) AS no_helmet_detections,
                COALESCE(ignition_status, 'OFF') AS virtual_ignition,
                COALESCE(status, detection_status, 'STATUS UNKNOWN') AS status,
                COALESCE(avg_confidence, confidence) AS avg_confidence
            FROM detection_history
            ORDER BY id ASC
            """,
            conn,
        )
        return df
    finally:
        conn.close()


def clear_history():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM detection_history")
    conn.commit()
    cur.close()
    conn.close()
