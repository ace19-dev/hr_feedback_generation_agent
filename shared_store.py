"""
shared_store.py - SQLite 기반 공유 상태 저장소

에이전트 간에 중간 결과를 공유하기 위한 저장소입니다.
Orchestrator가 각 에이전트의 결과(summary, draft, quality, comparison)를
이 저장소를 통해 다음 에이전트로 전달합니다.

스키마:
  - session: 세션 메타데이터 (직원, 상태)
  - result: 에이전트별 결과 JSON
"""

import re
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import STATE_DB_DIR, MOCK_DATA_DIR


# 직원별로 별도 DB 파일을 사용해 충돌을 방지합니다.
def _get_db_path(session_id: str) -> Path:
    """세션 ID로 SQLite DB 파일 경로를 반환합니다."""
    return STATE_DB_DIR / f"session_{session_id}.db"


def _get_conn(session_id: str) -> sqlite3.Connection:
    """
    DB 연결을 생성하고, 테이블이 없으면 자동으로 생성합니다.
    Row를 dict처럼 접근할 수 있도록 row_factory를 설정합니다.
    """
    db_path = _get_db_path(session_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # column명으로 접근 가능하게

    # 테이블이 없으면 생성 (멱등 - 이미 있으면 무시)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session (
            session_id   TEXT PRIMARY KEY,
            emp_id       TEXT NOT NULL,
            created_at   TEXT,
            status       TEXT   -- pending / running / awaiting_human / done / failed
        );

        CREATE TABLE IF NOT EXISTS result (
            session_id   TEXT,
            step         TEXT,    -- summary / draft / quality / comparison
            payload      TEXT,    -- JSON blob
            updated_at   TEXT,
            PRIMARY KEY (session_id, step)
        );
    """)
    conn.commit()
    return conn


# ─── 세션 관리 ────────────────────────────────────────────────

def create_session(session_id: str, emp_id: str) -> None:
    """새 평가 세션을 생성합니다."""
    conn = _get_conn(session_id)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO session (session_id, emp_id, created_at, status) VALUES (?, ?, ?, ?)",
            (session_id, emp_id, datetime.now().isoformat(), "pending")
        )
        conn.commit()
    finally:
        conn.close()


def update_session_status(session_id: str, status: str) -> None:
    """세션 상태를 변경합니다. (pending → running → awaiting_human → done)"""
    conn = _get_conn(session_id)
    try:
        conn.execute(
            "UPDATE session SET status = ? WHERE session_id = ?",
            (status, session_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[dict]:
    """세션 정보를 반환합니다. 없으면 None."""
    conn = _get_conn(session_id)
    try:
        row = conn.execute(
            "SELECT * FROM session WHERE session_id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── 결과 저장/조회 ──────────────────────────────────────────

def save_result(session_id: str, step: str, payload: dict) -> None:
    """
    에이전트 실행 결과를 저장합니다.

    Args:
        session_id: 세션 ID
        step: 저장할 단계명 ("summary" | "draft" | "quality" | "comparison")
        payload: 저장할 결과 딕셔너리 (JSON 직렬화 가능해야 함)
    """
    conn = _get_conn(session_id)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO result (session_id, step, payload, updated_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, step, json.dumps(payload, ensure_ascii=False), datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_result(session_id: str, step: str) -> Optional[dict]:
    """
    특정 단계의 결과를 조회합니다.

    Returns:
        결과 딕셔너리, 없으면 None
    """
    conn = _get_conn(session_id)
    try:
        row = conn.execute(
            "SELECT payload FROM result WHERE session_id = ? AND step = ?",
            (session_id, step)
        ).fetchone()
        return json.loads(row["payload"]) if row else None
    finally:
        conn.close()


def get_all_results(session_id: str) -> dict:
    """세션의 모든 단계 결과를 {step: payload} 형태로 반환합니다."""
    conn = _get_conn(session_id)
    try:
        rows = conn.execute(
            "SELECT step, payload FROM result WHERE session_id = ?",
            (session_id,)
        ).fetchall()
        return {row["step"]: json.loads(row["payload"]) for row in rows}
    finally:
        conn.close()


# ─── 직원 ID 표시 변환 ────────────────────────────────────────

def format_emp_references(text: str) -> str:
    """
    텍스트 내 직원 ID("E001" 등)를 "이름 직책" 형태로 치환합니다.
    결과 메시지에 emp_id가 그대로 노출되는 것을 방지하기 위해 사용합니다.
    """
    filepath = MOCK_DATA_DIR / "employees.json"
    if not filepath.exists():
        return text
    with open(filepath, "r", encoding="utf-8") as f:
        employees = json.load(f)
    emp_map = {e["emp_id"]: f'{e["name"]} {e["role"]}' for e in employees}

    def _replace(match: re.Match) -> str:
        emp_id = match.group(0)
        return emp_map.get(emp_id, emp_id)

    # \b는 한글 뒤에서 단어 경계로 인식되지 않으므로 lookaround로 직접 경계를 지정합니다.
    return re.sub(r"(?<![A-Za-z0-9])E\d{3}(?!\d)", _replace, text)


def format_emp_references_deep(obj):
    """
    딕셔너리/리스트를 재귀적으로 순회하며 문자열 값에 format_emp_references를 적용합니다.
    "emp_id" 키 값은 식별자이므로 변환 대상에서 제외합니다.
    """
    if isinstance(obj, dict):
        return {
            k: (v if k == "emp_id" else format_emp_references_deep(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [format_emp_references_deep(v) for v in obj]
    if isinstance(obj, str):
        return format_emp_references(obj)
    return obj


def delete_session(session_id: str) -> None:
    """세션 DB 파일을 통째로 삭제합니다. (세션 만료 시 호출)"""
    db_path = _get_db_path(session_id)
    if db_path.exists():
        db_path.unlink()
