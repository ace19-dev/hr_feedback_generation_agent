"""
agents/agent3_quality.py - 기능3: 피드백 품질 체크 에이전트

팀장이 확인/수정한 피드백 초안에 대해 4종 품질 검사를 수행합니다.
4개 체커는 asyncio.gather로 병렬 실행됩니다.

체커 목록:
  1. detect_recency_bias     - 특정 분기 편중 감지 (임베딩 유사도 기반)
  2. validate_grade_comment  - 등급-코멘트 불일치 감지 (RAG 등급 기준 활용)
  3. check_omission          - 면담 주요 업무 누락 감지
  4. detect_wrong_person     - 타 팀원 업무 혼재 감지

Output 스키마 (quality_check.json):
  {
    "emp_id": str,
    "overall_passed": bool,
    "checkers": {
      "recency_bias":    {"passed": bool, "severity": str, "message": str, "details": str},
      "grade_comment":   {"passed": bool, "severity": str, "message": str, "details": str},
      "omission":        {"passed": bool, "severity": str, "message": str, "details": str},
      "wrong_person":    {"passed": bool, "severity": str, "message": str, "details": str},
    },
    "warnings": [str, ...],   # severity가 warning 이상인 메시지 모음
    "suggestions": [str, ...] # 개선 제안 메시지 모음
  }
"""

import json
import re
import asyncio
import anthropic

from mcp_client import call_mcp_tool
from shared_store import get_result, save_result, format_emp_references_deep
from config import MODEL, MAX_TOKENS, LLM_TIMEOUT


async def _call_claude(
    system_prompt: str,
    user_message: str,
    tools: list
) -> dict:
    """
    공통 tool_use 루프 헬퍼.
    system_prompt와 user_message로 Claude를 호출하고 최종 JSON 결과를 반환합니다.
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=tools,
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

    # 최종 응답에서 JSON 파싱
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
                return {"passed": False, "severity": "error", "message": "결과 파싱 실패", "details": text}

    return {"passed": True, "severity": "info", "message": "체크 완료", "details": ""}


# ─── 체커 1: 근시성 편향 감지 ────────────────────────────────

async def detect_recency_bias(draft: dict, summary: dict) -> dict:
    """
    피드백 코멘트가 특정 분기에만 편중되는지 감지합니다.
    임베딩 유사도로 코멘트 내용이 어느 분기와 가장 유사한지 분석합니다.
    """
    tools = [
        {
            "name": "embed_text",
            "description": "텍스트를 임베딩하여 VectorStore에 저장합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "doc_id": {"type": "string"},
                    "collection": {"type": "string"},
                    "metadata": {"type": "string"}
                },
                "required": ["text", "doc_id"]
            }
        },
        {
            "name": "similarity_search",
            "description": "VectorStore에서 유사한 텍스트를 검색합니다.",
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
        }
    ]

    system = """당신은 HR 피드백 편향 감지 전문가입니다.
피드백 코멘트와 분기별 타임라인 데이터를 분석하여 근시성 편향(특정 분기 편중)이 있는지 확인하세요.

반드시 아래 JSON 형식으로 반환하세요:
{
  "passed": true/false,
  "severity": "ok" / "warning" / "critical",
  "message": "체크 결과 한 줄 요약",
  "details": "상세 설명",
  "quarterly_coverage": {"Q1": 언급횟수, "Q2": 언급횟수, "Q3": 언급횟수, "Q4": 언급횟수},
  "suggestion": "개선 제안 (passed=false일 때만)"
}"""

    user_msg = (
        f"피드백 코멘트:\n{draft.get('achievement_feedback', '')}\n{draft.get('competency_feedback', '')}\n\n"
        f"분기별 타임라인:\n{json.dumps(summary.get('timeline', []), ensure_ascii=False)}\n\n"
        f"타임라인 데이터를 VectorStore(collection='timelines')에 저장하고, "
        f"피드백 코멘트와 각 분기 타임라인의 유사도를 분석해 편향 여부를 판단하세요."
    )

    return await _call_claude(system, user_msg, tools)


# ─── 체커 2: 등급-코멘트 불일치 감지 ───────────────────────

async def validate_grade_comment(draft: dict) -> dict:
    """
    추천 등급과 코멘트 내용이 일치하는지 확인합니다.
    S등급인데 코멘트가 주로 부정적이거나, B등급인데 내용이 없는 경우를 감지합니다.
    RAG에서 등급 기준 가이드라인을 참조합니다.
    """
    tools = [
        {
            "name": "retrieve_grade_criteria",
            "description": "등급 기준 가이드라인에서 관련 내용을 검색합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query":     {"type": "string"},
                    "n_results": {"type": "integer"}
                },
                "required": ["query"]
            }
        }
    ]

    system = """당신은 HR 평가 품질 검증 전문가입니다.
피드백 초안의 추천 등급과 코멘트 내용이 등급 기준 가이드라인에 부합하는지 확인하세요.

반드시 아래 JSON 형식으로 반환하세요:
{
  "passed": true/false,
  "severity": "ok" / "warning" / "critical",
  "message": "체크 결과 한 줄 요약",
  "details": "상세 설명",
  "positive_ratio": 0.0~1.0,
  "grade_consistency": "consistent" / "inconsistent",
  "suggestion": "개선 제안 (passed=false일 때만)"
}"""

    grade = draft.get("suggested_grade", "")
    user_msg = (
        f"추천 등급: {grade}\n"
        f"업적 피드백: {draft.get('achievement_feedback', '')}\n"
        f"역량 피드백: {draft.get('competency_feedback', '')}\n"
        f"등급 근거: {draft.get('grade_rationale', '')}\n\n"
        f"RAG에서 '{grade}등급 피드백 기준'을 조회하여 코멘트 내용이 등급에 적절한지 판단하세요."
    )

    return await _call_claude(system, user_msg, tools)


# ─── 체커 3: 면담 내용 누락 감지 ──────────────────────────

async def check_omission(draft: dict, summary: dict, emp_id: str, year: int) -> dict:
    """
    1on1 면담에서 중요하게 다뤄진 주제가 피드백에 누락되었는지 확인합니다.
    """
    tools = [
        {
            "name": "get_1on1_records",
            "description": "직원의 분기별 1on1 면담 이력을 반환합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "emp_id": {"type": "string"},
                    "year": {"type": "integer"}
                },
                "required": ["emp_id", "year"]
            }
        }
    ]

    system = """당신은 HR 피드백 완결성 검증 전문가입니다.
1on1 면담 기록에서 팀장이 강조한 주요 업무/주제가 피드백 초안에 포함되었는지 확인하세요.

반드시 아래 JSON 형식으로 반환하세요:
{
  "passed": true/false,
  "severity": "ok" / "warning" / "critical",
  "message": "체크 결과 한 줄 요약",
  "details": "상세 설명",
  "omitted_topics": ["누락된 주제1", "누락된 주제2"],
  "covered_topics": ["포함된 주제1"],
  "suggestion": "개선 제안 (passed=false일 때만)"
}"""

    user_msg = (
        f"{emp_id}의 {year}년 1on1 면담 기록을 조회하고, "
        f"다음 피드백 초안에 면담에서 중요하게 언급된 주제들이 포함되었는지 확인하세요.\n\n"
        f"업적 피드백: {draft.get('achievement_feedback', '')}\n"
        f"역량 피드백: {draft.get('competency_feedback', '')}\n"
        f"성장 기회: {json.dumps(draft.get('growth_areas', []), ensure_ascii=False)}"
    )

    return await _call_claude(system, user_msg, tools)


# ─── 체커 4: 타인 업무 혼재 감지 ──────────────────────────

async def detect_wrong_person(draft: dict, emp_id: str, year: int) -> dict:
    """
    피드백에 다른 팀원의 업무가 잘못 기재되었는지 확인합니다.
    VectorStore에서 각 팀원 타임라인과 유사도를 비교합니다.
    """
    tools = [
        {
            "name": "similarity_search",
            "description": "VectorStore에서 유사한 텍스트를 검색합니다.",
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
            "name": "get_kpi_plan",
            "description": "직원의 KPI 계획을 반환합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "emp_id": {"type": "string"},
                    "year": {"type": "integer"}
                },
                "required": ["emp_id", "year"]
            }
        }
    ]

    system = """당신은 HR 피드백 정확성 검증 전문가입니다.
피드백 내용이 해당 직원의 실제 업무와 일치하는지, 다른 팀원의 업무가 혼재되지 않았는지 확인하세요.

반드시 아래 JSON 형식으로 반환하세요:
{
  "passed": true/false,
  "severity": "ok" / "warning" / "critical",
  "message": "체크 결과 한 줄 요약",
  "details": "상세 설명",
  "suspicious_content": ["의심스러운 내용1"],
  "likely_owner": "실제 업무 주인 추정 (있는 경우)",
  "suggestion": "개선 제안 (passed=false일 때만)"
}"""

    user_msg = (
        f"직원 {emp_id}의 KPI 계획을 조회하고, "
        f"VectorStore(collection='timelines')에서 이 피드백과 가장 유사한 타임라인을 검색하세요. "
        f"가장 유사한 것이 {emp_id} 본인이 아닌 다른 직원이면 혼재 오류로 판단하세요.\n\n"
        f"검증할 피드백:\n"
        f"업적: {draft.get('achievement_feedback', '')}\n"
        f"역량: {draft.get('competency_feedback', '')}"
    )

    return await _call_claude(system, user_msg, tools)


# ─── 메인 실행 함수 ──────────────────────────────────────

async def run(emp_id: str, session_id: str, year: int = 2025) -> dict:
    """
    4종 품질 체커를 병렬로 실행합니다.

    Args:
        emp_id:     평가 대상 직원 ID
        session_id: 현재 세션 ID
        year:       평가 연도

    Returns:
        quality_check 딕셔너리
    """
    draft = get_result(session_id, "draft")
    summary = get_result(session_id, "summary")

    if not draft or not summary:
        raise RuntimeError(f"[Agent3] draft 또는 summary 데이터가 없습니다. (session_id={session_id})")

    print(f"[Agent3] {emp_id} 품질 체크 시작 (4개 체커 병렬 실행)...")

    # 4개 체커를 asyncio.gather로 동시에 실행합니다.
    # 각 체커는 독립적이므로 순서에 관계없이 병렬 처리가 가능합니다.
    results = await asyncio.gather(
        detect_recency_bias(draft, summary),
        validate_grade_comment(draft),
        check_omission(draft, summary, emp_id, year),
        detect_wrong_person(draft, emp_id, year),
        return_exceptions=True  # 하나가 실패해도 나머지는 계속 진행
    )

    # gather 결과를 이름 있는 딕셔너리로 변환합니다.
    checker_names = ["recency_bias", "grade_comment", "omission", "wrong_person"]
    checkers = {}
    warnings = []
    suggestions = []

    for name, result in zip(checker_names, results):
        if isinstance(result, Exception):
            # 체커 실행 중 예외 발생 시 오류 정보를 저장합니다.
            checkers[name] = {
                "passed": False,
                "severity": "error",
                "message": f"체커 실행 오류: {str(result)}",
                "details": ""
            }
            warnings.append(f"[{name}] 체커 실행 오류 - 수동 확인 필요")
        else:
            checkers[name] = result
            severity = result.get("severity", "ok")
            if severity in ("warning", "critical"):
                warnings.append(f"[{name}] {result.get('message', '')}")
            if result.get("suggestion"):
                suggestions.append(f"[{name}] {result['suggestion']}")

    # 전체 통과 여부: 모든 체커가 passed=True이어야 함
    overall_passed = all(
        c.get("passed", False) for c in checkers.values()
        if not isinstance(c, Exception)
    )

    quality_check = {
        "emp_id": emp_id,
        "year": year,
        "overall_passed": overall_passed,
        "checkers": checkers,
        "warnings": warnings,
        "suggestions": suggestions,
        "warning_count": len(warnings),
    }

    quality_check = format_emp_references_deep(quality_check)
    save_result(session_id, "quality", quality_check)
    status = "통과" if overall_passed else f"경고 {len(warnings)}건"
    print(f"[Agent3] {emp_id} 품질 체크 완료 → {status}")

    return quality_check
