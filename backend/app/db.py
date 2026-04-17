from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import secrets
import sqlite3
from typing import Any

from .config import get_settings


settings = get_settings()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                github_user_id INTEGER NOT NULL UNIQUE,
                login TEXT NOT NULL,
                name TEXT,
                avatar_url TEXT,
                access_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                repo_full_name TEXT NOT NULL,
                base_branch TEXT NOT NULL,
                fix_branch TEXT,
                pr_number INTEGER,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT,
                pr_url TEXT,
                merged_at TEXT,
                merge_commit_sha TEXT,
                error TEXT,
                logs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )
        _ensure_job_columns(connection)


def _table_has_column(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def _ensure_job_columns(connection: sqlite3.Connection) -> None:
    if not _table_has_column(connection, "jobs", "pr_number"):
        connection.execute("ALTER TABLE jobs ADD COLUMN pr_number INTEGER")
    if not _table_has_column(connection, "jobs", "merged_at"):
        connection.execute("ALTER TABLE jobs ADD COLUMN merged_at TEXT")
    if not _table_has_column(connection, "jobs", "merge_commit_sha"):
        connection.execute("ALTER TABLE jobs ADD COLUMN merge_commit_sha TEXT")


def create_oauth_state() -> str:
    state = secrets.token_urlsafe(32)
    with connect() as connection:
        connection.execute(
            "INSERT INTO oauth_states (state, created_at) VALUES (?, ?)",
            (state, utc_now()),
        )
    return state


def pop_oauth_state(state: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        return cursor.rowcount > 0


def upsert_user(*, github_user_id: int, login: str, name: str | None, avatar_url: str | None, access_token: str) -> int:
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO users (github_user_id, login, name, avatar_url, access_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(github_user_id) DO UPDATE SET
                login = excluded.login,
                name = excluded.name,
                avatar_url = excluded.avatar_url,
                access_token = excluded.access_token,
                updated_at = excluded.updated_at
            """,
            (github_user_id, login, name, avatar_url, access_token, now, now),
        )
        row = connection.execute(
            "SELECT id FROM users WHERE github_user_id = ?",
            (github_user_id,),
        ).fetchone()
    return int(row["id"])


def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, expires_at, utc_now()),
        )
    return session_id


def delete_session(session_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def get_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None

    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                sessions.id AS session_id,
                sessions.expires_at,
                users.id AS user_id,
                users.github_user_id,
                users.login,
                users.name,
                users.avatar_url,
                users.access_token
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.id = ?
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= datetime.now(timezone.utc):
        delete_session(session_id)
        return None

    return dict(row)


def create_job(*, user_id: int, repo_full_name: str, base_branch: str, prompt: str) -> dict[str, Any]:
    job_id = secrets.token_hex(16)
    now = utc_now()
    payload = {
        "id": job_id,
        "user_id": user_id,
        "repo_full_name": repo_full_name,
        "base_branch": base_branch,
        "pr_number": None,
        "prompt": prompt,
        "status": "queued",
        "summary_json": None,
        "pr_url": None,
        "merged_at": None,
        "merge_commit_sha": None,
        "error": None,
        "logs_json": "[]",
        "created_at": now,
        "updated_at": now,
    }
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (id, user_id, repo_full_name, base_branch, pr_number, prompt, status, summary_json, pr_url, merged_at, merge_commit_sha, error, logs_json, created_at, updated_at)
            VALUES (:id, :user_id, :repo_full_name, :base_branch, :pr_number, :prompt, :status, :summary_json, :pr_url, :merged_at, :merge_commit_sha, :error, :logs_json, :created_at, :updated_at)
            """,
            payload,
        )
    return get_job(job_id, user_id=user_id)


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        raise ValueError("update_job requires at least one field")

    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = :{key}" for key in fields.keys())
    fields["job_id"] = job_id

    with connect() as connection:
        connection.execute(f"UPDATE jobs SET {assignments} WHERE id = :job_id", fields)
    return get_job(job_id)


def append_job_log(job_id: str, message: str) -> dict[str, Any]:
    job = get_job(job_id)
    logs = job.get("logs", []) if job else []
    logs.append(message)
    return update_job(job_id, logs_json=json.dumps(logs))


def get_job(job_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM jobs WHERE id = ?"
    args: list[Any] = [job_id]
    if user_id is not None:
        query += " AND user_id = ?"
        args.append(user_id)

    with connect() as connection:
        row = connection.execute(query, args).fetchone()

    if row is None:
        return None

    payload = dict(row)
    payload["logs"] = json.loads(payload.pop("logs_json") or "[]")
    payload["summary"] = json.loads(payload.pop("summary_json")) if payload.get("summary_json") else None
    return payload


def get_access_token_for_user(user_id: int) -> str:
    with connect() as connection:
        row = connection.execute("SELECT access_token FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(f"User {user_id} not found")
    return str(row["access_token"])
