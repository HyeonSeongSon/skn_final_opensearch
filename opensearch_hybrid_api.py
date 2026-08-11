from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Union, Optional
import json
import logging
from opensearch_hybrid import OpenSearchHybridClient

# FastAPI 앱 생성
app = FastAPI(
    title="OpenSearch Hybrid Search API",
    description="OpenSearch 3.0+ Search Pipeline 기반 하이브리드 검색 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenSearch 클라이언트 초기화
client = None

@app.on_event("startup")
async def startup_event():
    global client
    client = OpenSearchHybridClient()
    logging.info("OpenSearch Hybrid Client 초기화 완료")

# Pydantic 모델 정의
class SearchRequest(BaseModel):
    query_text: str
    keywords: Optional[Union[str, List[str]]] = None
    pipeline_id: str = "hybrid-minmax-pipeline"
    index_name: str = "pharma_test_index"
    top_k: int = 10
    use_rerank: bool = True
    rerank_top_k: int = 3

class KeywordExtractionRequest(BaseModel):
    user_input: str

class IndexRequest(BaseModel):
    index_name: str
    document: dict
    refresh: bool = False

class BulkIndexRequest(BaseModel):
    index_name: str
    documents: List[dict]
    refresh: bool = False

class IndexMappingRequest(BaseModel):
    index_name: str
    mapping: dict

class PipelineRequest(BaseModel):
    pipeline_id: str = "hybrid-minmax-pipeline"

class JSONLLoadRequest(BaseModel):
    file_path: str

class JSONLPatternLoadRequest(BaseModel):
    jsonl_pattern: str = "data/*.jsonl"

class RerankRequest(BaseModel):
    query_text: str
    documents: List[dict]
    top_k: int = 3

class SearchResponse(BaseModel):
    success: bool
    results: List[dict]
    total_count: int
    message: Optional[str] = None

class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

# API 엔드포인트 구현

@app.get("/", response_model=dict)
async def root():
    """API 상태 확인"""
    return {
        "message": "OpenSearch Hybrid Search API",
        "status": "running",
        "version": "1.0.0"
    }

@app.post("/search", response_model=SearchResponse)
async def search_with_pipeline(request: SearchRequest):
    """Search Pipeline을 사용한 하이브리드 검색"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        results = client.search_with_pipeline(
            query_text=request.query_text,
            keywords=request.keywords,
            pipeline_id=request.pipeline_id,
            index_name=request.index_name,
            top_k=request.top_k,
            use_rerank=request.use_rerank,
            rerank_top_k=request.rerank_top_k
        )
        
        return SearchResponse(
            success=True,
            results=results,
            total_count=len(results),
            message="검색이 성공적으로 완료되었습니다."
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")

@app.post("/extract-keywords", response_model=StandardResponse)
async def extract_keywords(request: KeywordExtractionRequest):
    """LLM을 사용한 키워드 추출"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        # LLM에서 키워드 추출
        raw_keywords = client.get_keyword(request.user_input)
        
        # 키워드 파싱 및 정리
        parsed_keywords = parse_keywords(raw_keywords)
        
        return StandardResponse(
            success=True,
            message="키워드 추출이 성공적으로 완료되었습니다.",
            data={"keywords": parsed_keywords, "raw_response": raw_keywords}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"키워드 추출 중 오류 발생: {str(e)}")

def parse_keywords(keywords_str: str) -> list:
    """LLM 응답에서 키워드 리스트 파싱"""
    import re
    import ast
    
    if not keywords_str:
        return []
    
    # 문자열 정리
    cleaned = keywords_str.strip()
    
    try:
        # 1. JSON/Python 리스트 형태인 경우
        if cleaned.startswith('[') and cleaned.endswith(']'):
            # ast.literal_eval로 파싱 시도
            try:
                return ast.literal_eval(cleaned)
            except:
                # 정규표현식으로 따옴표 안의 문자열 추출
                matches = re.findall(r'["\']([^"\']+)["\']', cleaned)
                return matches if matches else []
        
        # 2. 따옴표로 둘러싸인 리스트 형태인 경우 ["키워드1", "키워드2"]
        quotes_matches = re.findall(r'["\']([^"\']+)["\']', cleaned)
        if quotes_matches:
            return quotes_matches
        
        # 3. 쉼표로 구분된 경우
        if ',' in cleaned:
            keywords = [k.strip().strip('"\'') for k in cleaned.split(',')]
            return [k for k in keywords if k]
        
        # 4. 단일 키워드인 경우
        return [cleaned.strip('"\'')]
        
    except Exception:
        # 파싱 실패시 기본 분할
        return [k.strip().strip('"\'[]') for k in cleaned.replace('[', '').replace(']', '').split(',') if k.strip()]

@app.post("/rerank", response_model=SearchResponse)
async def rerank_documents(request: RerankRequest):
    """BGE Reranker를 사용한 문서 리랭킹"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        results = client.rerank_documents(
            query_text=request.query_text,
            documents=request.documents,
            top_k=request.top_k
        )
        
        return SearchResponse(
            success=True,
            results=results,
            total_count=len(results),
            message="리랭킹이 성공적으로 완료되었습니다."
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리랭킹 중 오류 발생: {str(e)}")

@app.post("/pipeline/create", response_model=StandardResponse)
async def create_search_pipeline(request: PipelineRequest):
    """Search Pipeline 생성"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        success = client.create_search_pipeline(request.pipeline_id)
        
        if success:
            return StandardResponse(
                success=True,
                message=f"Search pipeline '{request.pipeline_id}'가 성공적으로 생성되었습니다."
            )
        else:
            raise HTTPException(status_code=500, detail="Search pipeline 생성에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline 생성 중 오류 발생: {str(e)}")

@app.get("/pipeline/{pipeline_id}", response_model=StandardResponse)
async def get_search_pipeline(pipeline_id: str):
    """Search Pipeline 정보 조회"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        pipeline_info = client.get_search_pipeline(pipeline_id)
        
        if pipeline_info:
            return StandardResponse(
                success=True,
                message="Pipeline 정보가 성공적으로 조회되었습니다.",
                data=pipeline_info
            )
        else:
            raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}'를 찾을 수 없습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline 조회 중 오류 발생: {str(e)}")

@app.delete("/pipeline/{pipeline_id}", response_model=StandardResponse)
async def delete_search_pipeline(pipeline_id: str):
    """Search Pipeline 삭제"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        success = client.delete_search_pipeline(pipeline_id)
        
        if success:
            return StandardResponse(
                success=True,
                message=f"Search pipeline '{pipeline_id}'가 성공적으로 삭제되었습니다."
            )
        else:
            raise HTTPException(status_code=500, detail="Search pipeline 삭제에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline 삭제 중 오류 발생: {str(e)}")

@app.delete("/index/{index_name}", response_model=StandardResponse)
async def delete_index(index_name: str):
    """인덱스 삭제"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        client.delete_index(index_name)
        
        return StandardResponse(
            success=True,
            message=f"인덱스 '{index_name}'가 성공적으로 삭제되었습니다."
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"인덱스 삭제 중 오류 발생: {str(e)}")

@app.post("/index/document", response_model=StandardResponse)
async def index_document(request: IndexRequest):
    """단일 문서 임베딩 생성 및 색인"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        # 문서 복사본 생성 (원본 변경 방지)
        document = request.document.copy()
        
        # 임베딩 생성 (벡터DB이므로 무조건 포함)
        content = f"{document.get('문서명', '')} {document.get('장', '')} {document.get('조', '')} {document.get('문서내용', '')}"
        
        if hasattr(client, 'model') and client.model:
            document['content_vector'] = client.model.encode(content).tolist()
        
        result = client.index_document(
            index_name=request.index_name,
            document=document,
            refresh=request.refresh
        )
        
        if result:
            return StandardResponse(
                success=True,
                message="문서가 임베딩과 함께 성공적으로 색인되었습니다.",
                data={
                    "document_id": result.get("_id"),
                    "vector_dimension": len(document.get('content_vector', [])),
                    "has_embedding": 'content_vector' in document
                }
            )
        else:
            raise HTTPException(status_code=500, detail="문서 색인에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 색인 중 오류 발생: {str(e)}")

@app.post("/index/bulk", response_model=StandardResponse)
async def bulk_index_documents(request: BulkIndexRequest):
    """여러 문서 임베딩 생성 및 일괄 색인"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        # 모든 문서에 임베딩 생성 (벡터DB이므로 무조건 포함)
        documents_with_embeddings = []
        embedded_count = 0
        
        for doc in request.documents:
            # 문서 복사본 생성 (원본 변경 방지)
            document = doc.copy()
            
            # 임베딩 생성
            content = f"{document.get('문서명', '')} {document.get('장', '')} {document.get('조', '')} {document.get('문서내용', '')}"
            
            if hasattr(client, 'model') and client.model:
                document['content_vector'] = client.model.encode(content).tolist()
                embedded_count += 1
            
            documents_with_embeddings.append(document)
        
        success = client.bulk_index_documents(
            index_name=request.index_name,
            documents=documents_with_embeddings,
            refresh=request.refresh
        )
        
        if success:
            return StandardResponse(
                success=True,
                message=f"{len(documents_with_embeddings)}개 문서가 임베딩과 함께 성공적으로 일괄 색인되었습니다.",
                data={
                    "total_documents": len(documents_with_embeddings),
                    "embedded_documents": embedded_count,
                    "vector_dimension": 1024 if embedded_count > 0 else 0
                }
            )
        else:
            raise HTTPException(status_code=500, detail="일괄 색인에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"일괄 색인 중 오류 발생: {str(e)}")

@app.post("/index/create", response_model=StandardResponse)
async def create_index_with_mapping(request: IndexMappingRequest):
    """매핑과 함께 인덱스 생성"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        success = client.create_index_with_mapping(
            index_name=request.index_name,
            mapping=request.mapping
        )
        
        if success:
            return StandardResponse(
                success=True,
                message=f"인덱스 '{request.index_name}'가 성공적으로 생성되었습니다."
            )
        else:
            raise HTTPException(status_code=500, detail="인덱스 생성에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"인덱스 생성 중 오류 발생: {str(e)}")

@app.post("/load-jsonl", response_model=StandardResponse)
async def load_documents_from_jsonl(request: JSONLLoadRequest):
    """단일 JSONL 파일에서 문서 로드 (색인 없음)"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        documents = client.load_documents_from_jsonl(request.file_path)
        
        return StandardResponse(
            success=True,
            message=f"JSONL 파일에서 {len(documents)}개 문서를 성공적으로 로드했습니다.",
            data={"documents_count": len(documents), "documents": documents}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSONL 로드 중 오류 발생: {str(e)}")

@app.post("/load-jsonl-pattern", response_model=StandardResponse)
async def load_documents_from_jsonl_pattern(request: JSONLPatternLoadRequest):
    """여러 JSONL 파일들에서 문서 로드 (색인 없음)"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        import glob
        
        # JSONL 파일 패턴으로 파일 목록 가져오기
        jsonl_files = glob.glob(request.jsonl_pattern)
        
        if not jsonl_files:
            raise HTTPException(status_code=404, detail=f"패턴 '{request.jsonl_pattern}'에 해당하는 JSONL 파일을 찾을 수 없습니다.")
        
        all_documents = []
        
        for jsonl_file in jsonl_files:
            # JSONL 파일에서 문서 로드
            documents = client.load_documents_from_jsonl(jsonl_file)
            all_documents.extend(documents)
        
        return StandardResponse(
            success=True,
            message=f"{len(jsonl_files)}개 JSONL 파일에서 총 {len(all_documents)}개 문서를 성공적으로 로드했습니다.",
            data={
                "total_documents": len(all_documents),
                "jsonl_files": jsonl_files,
                "documents": all_documents
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSONL 패턴 로드 중 오류 발생: {str(e)}")

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


@app.get("/index/{index_name}/stats", response_model=StandardResponse)
async def get_index_stats(index_name: str):
    """인덱스 통계 정보 조회"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        # 인덱스 존재 확인
        if not client.client.indices.exists(index=index_name):
            raise HTTPException(status_code=404, detail=f"인덱스 '{index_name}'가 존재하지 않습니다.")
        
        # 인덱스 통계 조회
        stats_response = client.client.indices.stats(index=index_name)
        index_stats = stats_response['indices'][index_name]
        
        # 문서 수 조회
        count_response = client.client.count(index=index_name)
        total_documents = count_response['count']
        
        # 인덱스 매핑 정보 조회
        mapping_response = client.client.indices.get_mapping(index=index_name)
        mapping_info = mapping_response[index_name]['mappings']
        
        # 벡터 차원 정보 추출
        vector_dimension = None
        if 'properties' in mapping_info:
            content_vector = mapping_info['properties'].get('content_vector', {})
            if content_vector.get('type') == 'knn_vector':
                vector_dimension = content_vector.get('dimension')
        
        return StandardResponse(
            success=True,
            message=f"인덱스 '{index_name}' 통계가 성공적으로 조회되었습니다.",
            data={
                "index_name": index_name,
                "total_documents": total_documents,
                "vector_dimension": vector_dimension,
                "index_size_bytes": index_stats['total']['store']['size_in_bytes'],
                "shard_count": index_stats['total']['segments']['count'],
                "has_vector_field": vector_dimension is not None
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"인덱스 통계 조회 중 오류 발생: {str(e)}")

@app.get("/health", response_model=dict)
async def health_check():
    """서비스 헬스체크"""
    try:
        if not client or not client.client:
            return {"status": "unhealthy", "message": "OpenSearch 클라이언트가 초기화되지 않았습니다."}
        
        if client.client.ping():
            return {"status": "healthy", "message": "OpenSearch 연결이 정상입니다."}
        else:
            return {"status": "unhealthy", "message": "OpenSearch 연결에 실패했습니다."}
    
    except Exception as e:
        return {"status": "unhealthy", "message": f"헬스체크 중 오류 발생: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)