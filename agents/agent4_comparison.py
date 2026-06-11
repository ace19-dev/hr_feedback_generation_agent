"""
agents/agent4_comparison.py - 기능4: 상위평가자 비교뷰 에이전트

기능1(성과 요약) 완료 시점에 병렬로 시작됩니다.
팀 전체 구성원의 성과 요약을 수집하여 실장/본부장용 비교표를 생성합니다.

처리 흐름:
  1. 팀 전체 직원 목록 조회
  2. 각 직원의 summary (shared_store 또는 VectorStore에서) 수집
  3. Claude에게 비교표 생성 요청
  4. comparison_table.json → shared_store 저장

Output 스키마 (comparison_table.json):
  {
    "session_id": str,
    "year": int,
    "generated_at": str,
    "members": [
      {
        "emp_id": str,
        "name": str,
        "role": str,
        "level": str,
        "one_line_summary": str,    # 업무 핵심 1줄 요약
        "top_achievement": str,     # 가장 중요한 성과
        "suggested_grade": str,     # 기능2 초안의 추천 등급 (없으면 추정)
        "kpi_achievement_rate": float,
      }
    ],
    "team_highlights": str,         # 팀 전체 특이사항
  }
"""

import json
import re
import asyncio
import anthropic
from datetime import datetime

from mcp_client import call_mcp_tool
from shared_store import get_result, save_result, format_emp_references_deep
from config import MODEL, MAX_TOKENS, LLM_TIMEOUT, MOCK_DATA_DIR


TOOLS = [
    {
        "name": "get_kpi_plan",
        "description": "직원의 KPI 계획 및 달성 현황을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string"},
                "year": {"type": "integer"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "get_self_review",
        "description": "직원의 본인평가 전체 내용을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "emp_id": {"type": "string"},
                "year": {"type": "integer"}
            },
            "required": ["emp_id", "year"]
        }
    },
    {
        "name": "similarity_search",
        "description": "VectorStore에서 직원의 타임라인 요약을 검색합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "collection": {"type": "string"},
                "n_results": {"type": "integer"},
                "filter_metadata": {"type": "string"}
            },
            "required": ["query", "collection"]
        }
    },
    {
        "name": "retrieve_guideline",
        "description": "피드백 가이드라인에서 비교표 작성 기준을 검색합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "n_results": {"type": "integer"}
            },
            "required": ["query"]
        }
    },
]


def _load_all_employees() -> list[dict]:
    """목데이터에서 팀원 목록을 로딩합니다. (팀장 제외)"""
    filepath = MOCK_DATA_DIR / "employees.json"
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        employees = json.load(f)
    # 팀장(is_manager=True)은 비교 대상에서 제외
    return [e for e in employees if not e.get("is_manager", False)]


def _collect_member_summaries(session_id: str, all_emp_ids: list[str]) -> list[dict]:
    """
    가능한 모든 직원의 요약 데이터를 수집합니다.
    shared_store에 있으면 그것을 사용하고, 없으면 빈 딕셔너리를 반환합니다.
    실제 서비스에서는 각 직원의 세션 summary를 별도 API로 조회하지만,
    여기서는 단일 세션 기준으로 처리합니다.
    """
    summaries = {}
    for emp_id in all_emp_ids:
        summary = get_result(session_id, "summary")
        if summary and summary.get("emp_id") == emp_id:
            summaries[emp_id] = summary
    return summaries


async def run(emp_id: str, session_id: str, year: int = 2025) -> dict:
    """
    팀 전체 비교뷰 생성 에이전트를 실행합니다.
    기능1 완료 즉시 병렬로 실행됩니다.

    Args:
        emp_id:     현재 평가 대상 직원 ID (비교뷰의 중심 인물)
        session_id: 현재 세션 ID
        year:       평가 연도

    Returns:
        comparison_table 딕셔너리
    """
    client = anthropic.Anthropic()

    # 팀원 목록 로딩
    all_members = _load_all_employees()
    all_emp_ids = [m["emp_id"] for m in all_members]
    member_info_map = {m["emp_id"]: m for m in all_members}

    print(f"[Agent4] 팀 비교뷰 생성 시작 (총 {len(all_members)}명)...")

    system_prompt = f"""당신은 HR 성과 비교 분석 전문가입니다.
팀 전체 구성원의 성과 데이터를 수집하여 실장/본부장용 비교표를 생성하세요.
각 팀원의 KPI와 자기평가를 조회하여 핵심 성과를 1~2줄로 요약합니다.

대상 팀원 목록: {json.dumps(all_emp_ids)}
평가 연도: {year}

반드시 아래 JSON 형식으로 최종 결과를 반환하세요:
{{
  "year": {year},
  "generated_at": "현재 시각 ISO 형식",
  "members": [
    {{
      "emp_id": "직원ID",
      "name": "이름",
      "role": "직책",
      "level": "직급",
      "one_line_summary": "핵심 업무 1줄 (40자 이내)",
      "top_achievement": "올해 가장 중요한 성과 (2~3문장, 수치 포함)",
      "kpi_achievement_rate": 가중달성률(숫자),
      "notable_contribution": "팀/조직 기여 내용"
    }}
  ],
  "team_highlights": "팀 전체 관점에서의 주요 특이사항 (2~3문장)"
}}

모든 팀원({', '.join(all_emp_ids)})의 KPI와 자기평가를 각각 조회하세요.
JSON 형식 이외의 텍스트 없이 JSON만 반환하세요."""

    messages = [
        {
            "role": "user",
            "content": (
                f"팀 전체 {len(all_members)}명의 {year}년 성과 비교표를 생성해주세요. "
                f"각 팀원의 KPI 달성률과 자기평가를 조회하여 핵심 성과를 요약하세요."
            )
        }
    ]

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
                print(f"[Agent4] 도구 호출: {block.name}({block.input.get('emp_id', '')})")

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

    comparison = _parse_json_response(response)

    # 직원 기본정보(name, role, level)는 employees.json을 신뢰 소스로 사용해 덮어씁니다.
    # (LLM이 생성한 이름이 실제 mock 데이터와 다를 수 있음)
    for member in comparison.get("members", []):
        eid = member.get("emp_id")
        if eid in member_info_map:
            member["name"] = member_info_map[eid]["name"]
            member["role"] = member_info_map[eid]["role"]
            member["level"] = member_info_map[eid]["level"]

    comparison["session_id"] = session_id
    comparison.setdefault("generated_at", datetime.now().isoformat())

    comparison = format_emp_references_deep(comparison)
    save_result(session_id, "comparison", comparison)
    print(f"[Agent4] 팀 비교표 완료 ({len(comparison.get('members', []))}명)")

    return comparison


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
                return {"raw_response": text, "parse_error": True, "members": []}

    return {"error": "응답 없음", "members": []}
