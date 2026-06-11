"""
mcp_servers/hihr_server.py - hiHR MCP 서버

직원의 1on1 면담 이력, 성장플랜, 본인평가, KPI 계획을 제공합니다.
data/mock/ 디렉터리의 JSON 파일을 읽어 반환합니다.

제공 도구:
  - get_1on1_records: 분기별 1on1 면담 이력
  - get_growth_plan:  성장플랜 (자기평가 내 growth_plan 필드)
  - get_self_review:  본인평가 전체
  - get_kpi_plan:     KPI 및 연간업무계획
"""

import json
from fastmcp import FastMCP
from config import MOCK_DATA_DIR

# FastMCP 서버 인스턴스 생성
# 이 변수(mcp)를 mcp_client.py에서 인프로세스 Client로 연결합니다.
mcp = FastMCP("hihr-mcp")


def _load_json(filename: str) -> list:
    """JSON 목데이터 파일을 로딩합니다. 파일이 없으면 빈 리스트를 반환합니다."""
    filepath = MOCK_DATA_DIR / filename
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def get_1on1_records(emp_id: str, year: int) -> str:
    """
    직원의 분기별 1on1 면담 이력을 반환합니다.

    1on1 기록이 없는 분기는 결과에 포함되지 않습니다.
    (엣지케이스: E003 박지훈은 Q1만 존재)

    Args:
        emp_id: 직원 ID (예: "E001")
        year:   조회 연도 (예: 2025)

    Returns:
        JSON 문자열. 해당 직원·연도의 1on1 레코드 리스트.
        없는 분기는 "quarters_missing" 필드로 안내합니다.
    """
    records = _load_json("1on1_records.json")

    # 해당 직원·연도 필터링
    filtered = [
        r for r in records
        if r["emp_id"] == emp_id and r["year"] == year
    ]

    # 실제 기록된 분기 목록
    recorded_quarters = {r["quarter"] for r in filtered}

    # 누락된 분기 계산 (Q1~Q4 기준)
    all_quarters = {"Q1", "Q2", "Q3", "Q4"}
    missing_quarters = sorted(all_quarters - recorded_quarters)

    result = {
        "emp_id": emp_id,
        "year": year,
        "records": filtered,
        "quarters_recorded": sorted(recorded_quarters),
        "quarters_missing": missing_quarters,  # 빈 리스트면 전 분기 기록 있음
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_growth_plan(emp_id: str, year: int) -> str:
    """
    직원의 성장플랜을 반환합니다.
    본인평가(self_reviews) 내 growth_plan 필드에서 추출합니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도

    Returns:
        JSON 문자열. growth_plan 문자열과 improvement_area 포함.
    """
    reviews = _load_json("self_reviews.json")

    review = next(
        (r for r in reviews if r["emp_id"] == emp_id and r["year"] == year),
        None
    )

    if not review:
        return json.dumps({"error": f"{emp_id}의 {year}년 성장플랜 데이터가 없습니다."}, ensure_ascii=False)

    result = {
        "emp_id": emp_id,
        "year": year,
        "growth_plan": review.get("growth_plan", ""),
        "improvement_area": review.get("improvement_area", ""),
        "strength": review.get("strength", ""),
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_self_review(emp_id: str, year: int) -> str:
    """
    직원의 본인평가 전체 내용을 반환합니다.
    자기 등급, 성과 요약, 강점, 개선 영역, 성장 플랜, 상호 성찰을 포함합니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도

    Returns:
        JSON 문자열. 본인평가 전체 데이터.
    """
    reviews = _load_json("self_reviews.json")

    review = next(
        (r for r in reviews if r["emp_id"] == emp_id and r["year"] == year),
        None
    )

    if not review:
        return json.dumps({"error": f"{emp_id}의 {year}년 본인평가 데이터가 없습니다."}, ensure_ascii=False)

    return json.dumps(review, ensure_ascii=False, indent=2)


@mcp.tool()
def get_kpi_plan(emp_id: str, year: int) -> str:
    """
    직원의 KPI 계획 및 달성 현황을 반환합니다.
    각 KPI 항목별 목표, 달성값, 달성률, 가중치를 포함합니다.

    Args:
        emp_id: 직원 ID
        year:   조회 연도

    Returns:
        JSON 문자열. KPI 항목 리스트와 전체 가중 달성률.
    """
    plans = _load_json("kpi_plans.json")

    plan = next(
        (p for p in plans if p["emp_id"] == emp_id and p["year"] == year),
        None
    )

    if not plan:
        return json.dumps({"error": f"{emp_id}의 {year}년 KPI 계획 데이터가 없습니다."}, ensure_ascii=False)

    # 가중 달성률 계산: Σ(달성률 × 가중치) / Σ(가중치)
    kpi_items = plan.get("kpi_items", [])
    total_weight = sum(item["weight"] for item in kpi_items)

    if total_weight > 0:
        weighted_rate = sum(
            item["achievement_rate"] * item["weight"]
            for item in kpi_items
        ) / total_weight
    else:
        weighted_rate = 0.0

    result = {
        **plan,
        "weighted_achievement_rate": round(weighted_rate, 1),
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# 단독 실행 시 MCP stdio 서버로 동작합니다.
# mcp_client.py에서는 인프로세스 방식으로 사용하므로 이 블록은 직접 실행 시에만 동작합니다.
if __name__ == "__main__":
    mcp.run()
