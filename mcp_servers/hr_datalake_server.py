"""
mcp_servers/hr_datalake_server.py - HR DataLake MCP 서버

직원의 업무 활동 데이터를 제공합니다.
메일 제목·요약, Teams 대화 요약, 캘린더 일정 요약을 반환합니다.

제공 도구:
  - get_mail_summary:  이메일 제목 및 요약 목록
  - get_teams_chat:    Teams 채팅 맥락 및 요약
  - get_calendar:      분기별 캘린더 일정 요약
"""

import json
from fastmcp import FastMCP
from config import MOCK_DATA_DIR

mcp = FastMCP("hr-datalake-mcp")


def _load_datalake() -> list:
    """HR DataLake JSON 파일을 로딩합니다."""
    filepath = MOCK_DATA_DIR / "hr_datalake.json"
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_employee_data(emp_id: str, year: int) -> dict | None:
    """직원·연도 기준으로 DataLake 항목을 찾아 반환합니다."""
    data = _load_datalake()
    return next(
        (d for d in data if d["emp_id"] == emp_id and d["year"] == year),
        None
    )


@mcp.tool()
def get_mail_summary(emp_id: str, year: int, limit: int = 10) -> str:
    """
    직원의 주요 이메일 제목 및 요약을 반환합니다.
    업무 활동의 흔적을 파악하는 데 사용됩니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도
        limit:  반환할 최대 건수 (기본 10건)

    Returns:
        JSON 문자열. 월별 이메일 제목·요약 리스트.
    """
    emp_data = _get_employee_data(emp_id, year)

    if not emp_data:
        return json.dumps({"error": f"{emp_id}의 {year}년 메일 데이터가 없습니다."}, ensure_ascii=False)

    mail_summaries = emp_data.get("mail_summaries", [])[:limit]

    result = {
        "emp_id": emp_id,
        "year": year,
        "total_count": len(emp_data.get("mail_summaries", [])),
        "returned_count": len(mail_summaries),
        "mail_summaries": mail_summaries,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_teams_chat(emp_id: str, year: int, limit: int = 10) -> str:
    """
    직원의 Teams 채팅 맥락 및 요약을 반환합니다.
    팀 내 협업 패턴과 기여도를 파악하는 데 사용됩니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도
        limit:  반환할 최대 건수 (기본 10건)

    Returns:
        JSON 문자열. 월별 Teams 채팅 요약 리스트.
    """
    emp_data = _get_employee_data(emp_id, year)

    if not emp_data:
        return json.dumps({"error": f"{emp_id}의 {year}년 Teams 데이터가 없습니다."}, ensure_ascii=False)

    teams_chats = emp_data.get("teams_chats", [])[:limit]

    result = {
        "emp_id": emp_id,
        "year": year,
        "total_count": len(emp_data.get("teams_chats", [])),
        "returned_count": len(teams_chats),
        "teams_chats": teams_chats,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_calendar(emp_id: str, year: int, quarter: str = "all") -> str:
    """
    직원의 분기별 캘린더 일정 요약을 반환합니다.
    미팅 참여도, 활동량, 협업 패턴을 파악하는 데 사용됩니다.

    Args:
        emp_id:   직원 ID
        year:     조회 연도
        quarter:  조회할 분기 ("Q1" | "Q2" | "Q3" | "Q4" | "all", 기본 "all")

    Returns:
        JSON 문자열. 분기별 미팅 목록.
    """
    emp_data = _get_employee_data(emp_id, year)

    if not emp_data:
        return json.dumps({"error": f"{emp_id}의 {year}년 캘린더 데이터가 없습니다."}, ensure_ascii=False)

    calendar = emp_data.get("calendar_summaries", [])

    # 특정 분기만 필터링 (all이면 전체 반환)
    if quarter != "all":
        calendar = [c for c in calendar if c.get("quarter") == quarter]

    result = {
        "emp_id": emp_id,
        "year": year,
        "filter_quarter": quarter,
        "calendar_summaries": calendar,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
