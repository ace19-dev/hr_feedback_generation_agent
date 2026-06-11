"""
init_rag.py - RAG 인덱스 초기화 스크립트

data/mock/guidelines/*.md 파일을 청크 단위로 분할하여
ChromaDB에 임베딩과 함께 저장합니다.
이 스크립트는 최초 1회만 실행하면 됩니다.
(이미 실행했다면 재실행해도 안전합니다 - upsert 사용)

실행: python init_rag.py
"""

import sys
import re
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

# Windows 콘솔 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import CHROMA_DB_DIR, GUIDELINES_DIR

# RAG 인덱스 서버와 동일한 컬렉션 이름 사용 (일관성 보장)
GRADE_CRITERIA_COLLECTION = "grade_criteria"
FEEDBACK_GUIDE_COLLECTION = "feedback_guide"

# 청크 분할 기준: 섹션 구분자(##) 기준으로 분할합니다.
# 500자 단위 분할보다 섹션 단위가 의미적 완결성이 높습니다.
CHUNK_BY_SECTION = True
CHUNK_SIZE = 500           # 섹션 단위 분할 비활성화 시 사용하는 글자 수 기준
CHUNK_OVERLAP = 50         # 청크 간 오버랩 글자 수 (문맥 연결성 유지)


def split_by_section(text: str, source: str) -> list[dict]:
    """
    마크다운 문서를 ## 섹션 단위로 분할합니다.
    각 청크에 source와 section 메타데이터를 붙입니다.

    Args:
        text:   마크다운 전체 텍스트
        source: 파일명 (메타데이터로 저장)

    Returns:
        [{"content": ..., "section": ..., "source": ...}, ...] 리스트
    """
    chunks = []

    # ## 또는 ### 로 시작하는 섹션 경계를 기준으로 분할
    # 정규식: ## 또는 ### 다음에 텍스트가 오는 줄
    section_pattern = re.compile(r'^#{2,3}\s+.+', re.MULTILINE)
    matches = list(section_pattern.finditer(text))

    if not matches:
        # 섹션이 없으면 전체 텍스트를 하나의 청크로 처리
        return [{"content": text.strip(), "section": "전체", "source": source}]

    for i, match in enumerate(matches):
        section_title = match.group().strip("# ").strip()
        start = match.start()
        # 다음 섹션 시작 전까지가 현재 섹션의 범위
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if len(content) > 20:  # 너무 짧은 청크는 건너뜀
            chunks.append({
                "content": content,
                "section": section_title,
                "source": source,
            })

    return chunks


def split_by_char(text: str, source: str, chunk_size: int, overlap: int) -> list[dict]:
    """
    글자 수 기준으로 텍스트를 분할합니다. (섹션 분할 대안)

    Args:
        text:       전체 텍스트
        source:     파일명
        chunk_size: 청크당 최대 글자 수
        overlap:    청크 간 오버랩 글자 수

    Returns:
        청크 딕셔너리 리스트
    """
    chunks = []
    start = 0
    chunk_idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        content = text[start:end].strip()

        if len(content) > 20:
            chunks.append({
                "content": content,
                "section": f"chunk_{chunk_idx:03d}",
                "source": source,
            })
            chunk_idx += 1

        # 다음 청크 시작 위치 (오버랩 적용)
        start = end - overlap if end < len(text) else len(text)

    return chunks


def index_markdown_file(
    filepath: Path,
    collection: chromadb.Collection,
    collection_name: str
) -> int:
    """
    마크다운 파일을 청크로 분할하고 ChromaDB에 저장합니다.

    Returns:
        저장된 청크 수
    """
    print(f"  파일 읽기: {filepath.name}")
    text = filepath.read_text(encoding="utf-8")
    source = filepath.name

    # 청크 분할 방식 선택
    if CHUNK_BY_SECTION:
        chunks = split_by_section(text, source)
        print(f"  섹션 분할: {len(chunks)}개 청크 생성")
    else:
        chunks = split_by_char(text, source, CHUNK_SIZE, CHUNK_OVERLAP)
        print(f"  글자 수 분할: {len(chunks)}개 청크 생성")

    if not chunks:
        print(f"  경고: {filepath.name}에서 유효한 청크가 생성되지 않았습니다.")
        return 0

    # ChromaDB에 upsert (재실행 안전)
    documents = [c["content"] for c in chunks]
    ids = [f"{collection_name}_{source}_{i:03d}" for i, _ in enumerate(chunks)]
    metadatas = [{"source": c["source"], "section": c["section"]} for c in chunks]

    collection.upsert(
        documents=documents,
        ids=ids,
        metadatas=metadatas
    )

    print(f"  ChromaDB 저장 완료: {len(chunks)}개")
    return len(chunks)


def main():
    print("=" * 55)
    print("RAG 인덱스 초기화 시작")
    print("=" * 55)

    # ChromaDB 클라이언트 초기화
    print(f"\nChromaDB 경로: {CHROMA_DB_DIR}")
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))

    # 임베딩 함수 초기화 (첫 실행 시 모델 다운로드가 필요할 수 있습니다)
    print("임베딩 모델 로딩 중 (all-MiniLM-L6-v2)...")
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    print("임베딩 모델 로딩 완료")

    total_chunks = 0

    # 1. 등급 기준 문서 인덱싱
    print(f"\n[1/2] 등급 기준 문서 인덱싱...")
    grade_coll = chroma_client.get_or_create_collection(
        name=GRADE_CRITERIA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"}
    )
    grade_file = GUIDELINES_DIR / "grade_criteria.md"
    if grade_file.exists():
        n = index_markdown_file(grade_file, grade_coll, GRADE_CRITERIA_COLLECTION)
        total_chunks += n
    else:
        print(f"  경고: {grade_file} 파일이 없습니다. generate_mock_data.py를 먼저 실행하세요.")

    # 2. 피드백 가이드라인 문서 인덱싱
    print(f"\n[2/2] 피드백 가이드라인 문서 인덱싱...")
    guide_coll = chroma_client.get_or_create_collection(
        name=FEEDBACK_GUIDE_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"}
    )
    guide_file = GUIDELINES_DIR / "feedback_guide.md"
    if guide_file.exists():
        n = index_markdown_file(guide_file, guide_coll, FEEDBACK_GUIDE_COLLECTION)
        total_chunks += n
    else:
        print(f"  경고: {guide_file} 파일이 없습니다. generate_mock_data.py를 먼저 실행하세요.")

    print("\n" + "=" * 55)
    print(f"RAG 인덱스 초기화 완료! 총 {total_chunks}개 청크 저장됨")
    print(f"  - {GRADE_CRITERIA_COLLECTION}: {grade_coll.count()}개")
    print(f"  - {FEEDBACK_GUIDE_COLLECTION}: {guide_coll.count()}개")
    print("=" * 55)
    print("\n다음 단계: python ui/app.py")


if __name__ == "__main__":
    main()
