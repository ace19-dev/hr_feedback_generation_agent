"""
mcp_servers/rag_index_server.py - RAG 인덱스 MCP 서버

가이드라인 문서(등급 기준, 피드백 가이드)를 ChromaDB에서 검색합니다.
init_rag.py를 먼저 실행해 가이드라인 청크를 인덱싱해야 합니다.

제공 도구:
  - retrieve_grade_criteria: 등급 기준 가이드라인 검색
  - retrieve_guideline:      피드백 작성 가이드라인 검색
"""

import json
from fastmcp import FastMCP
import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DB_DIR

mcp = FastMCP("rag-index-mcp")

# 벡터 스토어 서버와 동일한 ChromaDB 클라이언트와 임베딩 함수를 사용합니다.
# 같은 컬렉션을 공유하므로 일관성이 보장됩니다.
_chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# 가이드라인 문서가 저장된 컬렉션 이름
# init_rag.py에서 동일한 이름으로 저장합니다.
GRADE_CRITERIA_COLLECTION = "grade_criteria"
FEEDBACK_GUIDE_COLLECTION = "feedback_guide"


def _search_collection(collection_name: str, query: str, n_results: int) -> dict:
    """
    지정한 컬렉션에서 쿼리와 유사한 청크를 검색합니다.
    컬렉션이 비어있으면 init_rag.py 실행을 안내합니다.
    """
    try:
        coll = _chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=_embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )

        if coll.count() == 0:
            return {
                "error": f"'{collection_name}' 컬렉션이 비어있습니다. python init_rag.py를 실행해주세요.",
                "query": query,
                "results": []
            }

        results = coll.query(
            query_texts=[query],
            n_results=min(n_results, coll.count()),
            include=["documents", "distances", "metadatas"]
        )

        formatted = []
        for i, (doc, dist, meta) in enumerate(zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0]
        )):
            formatted.append({
                "rank": i + 1,
                "chunk_id": results["ids"][0][i],
                "content": doc,
                "relevance_score": round(1 - dist, 4),
                "source": meta.get("source", ""),
                "section": meta.get("section", ""),
            })

        return {
            "query": query,
            "collection": collection_name,
            "results": formatted,
        }

    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


@mcp.tool()
def retrieve_grade_criteria(query: str, n_results: int = 3) -> str:
    """
    등급 기준 가이드라인(grade_criteria.md)에서 관련 내용을 검색합니다.
    기능3 품질 체크 시 등급-코멘트 일관성 검증에 사용됩니다.

    Args:
        query:     검색 쿼리 (예: "S등급 피드백 기준", "부정적 코멘트 경고")
        n_results: 반환할 최대 청크 수 (기본 3)

    Returns:
        JSON 문자열. 관련 가이드라인 청크 리스트.
    """
    result = _search_collection(GRADE_CRITERIA_COLLECTION, query, n_results)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def retrieve_guideline(query: str, n_results: int = 3) -> str:
    """
    피드백 작성 가이드라인(feedback_guide.md)에서 관련 내용을 검색합니다.
    피드백 초안 생성 및 품질 체크 시 작성 원칙 참고에 사용됩니다.

    Args:
        query:     검색 쿼리 (예: "업적 피드백 작성 기준", "근시성 편향 방지")
        n_results: 반환할 최대 청크 수 (기본 3)

    Returns:
        JSON 문자열. 관련 가이드라인 청크 리스트.
    """
    result = _search_collection(FEEDBACK_GUIDE_COLLECTION, query, n_results)
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
