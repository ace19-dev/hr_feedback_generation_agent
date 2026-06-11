# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project: HR 피드백 보조 AI (Multi-Agent + MCP)

## 프로젝트 개요

팀장이 평가 대상 팀원을 선택하면 Orchestrator Agent가 4개의 서브 에이전트를 순차·병렬로 호출하여 성과 데이터 요약 → 피드백 초안 생성 → 품질 체크 → 상위평가자 비교뷰를 자동 생성하는 HR 보조 AI.

실제 데이터 소스 없음 → `generate_mock_data.py`로 테스트 데이터를 먼저 생성한 뒤 개발 진행.

## 디렉터리 구조

```
agent_hr/
├── data/
│   ├── mock/
│   │   ├── employees.json          # 직원 기본정보 (팀원 5명 + 팀장 1명)
│   │   ├── kpi_plans.json          # KPI·연간업무계획 (직원별·연도별)
│   │   ├── 1on1_records.json       # 분기별 1on1 면담 이력 (Q1~Q4)
│   │   ├── self_reviews.json       # 본인평가·성장플랜·Mutual Reflection
│   │   ├── eval_history.json       # 과거 평가 등급·코멘트 (전년도)
│   │   ├── hr_datalake.json        # 메일제목·Teams대화·캘린더 요약
│   │   └── guidelines/
│   │       ├── grade_criteria.md   # 등급별 피드백 기준 (RAG 원본 문서)
│   │       └── feedback_guide.md   # 피드백 작성 가이드라인 (RAG 원본 문서)
│   └── state/
│       └── session_{id}.db         # 공유 상태 저장소 (SQLite)
├── mcp_servers/
│   ├── hihr_server.py              # get_growth_plan, get_1on1_records, get_self_review
│   ├── hr_datalake_server.py       # get_mail_summary, get_teams_chat, get_calendar
│   ├── eval_history_server.py      # get_eval_grade, get_eval_comment, get_past_feedback
│   ├── vector_store_server.py      # embed_text, similarity_search, store_embedding
│   └── rag_index_server.py         # retrieve_grade_criteria, retrieve_guideline
├── agents/
│   ├── orchestrator.py             # 메인 오케스트레이터
│   ├── agent1_summary.py           # 기능1: 성과데이터 통합요약
│   ├── agent2_draft.py             # 기능2: 피드백 초안 생성
│   ├── agent3_quality.py           # 기능3: 품질 체크 (4종 병렬)
│   └── agent4_comparison.py        # 기능4: 상위평가자 비교뷰
├── ui/
│   ├── app.py                      # FastAPI 백엔드 + WebSocket
│   ├── static/
│   └── templates/
│       └── index.html              # 팀장 UI (4탭 레이아웃)
├── shared_store.py                 # SQLite 기반 공유 상태 저장소
├── mcp_client.py                   # MCP JSON-RPC 클라이언트 헬퍼
├── generate_mock_data.py           # 테스트 데이터 일괄 생성
├── init_rag.py                     # RAG 인덱스 초기화 (최초 1회 실행)
├── config.py                       # 설정 (환경변수 로딩)
├── requirements.txt
└── .env                            # API 키 (git 제외)
```

## 기능 요건 (4개 서브 에이전트)

### 기능1 — 성과데이터 통합요약 (agent1_summary.py)
- **Input**: KPI계획 + 1on1이력(Q1~Q4) + 본인평가 + 성장플랜
- **Processing**: 분기별 시계열 통합, 업적/역량 영역 재분류, 1년간 키워드·업무 토픽 추출, 목표 대비 달성 맵핑
- **Output**: `summary.json` → 공유 저장소 저장
- **MCP 호출**: hiHR(1on1·성장플랜), HR DataLake, VectorStore(타임라인 임베딩 저장)
- **Tools**: `get_1on1_history`, `get_self_review`, `get_kpi_plan`, `extract_topics`, `build_timeline`

### 기능2 — 피드백 초안 생성 (agent2_draft.py)
- **Input**: 기능1 결과(`summary.json`) + 과거 평가 이력
- **Processing**: 업적 피드백 초안(주요 성과 기반), 역량 피드백 초안(면담 내용 기반), 강점·개선점 구분 서술
- **Output**: `draft.json` → 공유 저장소 저장 후 **human_approval_gate** 발동
- **MCP 호출**: 평가이력 MCP, VectorStore(유사 피드백 검색)
- **Tools**: `get_eval_history`, `get_past_feedback`, `generate_draft_llm`, `edit_draft`

### 기능3 — 피드백 품질 체크 (agent3_quality.py)
- **Input**: 팀장 수정·확인 코멘트 + 기능1 통합 데이터
- **Processing**: 아래 4개 체커를 `asyncio.gather`로 병렬 실행
  1. `detect_recency_bias` — 코멘트가 특정 분기에 편중되는지 (Embedding 유사도)
  2. `validate_grade_comment` — 높은 등급인데 부정적 코멘트만 있는지 (RAG 등급 기준)
  3. `check_omission` — 면담에서 언급된 주요 업무가 코멘트에 누락됐는지
  4. `detect_wrong_person` — 다른 팀원 업무를 잘못 기재했는지
- **Output**: `quality_check.json` (체커별 결과 + 개선 제안 메시지)
- **MCP 호출**: VectorStore(코멘트 편향 감지), RAG Index(등급 기준 조회)

### 기능4 — 상위평가자 비교뷰 (agent4_comparison.py)
- **Input**: 부서 전 구성원(20인)의 기능1 요약 (기능1 완료 시점에 병렬 분기)
- **Processing**: 구성원별 대표 업무 1~2줄 요약 생성
- **Output**: `comparison_table.json` (20인 비교표, 실장·본부장용)
- **MCP 호출**: VectorStore(팀원 요약 검색), RAG Index(가이드라인 조회)
- **Tools**: `get_all_summaries`, `generate_comparison_table`

## Orchestrator 실행 흐름

```
팀장 → 평가 대상 선택 → Trigger (emp_id, session_id)
  │
  ├─ collect_input_data() : 직원 기본정보 수집
  │
  ├─ [순차] invoke_subagent("agent1") → summary.json 저장
  │
  ├─ [순차] invoke_subagent("agent2") → draft.json 저장
  │         └─ human_approval_gate()  ← 팀장 검토 대기 (WebSocket pause)
  │                팀장 수정 후 재개 →
  │
  ├─ [병렬] asyncio.gather(
  │           invoke_subagent("agent3"),   # 품질 체크
  │           invoke_subagent("agent4")    # 비교뷰 (기능1 결과 활용)
  │         )
  │
  └─ notify_ui(session_id) → WebSocket push → 팀장 UI 갱신
```

## 에이전트↔MCP 통신 패턴

에이전트 내부에서 Claude `tool_use` 루프로 MCP Tool Call을 수행한다.

```python
# agents/agent1_summary.py 핵심 패턴
import anthropic
from mcp_client import call_mcp_tool   # JSON-RPC 래퍼

client = anthropic.Anthropic()

async def run(emp_id: str, session_id: str) -> dict:
    tools = [
        {"name": "get_1on1_records", "description": "...", "input_schema": {...}},
        {"name": "get_kpi_plan",     "description": "...", "input_schema": {...}},
    ]
    messages = [{"role": "user", "content": f"직원 {emp_id}의 성과 데이터를 통합 요약하라."}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason == "end_turn":
            return parse_summary(response)
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await call_mcp_tool(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
```

## MCP 서버 구현 패턴

표준 `mcp` SDK + stdio 통신 방식 사용.

```python
# mcp_servers/hihr_server.py 핵심 패턴
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json, asyncio

server = Server("hihr-mcp")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_1on1_records",
             description="직원의 분기별 1on1 면담 이력 반환",
             inputSchema={"type": "object", "properties": {
                 "emp_id": {"type": "string"},
                 "year":   {"type": "integer"}
             }, "required": ["emp_id", "year"]})
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    data = json.load(open("data/mock/1on1_records.json"))
    records = [r for r in data if r["emp_id"] == arguments["emp_id"]]
    return [TextContent(type="text", text=json.dumps(records, ensure_ascii=False))]

if __name__ == "__main__":
    asyncio.run(stdio_server(server))
```

## MCP 클라이언트 헬퍼 (mcp_client.py)

에이전트에서 MCP 서버를 subprocess로 기동하고 JSON-RPC 요청을 보내는 헬퍼.

```python
# 각 MCP 서버를 subprocess로 기동 후 stdin/stdout으로 JSON-RPC 통신
SERVER_MAP = {
    "get_1on1_records":        "mcp_servers/hihr_server.py",
    "get_growth_plan":         "mcp_servers/hihr_server.py",
    "get_self_review":         "mcp_servers/hihr_server.py",
    "get_mail_summary":        "mcp_servers/hr_datalake_server.py",
    "get_eval_grade":          "mcp_servers/eval_history_server.py",
    "embed_text":              "mcp_servers/vector_store_server.py",
    "similarity_search":       "mcp_servers/vector_store_server.py",
    "retrieve_grade_criteria": "mcp_servers/rag_index_server.py",
    "retrieve_guideline":      "mcp_servers/rag_index_server.py",
}
```

## 공유 상태 저장소 스키마 (SQLite)

```sql
-- shared_store.py 가 관리
CREATE TABLE session (
    session_id   TEXT PRIMARY KEY,
    emp_id       TEXT NOT NULL,
    created_at   TEXT,
    status       TEXT   -- pending / running / awaiting_human / done
);

CREATE TABLE result (
    session_id   TEXT,
    step         TEXT,  -- summary / draft / quality / comparison
    payload      TEXT,  -- JSON blob
    updated_at   TEXT,
    PRIMARY KEY (session_id, step)
);
```

## RAG 인덱스 초기화 절차

```
# 최초 1회만 실행
python init_rag.py

# 내부 처리:
# 1. data/mock/guidelines/*.md 파일 청크 분할 (500자 단위)
# 2. VectorStore MCP의 embed_text 호출 → ChromaDB에 저장
# 3. 이후 retrieve_grade_criteria / retrieve_guideline 호출 시 similarity_search 사용
```

## 환경 설정

**requirements.txt**
```
anthropic>=0.40.0
mcp>=1.0.0
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
chromadb>=0.5.0
python-dotenv>=1.0.0
jinja2>=3.1.0
websockets>=13.0
```

**.env** (git에서 제외)
```
ANTHROPIC_API_KEY=sk-ant-...
SESSION_SECRET=...
```

**config.py**
```python
from dotenv import load_dotenv
import os
load_dotenv()
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6"
MOCK_DATA_DIR = "data/mock"
STATE_DB_PATH = "data/state"
```

## 전체 실행 순서

```bash
# 1. 가상환경 생성 및 패키지 설치
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. .env 파일 생성 후 ANTHROPIC_API_KEY 입력

# 3. 테스트 데이터 생성 (최초 1회)
python generate_mock_data.py

# 4. RAG 인덱스 초기화 (최초 1회)
python init_rag.py

# 5. UI 서버 실행 (MCP 서버는 Orchestrator가 subprocess로 자동 기동)
python ui/app.py

# 브라우저에서 http://localhost:8000 접속
```

## 에러 처리 전략

| 상황 | 처리 방식 |
|------|-----------|
| MCP 서버 subprocess 기동 실패 | 3회 재시도 후 에러 메시지를 UI에 WebSocket push |
| LLM API 타임아웃 (>60초) | `asyncio.wait_for` + 타임아웃 예외 → 해당 step 상태 `failed` 저장 |
| tool_use 결과 파싱 실패 | 원본 텍스트를 그대로 저장, 로그 출력, 다음 단계 진행 |
| human_approval_gate 미응답 | 30분 후 세션 만료 처리 |
| VectorStore 미초기화 | `init_rag.py` 실행 안내 메시지 반환 |

## UI 탭 구성 (팀장 화면)

| 탭 | 내용 | 데이터 소스 |
|----|------|-------------|
| **탭1** 통합 요약 | Q1→Q4 타임라인, 업적·역량 분리 뷰 | `result.summary` |
| **탭2** 피드백 초안 | 업적·역량 코멘트 편집 에디터 | `result.draft` |
| **탭3** 품질 체크 | 4종 체커 결과 + 경고 배지 | `result.quality` |
| **탭4** 팀원 비교표 | 20인 업무 요약 테이블 | `result.comparison` |

WebSocket 이벤트로 각 에이전트 완료 시점마다 해당 탭 실시간 갱신.
`human_approval_gate` 발동 시 탭2에 "검토 후 확인" 버튼 노출.

## 테스트 시나리오

**정상 흐름 (Happy Path)**
1. 팀장이 "김민준(E001)" 선택
2. 기능1: Q1~Q4 타임라인 JSON 생성 확인
3. 기능2: 업적·역량 초안 텍스트 생성 확인
4. Human gate: 팀장이 초안 수정 후 "확인" 클릭
5. 기능3: 4종 체커 모두 통과 시 경고 없음 확인
6. 기능4: 팀 전원(5명) 비교표 생성 확인

**엣지 케이스**
- 1on1 이력이 Q1만 있는 직원 → 누락 분기는 "기록 없음" 처리
- 등급 S인데 코멘트가 부정적 → 기능3 체커2 경고 발동 확인
- 타 팀원 이름이 코멘트에 포함 → 기능3 체커4 오류 감지 확인

## 개발 단계 및 순서

| 단계 | 작업 | 완료 기준 |
|------|------|-----------|
| Phase 1 | `generate_mock_data.py` 작성 및 실행 | 6개 JSON + 2개 가이드라인 MD 생성 |
| Phase 2 | MCP 서버 5개 구현 | 각 서버 단독 실행 + tool call 응답 확인 |
| Phase 3 | `init_rag.py` + VectorStore MCP 구현 | ChromaDB에 가이드라인 청크 인덱싱 완료 |
| Phase 4 | 서브 에이전트 4개 구현 | 각 에이전트 단독 실행 + 결과 JSON 출력 확인 |
| Phase 5 | `orchestrator.py` 구현 | 전체 흐름 CLI 실행 (UI 없이) 완료 |
| Phase 6 | FastAPI UI + WebSocket | 브라우저에서 4탭 실시간 결과 확인 |
| Phase 7 | 엣지 케이스 테스트 | 위 3개 엣지 케이스 모두 통과 |

## 설계 원칙 (아키텍처 준수 사항)

1. **MCP 프로토콜 준수** — 에이전트 코드에서 DB·SDK 직접 호출 금지. 반드시 `call_mcp_tool()`만 사용
2. **느슨한 결합** — 서브 에이전트끼리 직접 통신 금지. Orchestrator가 `shared_store`를 통해 중간 결과 전달
3. **순차·병렬 혼합** — 기능1→2→3 순차 / 기능4는 기능1 완료 즉시 병렬 분기 / 기능3 내 4개 체커는 `asyncio.gather` 병렬
4. **Human-in-the-Loop** — `human_approval_gate`로 기능2 초안 후 팀장 검토 강제. AI는 보조, 최종 판단은 팀장
5. **데이터 품질** — mock 데이터는 현실적 시나리오(편향 있는 케이스 포함)로 설계
