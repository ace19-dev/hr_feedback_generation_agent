"""
config.py - 전역 설정 모듈

.env 파일에서 환경변수를 로딩하고, 프로젝트 전체에서 공통으로
사용하는 경로·모델명·설정값을 한 곳에서 관리합니다.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 기준으로 .env 파일 로딩
# (어느 디렉터리에서 실행해도 찾을 수 있도록 절대 경로 사용)
_project_root = Path(__file__).parent
load_dotenv(_project_root / ".env")

# ── Anthropic 설정 ──────────────────────────────────────────
# API 키가 없으면 즉시 에러를 내서, 나중에 깊은 곳에서 실패하는 것을 방지
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]

# 사용할 Claude 모델 - 빠른 응답 속도가 필요한 개발/테스트 단계에 적합
MODEL: str = "claude-haiku-4-5-20251001"

# ── 파일 경로 설정 ──────────────────────────────────────────
# 모든 경로를 프로젝트 루트 기준 절대 경로로 관리해 실행 위치에 무관하게 동작
PROJECT_ROOT: Path = _project_root

# 목(Mock) 데이터가 저장되는 디렉터리
MOCK_DATA_DIR: Path = PROJECT_ROOT / "data" / "mock"

# 가이드라인 문서 (RAG 원본) 디렉터리
GUIDELINES_DIR: Path = MOCK_DATA_DIR / "guidelines"

# SQLite 세션 DB 저장 디렉터리
STATE_DB_DIR: Path = PROJECT_ROOT / "data" / "state"

# ChromaDB 벡터 스토어 저장 디렉터리
CHROMA_DB_DIR: Path = PROJECT_ROOT / "data" / "chroma"

# ── 런타임 파라미터 ──────────────────────────────────────────
# LLM 응답 최대 토큰 수 (피드백 초안은 충분히 길어야 하므로 넉넉하게 설정)
MAX_TOKENS: int = 4096

# Human Approval Gate 최대 대기 시간 (초) - 30분 후 세션 만료
HUMAN_GATE_TIMEOUT: int = 1800

# MCP 서버 subprocess 최대 재시도 횟수
MCP_MAX_RETRIES: int = 3

# LLM API 호출 타임아웃 (초)
LLM_TIMEOUT: int = 60

# ── 디렉터리 자동 생성 ───────────────────────────────────────
# import 시점에 필요한 디렉터리를 미리 만들어, 런타임 에러를 방지
for _dir in [MOCK_DATA_DIR, GUIDELINES_DIR, STATE_DB_DIR, CHROMA_DB_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
