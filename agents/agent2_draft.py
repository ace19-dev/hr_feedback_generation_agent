"""
agents/agent2_draft.py - 기능2: 피드백 초안 생성 에이전트

기능1의 성과 요약 결과와 과거 평가 이력을 바탕으로
업적/역량 피드백 초안을 생성합니다.
초안 생성 후 팀장 검토를 위해 human_approval_gate를 발동합니다.

처리 흐름:
  1. shared_store에서 summary 로딩
  2. 과거 평가 이력 조회 (MCP)
  3. 유사 피드백 검색 (VectorStore)
  4. Claude에게 초안 생성 요청
  5. draft.json → shared_store 저장
  6. human_approval_gate 발동 (WebSocket으로 팀장 UI에 알림)

Output 스키마 (draft.json):
  {
    "emp_id": str,
    "year": int,
    "achievement_feedback": str,  # 업적 피드백 초안
    "competency_feedback": str,   # 역량 피드백 초안
    "strengths": [str, ...],      # 강점 목록
    "growth_areas": [str, ...],   # 성장 기회 목록
    "suggested_grade": str,       # 추천 등급
    "grade_rationale": str,       # 등급 근거
  }
"""

import json
import re
import asyncio
import anthropic

from mcp_client import call_mcp_tool
from shared_store import get_result, save_result, update_session_status
from config import MODEL, MAX_TOKENS, LLM_TIMEOUT, MOCK_DATA_DIR


TOOLS = [
    {
        "name": "get_past_feedback",
        "description": "직원의 과거 N년치 평가 이력(등급, 코멘트, 키워드)을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string"},
                "years":  {"type": "integer", "description": "조회할 연도 수 (기본 2)"}
            },
            "required": ["emp_id"]
        }
    },
    {
        "name": "get_eval_grade",
        "description": "직원의 특정 연도 평가 등급(종합/업적/역량)을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string"},
                "year":   {"type": "integer"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "similarity_search",
        "description": "VectorStore에서 쿼리와 유사한 텍스트를 검색합니다. 유사 피드백 예시나 타임라인 검색에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":           {"type": "string", "description": "검색 쿼리"},
                "collection":      {"type": "string", "description": "컬렉션 이름"},
                "n_results":       {"type": "integer", "description": "반환할 결과 수 (기본 5)"},
                "filter_metadata": {"type": "string", "description": "JSON 문자열 형태의 메타데이터 필터"}
            },
            "required": ["query", "collection"]
        }
    },
    {
        "name": "retrieve_guideline",
        "description": "피드백 작성 가이드라인에서 관련 내용을 검색합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string"},
                "n_results": {"type": "integer", "description": "반환할 청크 수 (기본 3)"}
            },
            "required": ["query"]
        }
    },
]


def _get_employee_name(emp_id: str) -> str:
    """employees.json에서 직원 이름을 조회합니다. 없으면 emp_id를 그대로 반환합니다."""
    filepath = MOCK_DATA_DIR / "employees.json"
    if not filepath.exists():
        return emp_id
    with open(filepath, "r", encoding="utf-8") as f:
        employees = json.load(f)
    for emp in employees:
        if emp.get("emp_id") == emp_id:
            return emp.get("name", emp_id)
    return emp_id


async def run(emp_id: str, session_id: str, year: int = 2025) -> dict:
    """
    피드백 초안 생성 에이전트를 실행합니다.

    Args:
        emp_id:     평가 대상 직원 ID
        session_id: 현재 세션 ID
        year:       평가 연도

    Returns:
        생성된 draft 딕셔너리
    """
    # 기능1 결과를 shared_store에서 로딩합니다.
    summary = get_result(session_id, "summary")
    if not summary:
        raise RuntimeError(f"[Agent2] summary 데이터가 없습니다. Agent1을 먼저 실행하세요. (session_id={session_id})")

    client = anthropic.Anthropic()
    emp_name = _get_employee_name(emp_id)

    system_prompt = f"""당신은 HR 피드백 초안 작성 전문가입니다.
제공된 성과 요약과 MCP 도구로 조회한 과거 평가 이력을 바탕으로
업적/역량 피드백 초안을 작성하세요.

반드시 아래 JSON 형식으로 최종 결과를 반환하세요:
{{
  "emp_id": "직원ID",
  "year": 연도,
  "achievement_feedback": "업적 피드백 초안 (구체적 수치와 성과 포함, 200자 이상)",
  "competency_feedback": "역량 피드백 초안 (행동 사례 기반, 150자 이상)",
  "strengths": ["강점1", "강점2", "강점3"],
  "growth_areas": ["성장 기회1", "성장 기회2"],
  "suggested_grade": "등급 (S/A+/A/B+/B/C 중 하나)",
  "grade_rationale": "이 등급을 추천하는 이유 (1~2문장)"
}}

작성 원칙:
- 업적 피드백: KPI 수치 기반, 연간 전체를 균형 있게 반영
- 역량 피드백: 1on1 면담에서 관찰된 행동 사례 기반
- 강점: 가장 두드러진 강점 2~3개
- 성장 기회: '~이 부족하다'가 아닌 '~을 더 발전시킬 기회가 있다' 관점
- 등급 추천: KPI 달성률과 1on1 기록을 종합적으로 판단
achievement_feedback, competency_feedback, grade_rationale 텍스트에서 직원을 지칭할 때는
직원 ID("{emp_id}")가 아닌 이름("{emp_name}")을 사용하세요.
JSON 형식 이외의 텍스트 없이 JSON만 반환하세요."""

    messages = [
        {
            "role": "user",
            "content": (
                f"다음은 {emp_id}({emp_name})의 {year}년 성과 요약입니다:\n"
                f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
                f"이 데이터와 MCP 도구(과거 평가 이력 조회, 피드백 가이드라인 참조)를 활용해 "
                f"피드백 초안을 작성해주세요. "
                f"전년도({year-1}년) 평가 이력도 반드시 조회하세요."
            )
        }
    ]

    print(f"[Agent2] {emp_id} 피드백 초안 생성 시작...")

    # tool_use 루프
    while True:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            ),
            timeout=LLM_TIMEOUT
        )

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        has_tool_use = False

        for block in response.content:
            if block.type == "tool_use":
                has_tool_use = True
                print(f"[Agent2] 도구 호출: {block.name}({block.input})")

                try:
                    result = await call_mcp_tool(block.name, block.input)
                    result_text = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
                except Exception as e:
                    result_text = json.dumps({"error": str(e)}, ensure_ascii=False)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text
                })

        if not has_tool_use:
            break

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    draft = _parse_json_response(response)
    draft["emp_id"] = emp_id
    draft["year"] = year
    draft["status"] = "pending_review"  # 팀장 검토 대기 상태

    # 결과를 저장하고 세션 상태를 "팀장 검토 대기"로 변경합니다.
    save_result(session_id, "draft", draft)
    update_session_status(session_id, "awaiting_human")
    print(f"[Agent2] {emp_id} 초안 완료 → human_approval_gate 발동")

    return draft


def apply_human_edits(session_id: str, edits: dict) -> dict:
    """
    팀장이 초안을 수정한 내용을 저장합니다.
    Orchestrator가 WebSocket으로 수정 내용을 받으면 이 함수를 호출합니다.

    Args:
        session_id: 세션 ID
        edits: 수정된 필드 딕셔너리 (예: {"achievement_feedback": "수정된 텍스트"})

    Returns:
        수정이 반영된 draft 딕셔너리
    """
    # 기존 초안을 로딩합니다.
    draft = get_result(session_id, "draft") or {}

    # 팀장 수정 내용을 덮어씁니다.
    draft.update(edits)
    draft["status"] = "approved"
    draft["human_edited"] = True

    # 수정된 초안을 저장합니다.
    save_result(session_id, "draft", draft)
    update_session_status(session_id, "running")  # 품질 체크 단계로 계속 진행
    print(f"[Agent2] 팀장 수정 적용 완료 (session_id={session_id})")

    return draft


def _parse_json_response(response: anthropic.types.Message) -> dict:
    """Claude 응답에서 JSON을 파싱합니다."""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text.strip()
            # JSON 코드 블록을 추출합니다 (앞에 설명 텍스트가 붙어있어도 추출 가능)
            fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
            if fence_match:
                text = fence_match.group(1).strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_response": text, "parse_error": True}

    return {"error": "응답에 텍스트 블록이 없습니다."}
