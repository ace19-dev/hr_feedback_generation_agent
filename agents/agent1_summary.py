"""
agents/agent1_summary.py - 기능1: 성과데이터 통합요약 에이전트

직원의 KPI, 1on1 면담, 본인평가, HR DataLake 데이터를 수집하여
연간 성과 요약 JSON을 생성합니다.

처리 흐름:
  1. MCP 도구로 모든 데이터 수집
  2. Claude에게 통합 요약 요청 (tool_use 루프)
  3. summary.json → shared_store 저장
  4. 타임라인 텍스트 → VectorStore 임베딩 저장

Output 스키마 (summary.json):
  {
    "emp_id": str,
    "year": int,
    "timeline": [{"quarter": str, "key_achievements": [...], "discussion_topics": [...]}],
    "achievement_summary": str,   # 업적 영역 종합
    "competency_summary": str,    # 역량 영역 종합
    "key_topics": [...],          # 추출된 키워드/업무 토픽
    "kpi_summary": {...},         # KPI 달성 현황
    "overall_assessment": str,    # 전체 요약 (1~2문장)
  }
"""

import json
import re
import asyncio
import anthropic

from mcp_client import call_mcp_tool
from shared_store import save_result
from config import MODEL, MAX_TOKENS, LLM_TIMEOUT, MOCK_DATA_DIR


# 에이전트1이 사용할 MCP 도구 정의 목록
# Claude가 tool_use 루프에서 이 도구들을 선택해 호출합니다.
TOOLS = [
    {
        "name": "get_kpi_plan",
        "description": "직원의 KPI 계획 및 달성 현황을 반환합니다. 목표 대비 실제 달성값과 가중 달성률을 포함합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string", "description": "직원 ID (예: 'E001')"},
                "year":   {"type": "integer", "description": "조회 연도 (예: 2025)"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "get_1on1_records",
        "description": "직원의 분기별 1on1 면담 이력을 반환합니다. 없는 분기는 quarters_missing 필드로 안내됩니다.",
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
        "name": "get_self_review",
        "description": "직원의 본인평가 전체 내용을 반환합니다. 자기 등급, 강점, 개선 영역, 성장 플랜, 상호 성찰을 포함합니다.",
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
        "name": "get_mail_summary",
        "description": "직원의 주요 이메일 제목 및 요약을 반환합니다. 주요 업무 완료/공유 이벤트를 파악할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string"},
                "year":   {"type": "integer"},
                "limit":  {"type": "integer", "description": "최대 건수 (기본 10)"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "get_calendar",
        "description": "직원의 분기별 캘린더 일정 요약을 반환합니다. 미팅 참여도와 협업 패턴을 파악할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id":   {"type": "string"},
                "year":     {"type": "integer"},
                "quarter":  {"type": "string", "description": "분기 ('Q1'~'Q4' 또는 'all', 기본 'all')"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "embed_text",
        "description": "텍스트를 임베딩하여 VectorStore에 저장합니다. 타임라인 요약을 저장해 나중에 유사도 검색에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":       {"type": "string", "description": "임베딩할 텍스트"},
                "doc_id":     {"type": "string", "description": "문서 고유 ID"},
                "collection": {"type": "string", "description": "컬렉션 이름"},
                "metadata":   {"type": "string", "description": "JSON 문자열 형태의 메타데이터"}
            },
            "required": ["text", "doc_id"]
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
    성과데이터 통합요약 에이전트를 실행합니다.

    Args:
        emp_id:     평가 대상 직원 ID
        session_id: 현재 세션 ID (결과 저장에 사용)
        year:       평가 연도 (기본 2025)

    Returns:
        생성된 summary 딕셔너리
    """
    client = anthropic.Anthropic()
    emp_name = _get_employee_name(emp_id)

    # 시스템 프롬프트: 에이전트의 역할과 출력 형식을 지시합니다.
    system_prompt = f"""당신은 HR 성과 데이터 분석 전문가입니다.
주어진 MCP 도구를 활용해 직원의 연간 성과 데이터를 수집하고 통합 요약을 작성하세요.

반드시 아래 JSON 형식으로 최종 결과를 반환하세요:
{{
  "emp_id": "직원ID",
  "year": 연도,
  "timeline": [
    {{
      "quarter": "Q1",
      "key_achievements": ["성과1", "성과2"],
      "discussion_topics": ["면담에서 논의된 주제"],
      "kpi_status": "달성/진행중/미달"
    }}
  ],
  "achievement_summary": "업적 영역 종합 요약 (2~3문장, 수치 포함)",
  "competency_summary": "역량 영역 종합 요약 (2~3문장, 행동 사례 기반)",
  "key_topics": ["키워드1", "키워드2", ...],
  "kpi_summary": {{
    "weighted_achievement_rate": 수치,
    "highlights": ["뛰어난 KPI 항목"],
    "concerns": ["미달 KPI 항목"]
  }},
  "overall_assessment": "1~2문장 전체 요약"
}}

1on1 기록이 없는 분기는 timeline에 quarters_missing 정보와 함께 '기록 없음'으로 표시하세요.
achievement_summary, competency_summary, overall_assessment 텍스트에서 직원을 지칭할 때는
직원 ID("{emp_id}")가 아닌 이름("{emp_name}")을 사용하세요.
JSON 형식 이외의 텍스트 없이 JSON만 반환하세요."""

    messages = [
        {
            "role": "user",
            "content": f"직원 {emp_id}({emp_name})의 {year}년 성과 데이터를 수집하고 통합 요약을 생성해주세요. "
                       f"KPI 계획, 1on1 면담 이력(Q1~Q4), 본인평가, 메일 요약, 캘린더를 모두 조회하세요. "
                       f"수집 완료 후 타임라인 요약 텍스트를 VectorStore에 저장(collection='timelines')하세요."
        }
    ]

    print(f"[Agent1] {emp_id} 성과 요약 시작...")

    # tool_use 루프: Claude가 도구 호출을 완료할 때까지 반복합니다.
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

        # Claude가 더 이상 도구를 호출하지 않으면 루프 종료
        if response.stop_reason == "end_turn":
            break

        # 도구 호출 블록을 수집합니다.
        tool_results = []
        has_tool_use = False

        for block in response.content:
            if block.type == "tool_use":
                has_tool_use = True
                print(f"[Agent1] 도구 호출: {block.name}({block.input})")

                # MCP 도구를 실제로 호출합니다.
                try:
                    result = await call_mcp_tool(block.name, block.input)
                    result_text = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
                except Exception as e:
                    result_text = json.dumps({"error": str(e)}, ensure_ascii=False)
                    print(f"[Agent1] 도구 호출 실패: {block.name} - {e}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text
                })

        # 도구 호출이 없으면 루프 종료 (예외적 stop_reason 처리)
        if not has_tool_use:
            break

        # 대화 이력에 어시스턴트 응답과 도구 결과를 추가합니다.
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # 최종 응답 텍스트에서 JSON을 파싱합니다.
    summary = _parse_json_response(response)
    summary["emp_id"] = emp_id
    summary["year"] = year

    # 결과를 공유 저장소에 저장합니다.
    save_result(session_id, "summary", summary)
    print(f"[Agent1] {emp_id} 요약 완료 → shared_store 저장")

    return summary


def _parse_json_response(response: anthropic.types.Message) -> dict:
    """
    Claude 응답에서 JSON 텍스트를 추출하고 파싱합니다.
    파싱 실패 시 원본 텍스트를 그대로 저장합니다.
    """
    # 응답 content 블록에서 텍스트 블록을 찾습니다.
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
                # JSON 파싱 실패 시 원본 텍스트를 담아서 반환합니다.
                return {"raw_response": text, "parse_error": True}

    return {"error": "응답에 텍스트 블록이 없습니다."}
