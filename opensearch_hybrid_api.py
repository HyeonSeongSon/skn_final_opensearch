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
        
        keywords = client.get_keyword(request.user_input)
        
        return StandardResponse(
            success=True,
            message="키워드 추출이 성공적으로 완료되었습니다.",
            data={"keywords": keywords}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"키워드 추출 중 오류 발생: {str(e)}")

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
    """단일 문서 색인"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        result = client.index_document(
            index_name=request.index_name,
            document=request.document,
            refresh=request.refresh
        )
        
        if result:
            return StandardResponse(
                success=True,
                message="문서가 성공적으로 색인되었습니다.",
                data=result
            )
        else:
            raise HTTPException(status_code=500, detail="문서 색인에 실패했습니다.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 색인 중 오류 발생: {str(e)}")

@app.post("/index/bulk", response_model=StandardResponse)
async def bulk_index_documents(request: BulkIndexRequest):
    """여러 문서 일괄 색인"""
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenSearch 클라이언트가 초기화되지 않았습니다.")
        
        success = client.bulk_index_documents(
            index_name=request.index_name,
            documents=request.documents,
            refresh=request.refresh
        )
        
        if success:
            return StandardResponse(
                success=True,
                message=f"{len(request.documents)}개 문서가 성공적으로 일괄 색인되었습니다."
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
    """JSONL 파일에서 문서 로드"""
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