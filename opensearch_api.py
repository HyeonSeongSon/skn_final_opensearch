"""
제약회사 문서 검색 시스템 FastAPI 서버 (run2.py)

기존 run.py의 기능을 FastAPI로 구현:
1. OpenSearchClient를 사용한 인덱스 관리
2. JSONL 파일들에서 문서 로드 및 색인
3. 하이브리드 검색 + BGE Reranker API 제공
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from opensearch import OpenSearchClient
import glob
import time
import logging
import asyncio
import numpy as np
from contextlib import asynccontextmanager

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 전역 OpenSearchClient 인스턴스
opensearch_client: Optional[OpenSearchClient] = None

# Pydantic 모델 정의
class SearchRequest(BaseModel):
    """검색 요청 모델"""
    keywords: List[str] = Field(..., description="검색 키워드 리스트")
    query_text: str = Field(..., description="검색 쿼리 텍스트")
    index_name: str = Field(default="internal_regulations_index", description="검색할 인덱스명")
    top_k: int = Field(default=10, description="하이브리드 검색 결과 수", ge=1, le=50)
    bm25_weight: float = Field(default=0.3, description="BM25 가중치", ge=0.0, le=1.0)
    vector_weight: float = Field(default=0.7, description="벡터 가중치", ge=0.0, le=1.0)
    use_rerank: bool = Field(default=True, description="BGE Reranker 사용 여부")
    rerank_top_k: int = Field(default=3, description="최종 결과 수", ge=1, le=10)

class SearchResponse(BaseModel):
    """검색 응답 모델"""
    success: bool
    message: str
    results: List[Dict[str, Any]]
    total_count: int
    query_info: Dict[str, Any]

class InitializeRequest(BaseModel):
    """초기화 요청 모델"""
    index_name: str = Field(default="internal_regulations_index", description="인덱스 명")
    recreate_index: bool = Field(default=True, description="기존 인덱스 삭제 후 재생성 여부")

class InitializeResponse(BaseModel):
    """초기화 응답 모델"""
    success: bool
    message: str
    indexed_documents: int
    jsonl_files: List[str]
    embedding_dimension: int

class IndexRequest(BaseModel):
    """인덱스 요청 모델"""
    index_name: str = Field(..., description="인덱스 명")
    mapping: Dict[str, Any] = Field(..., description="인덱스 매핑 (필수)")

class DocumentLoadRequest(BaseModel):
    """문서 로드 요청 모델"""
    index_name: str = Field(default="internal_regulations_index", description="인덱스 명")
    jsonl_pattern: str = Field(default="data/*.jsonl", description="JSONL 파일 패턴")

class SingleDocumentRequest(BaseModel):
    """단일 문서 색인 요청 모델"""
    index_name: str = Field(..., description="색인할 인덱스 명")
    document: Dict[str, Any] = Field(..., description="색인할 문서 데이터")
    refresh: bool = Field(default=False, description="색인 후 즉시 반영 여부")

# OpenSearchClient 초기화 함수
async def initialize_opensearch_client():
    """OpenSearchClient 초기화"""
    global opensearch_client
    logger.info("OpenSearch 클라이언트 초기화 중...")
    opensearch_client = OpenSearchClient()
    
    if not opensearch_client.client:
        logger.error("OpenSearch 연결 실패")
        raise Exception("OpenSearch 연결 실패")
    
    logger.info("OpenSearch 클라이언트 초기화 완료")

# FastAPI 애플리케이션 라이프사이클 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 실행
    await initialize_opensearch_client()
    yield
    # 종료 시 실행
    logger.info("애플리케이션 종료")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="제약회사 문서 검색 시스템 API",
    description="OpenSearch와 BGE Reranker를 사용한 하이브리드 검색 시스템 (run.py 기반)",
    version="2.0.0",
    lifespan=lifespan
)

@app.get("/", summary="API 정보")
async def root():
    """API 기본 정보 및 사용법"""
    return {
        "title": "제약회사 문서 검색 시스템 API",
        "description": "기존 run.py의 기능을 FastAPI로 구현",
        "version": "2.0.0",
        "data_location": "JSONL 파일들은 data/ 폴더에 위치해야 합니다",
        "endpoints": {
            "health": "GET /health - 시스템 상태 확인",
            "initialize": "POST /initialize - 시스템 전체 초기화 (run.py의 main() 함수와 동일)",
            "search": "POST /search - 하이브리드 검색 (normalized_hybrid_search)",
            "test_search": "POST /test-search - 테스트 검색 (run.py 예제와 동일)",
            "create_index": "POST /index/create - 새 인덱스 생성 (매핑 필수)",
            "delete_index": "DELETE /index/{index_name} - 인덱스 삭제",
            "index_document": "POST /document/index - 단일 문서 색인 (index_document)",
            "load_documents": "POST /documents/load - 문서 로드 및 색인 (bulk_index_documents)",
            "index_stats": "GET /index/{index_name}/stats - 인덱스 통계",
            "mapping_examples": "GET /mapping/examples - 매핑 예제 조회 (인덱스 생성 시 참고)",
            "docs": "GET /docs - API 문서 (Swagger UI)"
        },
        "usage": {
            "1": "data/ 폴더에 JSONL 파일들을 준비",
            "2": "POST /initialize로 시스템 초기화 또는 개별 함수 사용",
            "3": "POST /search로 문서 검색",
            "4": "GET /health로 시스템 상태 확인"
        }
    }

@app.get("/health", summary="시스템 상태 확인")
async def health_check():
    """OpenSearch 연결 상태 및 시스템 정보 확인"""
    if opensearch_client and opensearch_client.client:
        try:
            # OpenSearch 연결 상태 확인
            ping_result = opensearch_client.client.ping()
            
            # 임베딩 모델 정보
            vec_dim = None
            if hasattr(opensearch_client, 'model'):
                try:
                    vec_dim = len(opensearch_client.model.encode("test"))
                except:
                    vec_dim = "unknown"
            
            return {
                "status": "healthy" if ping_result else "unhealthy",
                "opensearch_connected": ping_result,
                "embedding_dimension": vec_dim,
                "message": "시스템이 정상 작동 중입니다." if ping_result else "OpenSearch 연결 실패",
                "timestamp": time.time()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "opensearch_connected": False,
                "error": str(e),
                "message": f"OpenSearch 연결 오류: {str(e)}"
            }
    else:
        return {
            "status": "unhealthy", 
            "opensearch_connected": False,
            "message": "OpenSearch 클라이언트가 초기화되지 않았습니다."
        }

@app.post("/search", response_model=SearchResponse, summary="하이브리드 검색 + BGE Reranker")
async def search_documents(request: SearchRequest):
    """
    run.py의 normalized_hybrid_search와 동일한 기능:
    - 하이브리드 검색 (BM25 + 벡터 유사도)
    - BGE Reranker로 결과 재정렬
    - 상위 N개 문서 반환
    """
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        logger.info("="*80)
        logger.info("하이브리드 검색 + BGE Reranker 실행")
        logger.info("="*80)
        logger.info(f"검색 쿼리: '{request.query_text}'")
        logger.info(f"키워드: {request.keywords}")
        
        # run.py와 동일한 정규화된 하이브리드 검색 실행
        final_results = opensearch_client.normalized_hybrid_search(
            keywords=request.keywords,
            query_text=request.query_text,
            index_name=request.index_name,      # 검색할 인덱스명
            top_k=request.top_k,           # 하이브리드 검색으로 N개 추출
            bm25_weight=request.bm25_weight,    # BM25 가중치
            vector_weight=request.vector_weight,  # 벡터 가중치  
            use_rerank=request.use_rerank,    # BGE Reranker 사용
            rerank_top_k=request.rerank_top_k      # 최종 상위 N개 출력
        )
        
        query_info = {
            "keywords": request.keywords,
            "query_text": request.query_text,
            "search_params": {
                "top_k": request.top_k,
                "bm25_weight": request.bm25_weight,
                "vector_weight": request.vector_weight,
                "use_rerank": request.use_rerank,
                "rerank_top_k": request.rerank_top_k
            }
        }
        
        if final_results:
            logger.info(f"최종 검색 완료! 상위 {len(final_results)}개 문서를 찾았습니다.")
            return SearchResponse(
                success=True,
                message=f"검색이 완료되었습니다. 상위 {len(final_results)}개의 관련 문서를 찾았습니다.",
                results=final_results,
                total_count=len(final_results),
                query_info=query_info
            )
        else:
            logger.info("검색 결과가 없습니다.")
            return SearchResponse(
                success=True,
                message="검색 결과가 없습니다.",
                results=[],
                total_count=0,
                query_info=query_info
            )
            
    except Exception as e:
        logger.error(f"검색 오류: {e}")
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")

@app.post("/test-search", summary="테스트 검색")
async def test_search():
    """run.py에서 사용한 테스트 쿼리와 동일한 검색 수행"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    # run.py의 테스트 쿼리와 동일
    test_keywords = ["신입사원", "교육", "기간"]
    test_query = "신입사원 교육 기간이 어떻게 돼?"
    
    request = SearchRequest(
        keywords=test_keywords,
        query_text=test_query,
        top_k=10,
        bm25_weight=0.3,
        vector_weight=0.7,
        use_rerank=True,
        rerank_top_k=3
    )
    
    return await search_documents(request)

@app.post("/index/create", summary="인덱스 생성")
async def create_index(request: IndexRequest):
    """새 인덱스 생성 (매핑 필수 입력)"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        vec_dim = len(opensearch_client.model.encode("dummy_text"))
        
        # 사용자가 제공한 매핑 사용 (필수)
        mapping = request.mapping
        logger.info(f"사용자 제공 매핑 사용: {request.index_name}")
        
        # 매핑 검증 (기본적인 구조 확인)
        if "mappings" not in mapping and "settings" not in mapping:
            raise HTTPException(
                status_code=400, 
                detail="매핑에 'mappings' 또는 'settings' 필드가 필요합니다."
            )
        
        success = opensearch_client.create_index_with_mapping(request.index_name, mapping)
        
        if success:
            return {
                "success": True, 
                "message": f"인덱스 '{request.index_name}'가 성공적으로 생성되었습니다.",
                "embedding_dimension": vec_dim,
                "used_mapping": mapping
            }
        else:
            raise HTTPException(status_code=500, detail="인덱스 생성 실패")
            
    except Exception as e:
        logger.error(f"인덱스 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"인덱스 생성 실패: {str(e)}")

@app.delete("/index/{index_name}", summary="인덱스 삭제")
async def delete_index(index_name: str):
    """지정된 인덱스 삭제"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        opensearch_client.delete_index(index_name)
        return {
            "success": True, 
            "message": f"인덱스 '{index_name}'가 삭제되었습니다."
        }
        
    except Exception as e:
        logger.error(f"인덱스 삭제 오류: {e}")
        raise HTTPException(status_code=500, detail=f"인덱스 삭제 실패: {str(e)}")

@app.post("/document/index", summary="단일 문서 색인")
async def index_single_document(request: SingleDocumentRequest):
    """단일 문서를 지정된 인덱스에 색인 (opensearch.py의 index_document 함수)"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        logger.info(f"단일 문서 색인 시작: {request.index_name}")
        
        # opensearch.py의 index_document 함수 호출
        result = opensearch_client.index_document(
            index_name=request.index_name,
            document=request.document,
            refresh=request.refresh
        )
        
        if result:
            return {
                "success": True,
                "message": f"문서가 인덱스 '{request.index_name}'에 성공적으로 색인되었습니다.",
                "document_id": result.get("_id"),
                "index_name": result.get("_index"),
                "result": result.get("result"),
                "opensearch_response": result
            }
        else:
            raise HTTPException(status_code=500, detail="문서 색인에 실패했습니다.")
            
    except Exception as e:
        logger.error(f"단일 문서 색인 오류: {e}")
        raise HTTPException(status_code=500, detail=f"단일 문서 색인 실패: {str(e)}")

@app.post("/documents/load", summary="문서 로드 및 색인")
async def load_documents(request: DocumentLoadRequest):
    """JSONL 파일들에서 문서를 로드하고 색인 (run.py 로직과 동일)"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        jsonl_files = glob.glob(request.jsonl_pattern)
        if not jsonl_files:
            raise HTTPException(
                status_code=404, 
                detail=f"패턴 '{request.jsonl_pattern}'에 맞는 JSONL 파일을 찾을 수 없습니다."
            )
        
        all_docs = []
        for jsonl_file in jsonl_files:
            logger.info(f"처리 중: {jsonl_file}")
            docs = opensearch_client.load_documents_from_jsonl(jsonl_file)
            
            # run.py와 동일한 임베딩 생성 및 출처 정보 추가
            for doc in docs:
                text = doc.get("문서내용", "")
                if text:
                    embedding = opensearch_client.model.encode(text)
                    doc["content_vector"] = np.array(embedding).tolist()
                doc["출처파일"] = jsonl_file
            
            all_docs.extend(docs)
            logger.info(f"완료: {jsonl_file} - {len(docs)}개 문서")
        
        # 문서 색인
        success = opensearch_client.bulk_index_documents(request.index_name, all_docs, refresh=True)
        
        if success:
            # 색인 완료 후 상위 3개 문서 조회
            logger.info("색인 완료 후 상위 3개 문서를 조회합니다...")
            
            # 상위 3개 문서 조회
            sample_docs = []
            for i, doc in enumerate(all_docs[:3], 1):
                sample_doc = doc.copy()
                
                # 벡터값은 앞에 5개만 표시
                if "content_vector" in sample_doc and isinstance(sample_doc["content_vector"], list):
                    vector_preview = sample_doc["content_vector"][:5]
                    sample_doc["content_vector"] = f"[{', '.join(map(str, vector_preview))}...] (총 {len(sample_doc['content_vector'])}차원)"
                
                # 문서내용은 100자로 제한
                if "문서내용" in sample_doc:
                    content = sample_doc["문서내용"]
                    if len(content) > 100:
                        sample_doc["문서내용"] = content[:100] + "..."
                
                sample_docs.append({
                    "순번": i,
                    "문서명": sample_doc.get("문서명", "N/A"),
                    "장": sample_doc.get("장", "N/A"),
                    "조": sample_doc.get("조", "N/A"),
                    "문서내용": sample_doc.get("문서내용", "N/A"),
                    "출처파일": sample_doc.get("출처파일", "N/A"),
                    "content_vector": sample_doc.get("content_vector", "N/A")
                })
            
            return {
                "success": True,
                "message": f"{len(all_docs)}개 문서가 성공적으로 색인되었습니다.",
                "indexed_documents": len(all_docs),
                "jsonl_files": jsonl_files,
                "sample_documents": sample_docs
            }
        else:
            raise HTTPException(status_code=500, detail="문서 색인 실패")
            
    except Exception as e:
        logger.error(f"문서 로드 오류: {e}")
        raise HTTPException(status_code=500, detail=f"문서 로드 실패: {str(e)}")

@app.get("/index/{index_name}/stats", summary="인덱스 통계")
async def get_index_stats(index_name: str):
    """인덱스의 문서 수 및 통계 정보"""
    if not opensearch_client:
        raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
    
    try:
        query = {"query": {"match_all": {}}}
        results = opensearch_client.search_document(index_name, query)
        
        return {
            "index_name": index_name,
            "total_documents": len(results),
            "message": f"인덱스 '{index_name}'에 {len(results)}개의 문서가 있습니다."
        }
        
    except Exception as e:
        logger.error(f"인덱스 통계 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=f"인덱스 통계 조회 실패: {str(e)}")

@app.get("/mapping/examples", summary="매핑 예제 조회")
async def get_mapping_examples():
    """
    제약회사 문서 검색 시스템에 최적화된 매핑 예제들을 반환합니다.
    인덱스 생성 시 참고할 수 있는 3가지 매핑 예제를 제공합니다.
    """
    vec_dim = 1024  # 벡터 차원 설정
    
    examples = {
        "1": {
            "name": "제약회사 문서 기본 매핑 (벡터 검색 없음)",
            "description": "벡터 검색 없이 기본적인 텍스트 검색만 지원하는 매핑",
            "mapping": {
                "settings": {
                    "index": {
                        "knn": False  # k-NN 검색 비활성화
                    }
                },
                "mappings": {
                    "properties": {
                        "문서명":    { "type": "keyword" },  # 정확한 문서명 매칭
                        "장":      { "type": "text" },      # 전문 검색 가능
                        "조":      { "type": "text" },      # 전문 검색 가능
                        "문서내용":  { "type": "text" },      # 전문 검색 가능
                        "출처파일":  { "type": "keyword" }    # 정확한 파일명 매칭
                    }
                }
            }
        },
        "2": {
            "name": "제약회사 문서 벡터 검색 지원 매핑 (권장)",
            "description": "하이브리드 검색(BM25 + 벡터)을 지원하는 권장 매핑",
            "mapping": {
                "settings": {
                    "index": {
                        "knn": True  # k-NN 검색 활성화
                    }
                },
                "mappings": {
                    "properties": {
                        "문서명":    { "type": "keyword" },  # 정확한 문서명 매칭
                        "장":      { "type": "text" },      # 전문 검색 가능
                        "조":      { "type": "text" },      # 전문 검색 가능
                        "문서내용":  { "type": "text" },      # 전문 검색 가능
                        "출처파일":  { "type": "keyword" },   # 정확한 파일명 매칭
                        "content_vector": {
                            "type": "knn_vector",           # 벡터 유사도 검색용
                            "dimension": vec_dim,
                            "method": {
                                "name": "hnsw",             # Hierarchical Navigable Small World
                                "space_type": "cosinesimil", # 코사인 유사도 사용
                                "engine": "lucene"          # 검색 엔진 (nmslib deprecated)
                            }
                        }
                    }
                }
            }
        },
        "3": {
            "name": "제약회사 문서 완전 매핑 (추가 필드 포함)",
            "description": "벡터 검색 + 추가 메타데이터 필드를 포함한 완전한 매핑",
            "mapping": {
                "settings": {
                    "index": {
                        "knn": True  # k-NN 검색 활성화
                    }
                },
                "mappings": {
                    "properties": {
                        "문서명":    { "type": "keyword" },  # 정확한 문서명 매칭
                        "장":      { "type": "text" },      # 전문 검색 가능
                        "조":      { "type": "text" },      # 전문 검색 가능
                        "문서내용":  { "type": "text" },      # 전문 검색 가능
                        "출처파일":  { "type": "keyword" },   # 정확한 파일명 매칭
                        "카테고리":  { "type": "keyword" },   # 문서 분류
                        "생성일시":  { "type": "date" },      # 문서 생성 일시
                        "수정일시":  { "type": "date" },      # 문서 수정 일시
                        "태그":     { "type": "keyword" },   # 문서 태그
                        "content_vector": {
                            "type": "knn_vector",           # 벡터 유사도 검색용
                            "dimension": vec_dim,
                            "method": {
                                "name": "hnsw",             # Hierarchical Navigable Small World
                                "space_type": "cosinesimil", # 코사인 유사도 사용
                                "engine": "lucene"          # 검색 엔진 (nmslib deprecated)
                            }
                        }
                    }
                }
            }
        }
    }
    
    return {
        "success": True,
        "message": "매핑 예제들이 성공적으로 조회되었습니다.",
        "vector_dimension": vec_dim,
        "total_examples": len(examples),
        "examples": examples,
        "usage_tip": "인덱스 생성 시 'mapping' 필드에 이 예제들을 사용하세요. 2번 예제가 권장됩니다."
    }

if __name__ == "__main__":
    import uvicorn
    print("="*80)
    print("제약회사 문서 검색 시스템 FastAPI 서버 시작 (run2.py)")
    print("기존 run.py의 모든 기능을 API로 제공")
    print("JSONL 파일들은 data 폴더에서 읽어옵니다.")
    print("="*80)
    print("API 문서: http://localhost:8000/docs")
    print("헬스 체크: http://localhost:8000/health")
    print("="*80)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 