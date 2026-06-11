"""
mcp_client.py - FastMCP 인프로세스 클라이언트 헬퍼

에이전트 코드에서 MCP 도구를 호출할 때 사용하는 유일한 인터페이스입니다.
각 MCP 서버 모듈을 직접 임포트하여 인프로세스(in-process) 방식으로
통신합니다. subprocess 오버헤드 없이 MCP 프로토콜을 그대로 사용합니다.

사용법:
    from mcp_client import call_mcp_tool

    result = await call_mcp_tool("get_1on1_records", {"emp_id": "E001", "year": 2025})
    # result는 JSON 파싱된 Python 객체 (list 또는 dict)
"""

import json
from typing import Any

from fastmcp import Client

# 각 MCP 서버 모듈을 임포트합니다.
# 서버는 FastMCP 인스턴스(mcp)를 module-level 변수로 노출합니다.
from mcp_servers import hihr_server
from mcp_servers import hr_datalake_server
from mcp_servers import eval_history_server
from mcp_servers import vector_store_server
from mcp_servers import rag_index_server

# ─── 도구명 → FastMCP 서버 인스턴스 매핑 ──────────────────────
# 에이전트는 도구명만 알면 되고, 어느 서버에 있는지는 몰라도 됩니다.
_SERVER_MAP: dict[str, Any] = {
    # hiHR 서버 - 1on1 면담, 성장플랜, 본인평가 관련
    "get_1on1_records":   hihr_server.mcp,
    "get_growth_plan":    hihr_server.mcp,
    "get_self_review":    hihr_server.mcp,
    "get_kpi_plan":       hihr_server.mcp,

    # HR DataLake 서버 - 메일, Teams, 캘린더 요약
    "get_mail_summary":   hr_datalake_server.mcp,
    "get_teams_chat":     hr_datalake_server.mcp,
    "get_calendar":       hr_datalake_server.mcp,

    # 평가이력 서버 - 과거 등급, 코멘트, 피드백
    "get_eval_grade":     eval_history_server.mcp,
    "get_eval_comment":   eval_history_server.mcp,
    "get_past_feedback":  eval_history_server.mcp,

    # 벡터 스토어 서버 - 임베딩 저장/검색 (ChromaDB)
    "embed_text":          vector_store_server.mcp,
    "similarity_search":   vector_store_server.mcp,
    "store_embedding":     vector_store_server.mcp,

    # RAG 인덱스 서버 - 가이드라인 문서 검색
    "retrieve_grade_criteria": rag_index_server.mcp,
    "retrieve_guideline":      rag_index_server.mcp,
}


async def call_mcp_tool(tool_name: str, arguments: dict) -> Any:
    """
    MCP 도구를 호출하고 결과를 반환합니다.

    FastMCP Client를 인프로세스 방식으로 생성하여 호출합니다.
    각 호출마다 새 Client를 만들지만, 인프로세스이므로 오버헤드가 최소화됩니다.

    Args:
        tool_name: 호출할 MCP 도구 이름 (예: "get_1on1_records")
        arguments: 도구에 전달할 인자 딕셔너리

    Returns:
        도구 응답을 JSON 파싱한 Python 객체.
        텍스트 응답이면 문자열 그대로, JSON이면 dict/list.

    Raises:
        KeyError: 등록되지 않은 도구명을 사용한 경우
        Exception: MCP 도구 실행 중 오류 발생 시
    """
    if tool_name not in _SERVER_MAP:
        raise KeyError(f"알 수 없는 MCP 도구: '{tool_name}'. SERVER_MAP을 확인하세요.")

    server_instance = _SERVER_MAP[tool_name]

    # FastMCP Client를 컨텍스트 매니저로 사용합니다.
    # 인프로세스 방식이므로 subprocess 없이 직접 서버 함수를 호출합니다.
    async with Client(server_instance) as client:
        result = await client.call_tool(tool_name, arguments)

    # FastMCP 3.x의 call_tool()은 CallToolResult 객체를 반환합니다.
    # content는 list[TextContent] 형태이며, 첫 번째 항목의 텍스트를 추출해 JSON이면 파싱합니다.
    if not result.content:
        return {}

    raw_text = result.content[0].text

    # JSON 파싱 시도 - 실패하면 원본 텍스트를 그대로 반환합니다.
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return raw_text


async def list_tools(server_name: str) -> list[dict]:
    """
    특정 서버에서 제공하는 도구 목록을 조회합니다.
    디버깅 및 개발 시 사용합니다.

    Args:
        server_name: 서버 이름 ("hihr" | "datalake" | "eval" | "vector" | "rag")
    """
    server_map = {
        "hihr":    hihr_server.mcp,
        "datalake": hr_datalake_server.mcp,
        "eval":    eval_history_server.mcp,
        "vector":  vector_store_server.mcp,
        "rag":     rag_index_server.mcp,
    }
    server = server_map.get(server_name)
    if not server:
        raise KeyError(f"알 수 없는 서버: '{server_name}'")

    async with Client(server) as client:
        tools = await client.list_tools()

    return [{"name": t.name, "description": t.description} for t in tools]
