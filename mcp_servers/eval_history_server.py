"""
mcp_servers/eval_history_server.py - 평가 이력 MCP 서버

직원의 과거 평가 등급, 코멘트, 피드백을 제공합니다.
기능2(피드백 초안 생성)에서 과거 피드백 패턴을 참고할 때 사용됩니다.

제공 도구:
  - get_eval_grade:    과거 평가 등급 (업적/역량 등급 포함)
  - get_eval_comment:  과거 팀장 코멘트
  - get_past_feedback: 과거 평가 전체 (등급 + 코멘트 통합)
"""

import json
from fastmcp import FastMCP
from config import MOCK_DATA_DIR

mcp = FastMCP("eval-history-mcp")


def _load_eval_history() -> list:
    """평가 이력 JSON 파일을 로딩합니다."""
    filepath = MOCK_DATA_DIR / "eval_history.json"
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def get_eval_grade(emp_id: str, year: int) -> str:
    """
    직원의 특정 연도 평가 등급을 반환합니다.
    종합 등급, 업적 등급, 역량 등급, 팀 내 순위를 포함합니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도 (예: 2024 → 전년도 평가)

    Returns:
        JSON 문자열. 등급 정보.
    """
    history = _load_eval_history()

    record = next(
        (h for h in history if h["emp_id"] == emp_id and h["year"] == year),
        None
    )

    if not record:
        return json.dumps(
            {"error": f"{emp_id}의 {year}년 평가 등급 데이터가 없습니다.", "emp_id": emp_id, "year": year},
            ensure_ascii=False
        )

    # 등급 관련 필드만 선택해서 반환합니다.
    result = {
        "emp_id": record["emp_id"],
        "year": record["year"],
        "grade": record["grade"],
        "achievement_grade": record.get("achievement_grade"),
        "competency_grade": record.get("competency_grade"),
        "rank_in_team": record.get("rank_in_team"),
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_eval_comment(emp_id: str, year: int) -> str:
    """
    직원의 특정 연도 팀장 평가 코멘트를 반환합니다.
    피드백 초안 작성 시 전년도 표현 스타일과 키워드를 참고하는 데 사용됩니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도

    Returns:
        JSON 문자열. 팀장 코멘트와 강점/개선 키워드.
    """
    history = _load_eval_history()

    record = next(
        (h for h in history if h["emp_id"] == emp_id and h["year"] == year),
        None
    )

    if not record:
        return json.dumps(
            {"error": f"{emp_id}의 {year}년 코멘트 데이터가 없습니다.", "emp_id": emp_id, "year": year},
            ensure_ascii=False
        )

    result = {
        "emp_id": record["emp_id"],
        "year": record["year"],
        "manager_comment": record.get("manager_comment", ""),
        "strength_keywords": record.get("strength_keywords", []),
        "improvement_keywords": record.get("improvement_keywords", []),
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_past_feedback(emp_id: str, years: int = 2) -> str:
    """
    직원의 과거 N년치 평가 데이터 전체를 반환합니다.
    등급 추이, 강점/개선점 변화 흐름을 파악하는 데 사용됩니다.

    Args:
        emp_id: 직원 ID
        years:  조회할 연도 수 (기본 2 → 가장 최근 2개 연도)

    Returns:
        JSON 문자열. 연도별 평가 전체 리스트 (최신순).
    """
    history = _load_eval_history()

    # 해당 직원의 모든 평가 이력을 최신 연도순으로 정렬
    emp_history = sorted(
        [h for h in history if h["emp_id"] == emp_id],
        key=lambda x: x["year"],
        reverse=True  # 최신 연도 먼저
    )

    # 요청한 연도 수만큼 잘라냅니다.
    limited_history = emp_history[:years]

    result = {
        "emp_id": emp_id,
        "requested_years": years,
        "returned_count": len(limited_history),
        "feedback_history": limited_history,
        # 등급 추이를 한눈에 볼 수 있도록 요약 추가
        "grade_trend": [
            {"year": h["year"], "grade": h["grade"]}
            for h in limited_history
        ],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
