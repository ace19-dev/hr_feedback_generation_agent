# HR 피드백 보조 AI — Multi-Agent + MCP 아키텍처

`CLAUDE.md`(기획/설계 문서)와 `doc/architecture_diagram.png`(아키텍처 다이어그램)를 기반으로
프로젝트 전체 구조와 동작 방식을 정리한 설명 문서입니다.

---

## 1. 프로젝트 개요

팀장이 평가 대상 팀원을 선택하면, **Orchestrator Agent**가 4개의 서브 에이전트를
순차·병렬로 호출하여 다음을 자동 생성하는 HR 피드백 보조 AI입니다.

1. 성과 데이터 통합 요약
2. 피드백 초안 생성
3. 피드백 품질 체크
4. 상위평가자(실장·본부장)용 팀원 비교뷰

실제 사내 시스템(hiHR, HR DataLake, 평가이력 DB 등) 연동 대신, `generate_mock_data.py`로
생성한 mock 데이터를 사용해 개발·검증합니다.

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│ UI: 팀장 / 상위평가자 UI                                       │
│  - 통합요약 뷰 · 피드백 초안 편집 · 품질체크 결과 ·             │
│    실/본부 비교표 · 수정 후 재확인                              │
└───────────────┬─────────────────────────▲────────────────────┘
       Trigger   │                         │ 결과 전달
   (평가대상 선택) │                         │ (초안·체크결과)
                  ▼                         │
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator Agent                                            │
│  Trigger 수신 → 데이터 수집 지시 → 서브 에이전트 순차/병렬 호출  │
│  → 결과 취합·저장 → UI 응답                                    │
│  Tools: invoke_subagent, collect_input_data, store_result,    │
│         human_approval_gate, notify_ui                         │
└───────┬─────────────┬─────────────┬─────────────┬────────────┘
        │순차          │순차          │             │ 기능①완료 후 분기
        ▼             ▼             ▼             ▼ (기능②③과 병렬 실행)
 ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────┐
 │ 기능1      │ │ 기능2      │ │ 기능3      │ │ 기능4          │
 │ 성과데이터  │ │ 피드백     │ │ 피드백     │ │ 상위평가자      │
 │ 통합요약    │ │ 초안 생성   │ │ 품질체크    │ │ 비교뷰          │
 └───────────┘ └───────────┘ └───────────┘ └───────────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                              ▼
            MCP Server Layer (hiHR / HR DataLake / 평가이력 /
                               VectorStore / RAG Index)
                              │
                              ▼ 결과 저장
            공유 상태 저장소 (Orchestrator Read/Write)
            통합요약 JSON | 피드백 초안 | 품질체크 결과 | 비교뷰 데이터
            ※ 에이전트 간 직접 통신 없음 — Orchestrator가 저장소를
              통해 중간 결과 전달
                              │
                              ▼ ETL · API Connector
            실제 데이터 소스 (Source Systems)
            hiHR 시스템 | HR Data Lake | 평가 이력 DB |
            학습/교육 이수 이력 | 코칭·업무배분 프로젝트 결과 |
            전년도 평가 결과 | 등급 기준 가이드라인
```

---

## 3. Orchestrator 실행 흐름

```
팀장 → 평가 대상 선택 → Trigger (emp_id, session_id)
  │
  ├─ collect_input_data() : 직원 기본정보 수집
  │
  ├─ [순차] 기능1 (agent1_summary) → summary.json 저장
  │     │
  │     └─ 완료 즉시 [병렬 분기] 기능4 (agent4_comparison)를
  │        백그라운드 task로 시작 (Human Gate / 기능2·3과 무관)
  │
  ├─ [순차] 기능2 (agent2_draft) → draft.json 저장
  │         └─ human_approval_gate()  ← 팀장 검토 대기 (WebSocket pause)
  │                팀장 수정 후 재개 →
  │
  ├─ [순차] 기능3 (agent3_quality)
  │         └─ 내부 4개 체커는 asyncio.gather로 병렬 실행
  │
  ├─ 기능4 백그라운드 task 결과 await (이미 완료돼 있으면 즉시 반환)
  │
  └─ notify_ui(session_id) → WebSocket push → 팀장 UI 4탭 갱신
```

> 다이어그램의 "기능①완료 후 분기 / 기능②③과 병렬 실행" 규칙을 반영해,
> `orchestrator.py`는 기능1 완료 직후 `asyncio.create_task()`로 기능4를 먼저
> 띄워두고, 기능3 완료 후 그 결과를 `await`합니다.

---

## 4. 서브 에이전트 4개 상세

### 기능1 — 성과데이터 통합요약 (`agents/agent1_summary.py`)
- **Input**: KPI계획 + 1on1 이력(Q1~Q4) + 본인평가 + 성장플랜
- **Processing**: 분기별 시계열 통합, 업적/역량 영역 재분류, 1년간 키워드·업무
  토픽 추출, 목표 대비 달성 맵핑
- **Output**: `summary.json` → 공유 저장소(`step="summary"`)
- **MCP 호출**: hiHR(1on1·성장플랜·본인평가), VectorStore(타임라인 임베딩 저장)
- **Tools**: `get_1on1_history`, `get_self_review`, `get_kpi_plan`,
  `extract_topics`, `build_timeline`

### 기능2 — 피드백 초안 생성 (`agents/agent2_draft.py`)
- **Input**: 기능1 결과(`summary.json`) + 과거 평가 이력
- **Processing**: 업적 피드백 초안(주요 성과 기반), 역량 피드백 초안(면담
  내용 기반), 강점·개선점 구분 서술
- **Output**: `draft.json` → 공유 저장소(`step="draft"`) 저장 후
  **human_approval_gate** 발동
- **MCP 호출**: 평가이력 MCP, VectorStore(유사 피드백 검색)
- **Tools**: `get_eval_history`, `get_past_feedback`, `generate_draft_llm`,
  `edit_draft`

### 기능3 — 피드백 품질 체크 (`agents/agent3_quality.py`)
- **Input**: 팀장 수정·확인 코멘트 + 기능1 통합 데이터
- **Processing**: 아래 4개 체커를 `asyncio.gather`로 병렬 실행
  1. `detect_recency_bias` — 코멘트가 특정 분기에 편중되는지 (Embedding 유사도)
  2. `validate_grade_comment` — 높은 등급인데 부정적 코멘트만 있는지 (RAG
     등급 기준)
  3. `check_omission` — 면담에서 언급된 주요 업무가 코멘트에 누락됐는지
  4. `detect_wrong_person` — 다른 팀원 업무를 잘못 기재했는지
- **Output**: `quality_check.json` → 공유 저장소(`step="quality"`) 저장
  (체커별 결과 + 개선 제안 메시지)
- **MCP 호출**: VectorStore(코멘트 편향 감지), RAG Index(등급 기준 조회)

### 기능4 — 상위평가자 비교뷰 (`agents/agent4_comparison.py`)
- **Input**: 부서 전 구성원의 기능1 요약 (기능1 완료 시점에 병렬 분기)
- **Processing**: 구성원별 대표 업무 1~2줄 요약 생성, KPI 달성률·추천 등급 등 포함
- **Output**: `comparison_table.json` → 공유 저장소(`step="comparison"`)
  저장 (실장·본부장용 비교표)
- **MCP 호출**: VectorStore(팀원 요약 검색), RAG Index(가이드라인 조회)
- **Tools**: `get_all_summaries`, `generate_comparison_table`
- 직원 기본정보(이름·직책·직급)는 `employees.json`을 신뢰 소스(source of
  truth)로 항상 덮어써서, LLM이 생성한 이름이 실제 mock 데이터와 어긋나지
  않도록 보정합니다.

---

## 5. MCP 서버 계층

표준 `mcp` SDK + stdio(JSON-RPC) 통신. 에이전트는 DB·SDK를 직접 호출하지 않고
반드시 `mcp_client.call_mcp_tool()`을 통해서만 외부 데이터에 접근합니다.

| MCP 서버 | 주요 Tool | 데이터 소스 |
|---|---|---|
| `hihr_server.py` | `get_growth_plan`, `get_1on1_records`, `get_self_review` | `1on1_records.json`, `self_reviews.json` |
| `hr_datalake_server.py` | `get_mail_summary`, `get_teams_chat`, `get_calendar` | `hr_datalake.json` |
| `eval_history_server.py` | `get_eval_grade`, `get_eval_comment`, `get_past_feedback` | `eval_history.json` |
| `vector_store_server.py` | `embed_text`, `similarity_search`, `store_embedding` | ChromaDB (`data/chroma`) |
| `rag_index_server.py` | `retrieve_grade_criteria`, `retrieve_guideline` | `data/mock/guidelines/*.md` (ChromaDB 인덱싱) |

각 서버는 Orchestrator가 subprocess로 기동하며, `mcp_client.py`의
`SERVER_MAP`이 tool 이름 → 서버 파일 경로를 매핑합니다.

---

## 6. 공유 상태 저장소 (`shared_store.py`)

세션별 SQLite 파일(`data/state/session_<id>.db`)에 두 테이블을 관리합니다.

```sql
CREATE TABLE session (
    session_id   TEXT PRIMARY KEY,
    emp_id       TEXT NOT NULL,
    created_at   TEXT,
    status       TEXT   -- pending / running / awaiting_human / done / failed
);

CREATE TABLE result (
    session_id   TEXT,
    step         TEXT,  -- summary / draft / quality / comparison
    payload      TEXT,  -- JSON blob
    updated_at   TEXT,
    PRIMARY KEY (session_id, step)
);
```

서브 에이전트끼리 직접 통신하지 않고, Orchestrator가 이 저장소를 통해 단계별
결과를 다음 에이전트로 전달합니다(느슨한 결합).

또한 `format_emp_references_deep()` / `format_emp_references()`는 결과
텍스트에 `E001` 같은 사번이 그대로 노출되지 않도록, `employees.json`을 참조해
"이름 직책" 형태로 치환합니다(내부 매칭/로직에서는 `emp_id`를 그대로 유지).

---

## 7. UI 구성 (`ui/app.py` + `ui/templates/index.html`)

FastAPI + WebSocket 기반. 팀장이 평가 대상을 선택하면 파이프라인이 시작되고,
각 에이전트가 완료될 때마다 WebSocket 이벤트로 해당 탭이 실시간 갱신됩니다.

| 탭 | 내용 | 데이터 소스 |
|---|---|---|
| 탭1 통합 요약 | Q1→Q4 타임라인, 업적·역량 분리 뷰 | `result.summary` |
| 탭2 피드백 초안 | 업적·역량 코멘트 편집 에디터 | `result.draft` |
| 탭3 품질 체크 | 4종 체커 결과 + 경고 배지 | `result.quality` |
| 탭4 팀원 비교표 | 구성원 비교 테이블 | `result.comparison` |

WebSocket 이벤트 타입: `agent_progress`, `step_result`, `human_gate`,
`done`, `error`. `human_gate` 발동 시 탭2에 "검토 후 확인" 버튼이 노출되고,
팀장이 확인하면 `approve_draft()`가 호출되어 파이프라인이 재개됩니다.

---

## 8. 핵심 설계 원칙

1. **MCP 프로토콜** — 에이전트가 직접 SDK/DB 드라이버를 호출하지 않고 MCP
   Tool Call(JSON-RPC) 한 줄로 외부 시스템에 접근 → 에이전트 코드 단순화·교체 용이
2. **느슨한 결합** — 서브 에이전트끼리 직접 통신 금지. Orchestrator가 공유
   저장소를 통해 중간 결과 전달 → 각 에이전트를 독립적으로 교체·테스트 가능
3. **순차·병렬 혼합** — 기능1→2→3은 의존 관계로 순차 실행 / 기능4는 기능1
   완료 시점에 병렬 분기 / 기능3 내부 4개 체커는 서로 독립이므로 병렬 실행
4. **Human-in-the-Loop** — `human_approval_gate` Tool이 기능2 초안 생성 후
   팀장 검토를 강제 — 수정본이 기능3 입력으로 재진입 (AI는 '보조', 최종
   판단은 팀장)
5. **데이터 품질 의존성** — 구성원이 hiHR에 입력하는 데이터 품질이 Agent
   산출물 품질에 직결 → 입력 표준·필수 항목 정의가 선행 조건

---

## 9. 디렉터리 구조

```
agent_hr/
├── data/
│   ├── mock/
│   │   ├── employees.json          # 직원 기본정보 (팀원 5명 + 팀장 1명)
│   │   ├── kpi_plans.json          # KPI·연간업무계획
│   │   ├── 1on1_records.json       # 분기별 1on1 면담 이력 (Q1~Q4)
│   │   ├── self_reviews.json       # 본인평가·성장플랜·Mutual Reflection
│   │   ├── eval_history.json       # 과거 평가 등급·코멘트
│   │   ├── hr_datalake.json        # 메일제목·Teams대화·캘린더 요약
│   │   └── guidelines/             # RAG 원본 (등급 기준·피드백 가이드)
│   ├── chroma/                     # ChromaDB 벡터 스토어
│   └── state/                      # 세션별 SQLite 공유 저장소
├── mcp_servers/                    # 5개 MCP 서버 (stdio/JSON-RPC)
├── agents/                         # orchestrator + 서브 에이전트 4개
├── ui/                             # FastAPI 백엔드 + WebSocket + 템플릿
├── shared_store.py                 # SQLite 기반 공유 상태 저장소
├── mcp_client.py                   # MCP JSON-RPC 클라이언트 헬퍼
├── generate_mock_data.py           # 테스트 데이터 일괄 생성
├── init_rag.py                     # RAG 인덱스 초기화 (최초 1회)
├── config.py                       # 설정 (환경변수 로딩)
└── doc/architecture_diagram.png    # 아키텍처 다이어그램
```

---

## 10. 실행 방법

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

`config.py`의 `MODEL`은 현재 `claude-haiku-4-5-20251001`로 설정되어 있어,
개발/테스트 단계에서 빠른 응답을 우선합니다.

---

## 11. 에러 처리 전략

| 상황 | 처리 방식 |
|---|---|
| MCP 서버 subprocess 기동 실패 | 3회 재시도 후 에러 메시지를 UI에 WebSocket push |
| LLM API 타임아웃 (>60초) | `asyncio.wait_for` + 타임아웃 예외 → 해당 step 상태 `failed` 저장 |
| tool_use 결과 파싱 실패 | 원본 텍스트를 그대로 저장, 로그 출력, 다음 단계 진행 |
| human_approval_gate 미응답 | 30분 후 세션 만료 처리 |
| VectorStore 미초기화 | `init_rag.py` 실행 안내 메시지 반환 |
