"""
mcp_servers/vector_store_server.py - 벡터 스토어 MCP 서버

ChromaDB를 사용한 임베딩 저장 및 유사도 검색을 제공합니다.
기능1에서 타임라인 임베딩 저장, 기능3에서 편향 감지에 사용됩니다.

제공 도구:
  - embed_text:        텍스트를 임베딩하여 ChromaDB에 저장
  - similarity_search: 쿼리와 유사한 텍스트 검색
  - store_embedding:   이미 계산된 임베딩을 직접 저장 (배치 처리용)

사용 중인 임베딩 모델: all-MiniLM-L6-v2 (sentence-transformers)
"""

import json
from fastmcp import FastMCP
import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DB_DIR

mcp = FastMCP("vector-store-mcp")

# ─── ChromaDB 클라이언트 초기화 ──────────────────────────────
# 영속성 클라이언트: data/chroma/ 디렉터리에 데이터를 저장합니다.
# 서버가 재시작되어도 이전에 저장한 임베딩이 유지됩니다.
_chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))

# sentence-transformers의 all-MiniLM-L6-v2 모델을 임베딩 함수로 사용합니다.
# 한국어 포함 다국어를 지원하며, 경량 모델이라 빠릅니다.
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def _get_collection(collection_name: str) -> chromadb.Collection:
    """
    컬렉션을 가져오거나 없으면 생성합니다.
    임베딩 함수는 항상 동일한 함수를 사용합니다.
    """
    return _chroma_client.get_or_create_collection(
        name=collection_name,
        embedding_function=_embedding_fn,
        metadata={"hnsw:space": "cosine"}  # 코사인 유사도 사용
    )


@mcp.tool()
def embed_text(
    text: str,
    doc_id: str,
    collection: str = "default",
    metadata: str = "{}"
) -> str:
    """
    텍스트를 임베딩하여 ChromaDB 컬렉션에 저장합니다.

    Args:
        text:       임베딩할 텍스트
        doc_id:     문서 고유 ID (중복 시 덮어씀)
        collection: 저장할 컬렉션 이름 (기본 "default")
        metadata:   JSON 문자열 형태의 메타데이터 (예: '{"emp_id": "E001"}')

    Returns:
        JSON 문자열. 저장 성공 여부와 doc_id.
    """
    try:
        meta = json.loads(metadata) if metadata else {}
        coll = _get_collection(collection)

        # upsert: 같은 ID가 있으면 덮어씁니다.
        coll.upsert(
            documents=[text],
            ids=[doc_id],
            metadatas=[meta]
        )

        return json.dumps({
            "success": True,
            "doc_id": doc_id,
            "collection": collection,
            "text_length": len(text),
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def similarity_search(
    query: str,
    collection: str = "default",
    n_results: int = 5,
    filter_metadata: str = "{}"
) -> str:
    """
    쿼리 텍스트와 유사한 문서를 ChromaDB에서 검색합니다.

    Args:
        query:           검색할 쿼리 텍스트
        collection:      검색할 컬렉션 이름
        n_results:       반환할 최대 결과 수 (기본 5)
        filter_metadata: JSON 문자열 형태의 메타데이터 필터 (예: '{"emp_id": "E001"}')
                         빈 문자열 또는 '{}'이면 필터 없이 전체 검색

    Returns:
        JSON 문자열. 유사 문서 리스트 (id, text, score, metadata 포함).
    """
    try:
        coll = _get_collection(collection)

        # 컬렉션이 비어있는지 확인
        if coll.count() == 0:
            return json.dumps({
                "query": query,
                "collection": collection,
                "results": [],
                "message": "컬렉션이 비어있습니다. init_rag.py를 먼저 실행하세요."
            }, ensure_ascii=False)

        # 메타데이터 필터 파싱
        where_filter = json.loads(filter_metadata) if filter_metadata and filter_metadata != "{}" else None

        # 쿼리 실행
        query_params = {
            "query_texts": [query],
            "n_results": min(n_results, coll.count()),  # 컬렉션 크기 초과 방지
            "include": ["documents", "distances", "metadatas"]
        }
        if where_filter:
            query_params["where"] = where_filter

        results = coll.query(**query_params)

        # 결과를 읽기 좋은 형태로 변환합니다.
        formatted = []
        for i, (doc, dist, meta) in enumerate(zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0]
        )):
            formatted.append({
                "rank": i + 1,
                "doc_id": results["ids"][0][i],
                "text": doc,
                "similarity_score": round(1 - dist, 4),  # 코사인 거리 → 유사도 점수로 변환
                "metadata": meta,
            })

        return json.dumps({
            "query": query,
            "collection": collection,
            "total_in_collection": coll.count(),
            "results": formatted,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e), "query": query}, ensure_ascii=False)


@mcp.tool()
def store_embedding(
    documents: str,
    ids: str,
    collection: str = "default",
    metadatas: str = "[]"
) -> str:
    """
    여러 문서를 한 번에 ChromaDB에 저장합니다. (배치 처리용)

    Args:
        documents:  JSON 문자열 형태의 텍스트 리스트 (예: '["text1", "text2"]')
        ids:        JSON 문자열 형태의 ID 리스트 (예: '["id1", "id2"]')
        collection: 저장할 컬렉션 이름
        metadatas:  JSON 문자열 형태의 메타데이터 리스트 (예: '[{"key": "val"}]')

    Returns:
        JSON 문자열. 저장된 문서 수와 성공 여부.
    """
    try:
        docs = json.loads(documents)
        doc_ids = json.loads(ids)
        metas = json.loads(metadatas) if metadatas else [{}] * len(docs)

        # 길이 검증
        if len(docs) != len(doc_ids):
            return json.dumps({"success": False, "error": "documents와 ids의 길이가 다릅니다."}, ensure_ascii=False)

        # 메타데이터 길이 맞추기
        if len(metas) != len(docs):
            metas = [{}] * len(docs)

        coll = _get_collection(collection)
        coll.upsert(documents=docs, ids=doc_ids, metadatas=metas)

        return json.dumps({
            "success": True,
            "stored_count": len(docs),
            "collection": collection,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
