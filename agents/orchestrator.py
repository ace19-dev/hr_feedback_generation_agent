"""
agents/orchestrator.py - 메인 오케스트레이터

4개 서브 에이전트의 실행 흐름을 조율합니다.

실행 순서:
  1. [순차] Agent1 → summary.json 저장
     └─ Agent1 완료 즉시 [병렬 분기] Agent4 시작 (Human Gate와 무관하게 백그라운드 진행)
  2. [순차] Agent2 → draft.json 저장 → human_approval_gate 발동 (WebSocket pause)
            팀장 수정 후 재개 →
  3. [순차] Agent3 (품질 체크 4종은 내부에서 asyncio.gather 병렬 실행)
  4. Agent4 결과를 await하여 수신 후 WebSocket으로 UI에 통지
  5. WebSocket으로 UI에 최종 완료 알림

WebSocket 이벤트 타입:
  - agent_progress:  각 에이전트 시작/완료 알림
  - step_result:     단계별 결과 데이터 전송
  - human_gate:      팀장 검토 요청 (기능2 완료 후)
  - done:            전체 완료 알림
  - error:           오류 발생 알림
"""

import asyncio
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from agents import agent1_summary, agent2_draft, agent3_quality, agent4_comparison
from shared_store import create_session, update_session_status, get_result
from config import HUMAN_GATE_TIMEOUT


# WebSocket 이벤트 전송 콜백 타입
# UI app.py에서 실제 WebSocket 전송 함수를 주입합니다.
NotifyFunc = Callable[[str, str, dict], Awaitable[None]]


async def _notify(notify_func: NotifyFunc, session_id: str, event_type: str, data: dict):
    """
    UI WebSocket으로 이벤트를 전송합니다.
    notify_func이 없으면 콘솔에만 출력합니다. (CLI 모드)
    """
    if notify_func:
        try:
            await notify_func(session_id, event_type, data)
        except Exception as e:
            print(f"[Orchestrator] WebSocket 전송 실패: {e}")
    else:
        # CLI 모드: WebSocket 대신 콘솔 출력
        print(f"[Orchestrator] EVENT({event_type}): {data.get('message', '')}")


async def run_pipeline(
    emp_id: str,
    year: int = 2025,
    notify_func: NotifyFunc = None,
    session_id: str = None,
) -> dict:
    """
    전체 평가 파이프라인을 실행합니다.

    Args:
        emp_id:       평가 대상 직원 ID
        year:         평가 연도 (기본 2025)
        notify_func:  WebSocket 이벤트 전송 콜백 (없으면 CLI 모드)
        session_id:   기존 세션 ID (없으면 새로 생성)

    Returns:
        {
          "session_id": str,
          "summary": dict,
          "draft": dict,
          "quality": dict,
          "comparison": dict,
        }
    """
    # 세션 ID 생성 (없으면 새로 생성)
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    create_session(session_id, emp_id)
    update_session_status(session_id, "running")

    print(f"\n{'='*55}")
    print(f"[Orchestrator] 평가 파이프라인 시작")
    print(f"  직원: {emp_id} / 연도: {year} / 세션: {session_id}")
    print(f"{'='*55}")

    await _notify(notify_func, session_id, "agent_progress", {
        "step": "started",
        "message": f"{emp_id} 평가 파이프라인 시작",
        "session_id": session_id,
    })

    try:
        # ── Step 1: 성과데이터 통합요약 (순차) ────────────────────
        print("\n[Step 1] 성과 데이터 통합 요약...")
        await _notify(notify_func, session_id, "agent_progress", {
            "step": "agent1_start",
            "message": "성과 데이터 수집 및 요약 중...",
        })

        summary = await agent1_summary.run(emp_id, session_id, year)

        await _notify(notify_func, session_id, "step_result", {
            "step": "summary",
            "message": "성과 요약 완료",
            "data": summary,
        })
        print(f"[Step 1] 완료 [OK]")

        # ── Agent4 병렬 분기 ──────────────────────────────────────
        # 기능1 완료 즉시, Human Gate/Agent2/Agent3와 무관하게 백그라운드로 시작합니다.
        print("\n[Agent4] 팀 비교뷰 백그라운드 생성 시작...")
        await _notify(notify_func, session_id, "agent_progress", {
            "step": "agent4_start",
            "message": "팀 비교뷰 생성 중 (백그라운드)...",
        })
        comparison_task = asyncio.create_task(
            agent4_comparison.run(emp_id, session_id, year)
        )

        # ── Step 2: 피드백 초안 생성 (순차) ───────────────────────
        print("\n[Step 2] 피드백 초안 생성...")
        await _notify(notify_func, session_id, "agent_progress", {
            "step": "agent2_start",
            "message": "피드백 초안 생성 중...",
        })

        draft = await agent2_draft.run(emp_id, session_id, year)

        await _notify(notify_func, session_id, "step_result", {
            "step": "draft",
            "message": "피드백 초안 생성 완료 - 검토가 필요합니다",
            "data": draft,
        })
        print(f"[Step 2] 완료 [OK]")

        # ── Human Approval Gate ────────────────────────────────────
        # 팀장이 초안을 검토하고 수정할 때까지 대기합니다.
        # WebSocket으로 "검토 요청" 이벤트를 보내고 asyncio.Event로 대기합니다.
        print("\n[Human Gate] 팀장 검토 대기 중...")
        await _notify(notify_func, session_id, "human_gate", {
            "step": "awaiting_review",
            "message": "초안을 검토하고 '확인' 버튼을 눌러주세요.",
            "timeout_seconds": HUMAN_GATE_TIMEOUT,
        })

        # asyncio.Event를 사용해 팀장 응답을 비동기 대기합니다.
        approval_event = asyncio.Event()
        _approval_events[session_id] = approval_event

        try:
            # 타임아웃: HUMAN_GATE_TIMEOUT초 (기본 30분) 후 자동 진행
            await asyncio.wait_for(approval_event.wait(), timeout=HUMAN_GATE_TIMEOUT)
            print("[Human Gate] 팀장 승인 완료, 다음 단계로 진행합니다.")
        except asyncio.TimeoutError:
            # 타임아웃 시 현재 초안 그대로 진행합니다.
            print("[Human Gate] 타임아웃 - 현재 초안으로 진행합니다.")
            await _notify(notify_func, session_id, "agent_progress", {
                "step": "gate_timeout",
                "message": "검토 시간 초과 - 현재 초안으로 진행합니다.",
            })
        finally:
            _approval_events.pop(session_id, None)

        # ── Step 3: 품질 체크 (내부 4종 체커는 asyncio.gather 병렬) ──
        print("\n[Step 3] 품질 체크 생성...")
        await _notify(notify_func, session_id, "agent_progress", {
            "step": "agent3_start",
            "message": "품질 체크 생성 중...",
        })

        quality = await agent3_quality.run(emp_id, session_id, year)

        await _notify(notify_func, session_id, "step_result", {
            "step": "quality",
            "message": f"품질 체크 완료 (경고 {quality.get('warning_count', 0)}건)",
            "data": quality,
        })
        print(f"[Step 3] 완료 [OK]")

        # ── Agent4 결과 수신 ──────────────────────────────────────
        # Agent1 완료 직후 시작된 비교뷰 생성을 여기서 await합니다.
        # (이미 완료되어 있으면 즉시 반환됩니다)
        comparison = await comparison_task

        await _notify(notify_func, session_id, "step_result", {
            "step": "comparison",
            "message": f"팀 비교표 완료 ({len(comparison.get('members', []))}명)",
            "data": comparison,
        })
        print(f"[Agent4] 팀 비교뷰 완료 [OK]")

        # ── 완료 ────────────────────────────────────────────────
        update_session_status(session_id, "done")
        await _notify(notify_func, session_id, "done", {
            "step": "done",
            "message": "전체 평가 파이프라인 완료",
            "session_id": session_id,
        })

        print(f"\n{'='*55}")
        print(f"[Orchestrator] 파이프라인 완료! 세션: {session_id}")
        print(f"{'='*55}\n")

        return {
            "session_id": session_id,
            "summary": summary,
            "draft": draft,
            "quality": quality,
            "comparison": comparison,
        }

    except Exception as e:
        # 오류 발생 시 세션 상태를 failed로 변경하고 UI에 알립니다.
        update_session_status(session_id, "failed")
        error_msg = f"파이프라인 오류: {str(e)}"
        print(f"[Orchestrator] ERROR: {error_msg}")

        await _notify(notify_func, session_id, "error", {
            "message": error_msg,
            "session_id": session_id,
        })
        raise


# ─── Human Approval Gate 이벤트 저장소 ─────────────────────
# 세션 ID → asyncio.Event 매핑
# WebSocket으로 팀장 승인이 도착하면 해당 이벤트를 set()합니다.
_approval_events: dict[str, asyncio.Event] = {}


def approve_draft(session_id: str, edits: dict = None) -> bool:
    """
    팀장이 초안을 승인(또는 수정 후 승인)하면 호출됩니다.
    WebSocket 핸들러(ui/app.py)에서 이 함수를 호출합니다.

    Args:
        session_id: 세션 ID
        edits:      팀장 수정 내용 (없으면 원본 초안 그대로)

    Returns:
        승인 이벤트가 성공적으로 처리되었으면 True
    """
    from agents.agent2_draft import apply_human_edits

    # 팀장 수정 내용이 있으면 draft를 업데이트합니다.
    if edits:
        apply_human_edits(session_id, edits)

    # 대기 중인 이벤트를 set()하여 파이프라인을 재개합니다.
    event = _approval_events.get(session_id)
    if event:
        event.set()
        print(f"[Orchestrator] Human gate 해제 (session_id={session_id})")
        return True

    print(f"[Orchestrator] 경고: {session_id}의 대기 이벤트가 없습니다.")
    return False


# ─── CLI 모드 진입점 ─────────────────────────────────────────

if __name__ == "__main__":
    """
    CLI에서 직접 실행하는 경우: UI 없이 전체 파이프라인을 테스트합니다.
    사용: python agents/orchestrator.py [emp_id]
    """
    import sys
    import json

    # 평가 대상 직원 (CLI 인수 또는 기본값 E001)
    target_emp = sys.argv[1] if len(sys.argv) > 1 else "E001"
    print(f"CLI 모드: {target_emp} 평가 파이프라인 실행")
    print("(Human Approval Gate는 30초 후 자동으로 통과됩니다)\n")

    # Human Gate를 빠르게 통과시키기 위해 타임아웃을 30초로 재설정합니다.
    import config
    config.HUMAN_GATE_TIMEOUT = 30

    result = asyncio.run(run_pipeline(emp_id=target_emp))

    # 결과를 파일로 저장합니다.
    output_file = f"pipeline_result_{target_emp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장 완료: {output_file}")
