"""
ui/app.py - FastAPI 백엔드 + WebSocket 서버

팀장 UI에 REST API와 실시간 WebSocket 이벤트를 제공합니다.
Orchestrator를 asyncio Task로 실행하고 결과를 WebSocket으로 push합니다.

엔드포인트:
  GET  /                         → 팀장 UI (index.html)
  GET  /api/employees            → 직원 목록 조회
  POST /api/evaluate             → 평가 파이프라인 시작
  POST /api/approve/{session_id} → 팀장 초안 승인/수정
  POST /api/recheck/{session_id} → 초안 수정 후 품질 체크 재실행
  GET  /api/session/{session_id} → 세션 전체 결과 조회
  WS   /ws/{session_id}          → 실시간 이벤트 스트림
"""

import json
import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel

# ui/ 디렉터리에서 실행되므로 프로젝트 루트를 sys.path에 추가합니다.
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import run_pipeline, approve_draft
from agents import agent3_quality
from agents.agent2_draft import apply_human_edits
from shared_store import get_all_results, get_session, get_result
from config import MOCK_DATA_DIR

app = FastAPI(title="HR 피드백 보조 AI", version="1.0.0")

# 정적 파일 (CSS, JS) 서빙 디렉터리
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Jinja2 HTML 템플릿 설정
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ─── WebSocket 연결 관리 ──────────────────────────────────
# 세션 ID → WebSocket 리스트 (같은 세션을 여러 탭에서 열 수 있음)
_ws_connections: dict[str, list[WebSocket]] = {}


async def _send_to_session(session_id: str, event_type: str, data: dict):
    """
    특정 세션의 모든 WebSocket 클라이언트로 이벤트를 전송합니다.
    Orchestrator의 notify_func 콜백으로 주입됩니다.
    끊어진 연결은 자동으로 정리합니다.
    """
    connections = _ws_connections.get(session_id, [])
    if not connections:
        return

    payload = json.dumps(
        {"type": event_type, "session_id": session_id, **data},
        ensure_ascii=False
    )

    alive = []
    for ws in connections:
        try:
            await ws.send_text(payload)
            alive.append(ws)
        except Exception:
            pass  # 끊어진 연결은 조용히 제거

    _ws_connections[session_id] = alive


# ─── Pydantic 요청 모델 ──────────────────────────────────

class EvaluateRequest(BaseModel):
    emp_id: str       # 평가 대상 직원 ID (예: "E001")
    year: int = 2025

class ApproveRequest(BaseModel):
    edits: dict = {}  # 팀장 수정 내용 (빈 딕셔너리면 원본 초안 그대로 승인)

class RecheckRequest(BaseModel):
    edits: dict = {}  # 재검토 전 반영할 초안 수정 내용


# ─── REST API ────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    """팀장 UI 메인 화면을 렌더링합니다."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/employees")
async def get_employees():
    """
    평가 대상 팀원 목록을 반환합니다.
    팀장(is_manager=True)은 목록에서 제외됩니다.
    """
    filepath = MOCK_DATA_DIR / "employees.json"
    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail="employees.json이 없습니다. python generate_mock_data.py를 먼저 실행하세요."
        )

    with open(filepath, "r", encoding="utf-8") as f:
        employees = json.load(f)

    members = [e for e in employees if not e.get("is_manager", False)]
    return {"employees": members}


@app.post("/api/evaluate")
async def start_evaluation(req: EvaluateRequest):
    """
    평가 파이프라인을 시작합니다.
    Orchestrator를 백그라운드 Task로 실행하고 session_id를 즉시 반환합니다.
    실제 진행 상황은 WebSocket /ws/{session_id} 로 수신합니다.
    """
    session_id = str(uuid.uuid4())[:8]

    # create_task: 현재 요청을 블로킹하지 않고 백그라운드에서 파이프라인 실행
    asyncio.create_task(
        run_pipeline(
            emp_id=req.emp_id,
            year=req.year,
            notify_func=_send_to_session,
            session_id=session_id,
        )
    )

    return {
        "session_id": session_id,
        "emp_id": req.emp_id,
        "message": f"파이프라인 시작. WebSocket /ws/{session_id} 로 연결하세요.",
    }


@app.post("/api/approve/{session_id}")
async def approve_evaluation(session_id: str, req: ApproveRequest):
    """
    팀장이 피드백 초안을 승인합니다.
    수정 내용(edits)이 있으면 draft에 반영한 후 Human Gate를 해제합니다.
    """
    success = approve_draft(session_id, req.edits or None)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"세션 {session_id}의 대기 상태를 찾을 수 없습니다. 이미 처리됐거나 만료된 세션입니다."
        )

    return {
        "message": "승인 완료. 품질 체크 및 비교뷰 생성을 시작합니다.",
        "session_id": session_id,
    }


@app.post("/api/recheck/{session_id}")
async def recheck_quality(session_id: str, req: RecheckRequest):
    """
    팀장이 품질 체크 경고를 참고해 초안을 수정한 뒤, 품질 체크(기능3)를
    다시 실행합니다. 비교뷰(기능4)는 재실행하지 않습니다.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"세션 {session_id}을 찾을 수 없습니다.")

    if req.edits:
        draft = apply_human_edits(session_id, req.edits)
        await _send_to_session(session_id, "step_result", {
            "step": "draft",
            "message": "초안 수정 반영",
            "data": draft,
        })

    summary = get_result(session_id, "summary") or {}
    year = summary.get("year", 2025)

    quality = await agent3_quality.run(session["emp_id"], session_id, year)

    await _send_to_session(session_id, "step_result", {
        "step": "quality",
        "message": f"품질 재체크 완료 (경고 {quality.get('warning_count', 0)}건)",
        "data": quality,
    })

    return {"session_id": session_id, "quality": quality}


@app.get("/api/session/{session_id}")
async def get_session_results(session_id: str):
    """
    세션의 모든 결과(summary, draft, quality, comparison)를 반환합니다.
    페이지 새로고침 시 최신 상태를 복원하는 데 사용됩니다.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"세션 {session_id}을 찾을 수 없습니다.")

    return {
        "session": session,
        "results": get_all_results(session_id),
    }


# ─── WebSocket 엔드포인트 ────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    팀장 UI와 실시간으로 통신하는 WebSocket 엔드포인트.
    에이전트 진행 상황, 단계별 결과, Human Gate 알림을 클라이언트로 push합니다.
    """
    await websocket.accept()

    # 연결 목록에 추가합니다.
    _ws_connections.setdefault(session_id, []).append(websocket)
    print(f"[WebSocket] 연결: {session_id} (현재 {len(_ws_connections[session_id])}개 연결)")

    # 이미 결과가 있는 세션이면 현재 상태를 즉시 전송합니다. (새로고침 대응)
    existing = get_all_results(session_id)
    if existing:
        await websocket.send_text(json.dumps(
            {"type": "restore", "session_id": session_id, "results": existing},
            ensure_ascii=False
        ))

    try:
        # 클라이언트 메시지 수신 루프 (ping/pong 처리)
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        print(f"[WebSocket] 연결 해제: {session_id}")
    finally:
        conns = _ws_connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)


# ─── 실행 진입점 ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("HR 피드백 보조 AI 서버 시작 중...")
    print("브라우저: http://localhost:8000")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=str(Path(__file__).parent),
    )
