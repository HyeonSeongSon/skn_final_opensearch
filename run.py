"""
제약회사 문서 검색 시스템 실행 스크립트

main.py의 OpenSearchClient를 사용하여:
1. 기존 인덱스 삭제
2. 새 인덱스 생성 (BGE Reranker 지원)
3. JSONL 파일들에서 문서 로드
4. 문서에 임베딩 벡터 추가
5. OpenSearch에 문서 색인
6. 하이브리드 검색 + BGE Reranker로 상위 3개 문서 추출
"""

from opensearch import OpenSearchClient
import glob
import time
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """메인 실행 함수"""
    print("="*80)
    print("제약회사 문서 검색 시스템 시작")
    print("="*80)
    
    # 1. OpenSearchClient 인스턴스 생성
    print("\n1. OpenSearch 클라이언트 초기화 중...")
    client = OpenSearchClient()
    
    if not client.client:
        print("❌ OpenSearch 연결 실패. 프로그램을 종료합니다.")
        return
    
    # 모델 차원 확인
    vec_dim = len(client.model.encode("dummy_text"))
    print(f"임베딩 모델 차원: {vec_dim}")
    
    # 2. 기존 인덱스 삭제
    print("\n2. 기존 인덱스 삭제 중...")
    client.delete_index("internal_regulations_index")
    
    # 3. 새 인덱스 생성 (BGE Reranker와 코사인 유사도 지원)
    print("\n3. 새 인덱스 생성 중...")
    mapping = {
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
    
    success = client.create_index_with_mapping("internal_regulations_index", mapping)
    if not success:
        print("❌ 인덱스 생성 실패. 프로그램을 종료합니다.")
        return
    
    # 4. JSONL 파일들 자동 탐지 및 로드
    print("\n4. JSONL 파일들에서 문서 로드 중...")
    jsonl_files = glob.glob("*.jsonl")
    print(f"발견된 JSONL 파일들: {jsonl_files}")
    
    if not jsonl_files:
        print("❌ JSONL 파일을 찾을 수 없습니다.")
        return
    
    all_docs = []
    for jsonl_file in jsonl_files:
        print(f"\n처리 중: {jsonl_file}")
        docs = client.load_documents_from_jsonl(jsonl_file)
        print(f"  - 로드된 문서 수: {len(docs)}")
        
        # 5. 각 문서에 임베딩 벡터 생성 및 출처 정보 추가
        for doc in docs:
            text = doc.get("문서내용", "")
            if text:
                # KURE-v1 모델로 임베딩 생성 (1024차원)
                embedding = client.model.encode(text)
                doc["content_vector"] = embedding.tolist()  # type: ignore
            
            # 출처 파일 정보 추가
            doc["출처파일"] = jsonl_file
        
        all_docs.extend(docs)
        print(f"  - 임베딩 완료: {len(docs)}개")
    
    print(f"\n총 처리된 문서 수: {len(all_docs)}")
    
    # 6. OpenSearch에 문서 색인
    print("\n6. OpenSearch에 문서 색인 중...")
    success = client.bulk_index_documents("internal_regulations_index", all_docs, refresh=True)
    
    if not success:
        print("❌ 문서 색인 실패.")
        return
    
    print("✅ 문서 색인 완료!")
    
    # 색인 완료 대기
    print("색인 완료 대기 중...")
    time.sleep(2)
    
    # 7. 색인 검증
    print("\n7. 색인 검증 중...")
    query = {"query": {"match_all": {}}}
    results = client.search_document("internal_regulations_index", query)
    print(f"✅ 전체 색인된 문서 수: {len(results)}개")
    
    # 8. 하이브리드 검색 + BGE Reranker 테스트
    print("\n" + "="*80)
    print("8. 하이브리드 검색 + BGE Reranker 테스트")
    print("="*80)
    
    # 테스트 쿼리
    test_keywords = ["신입사원", "교육", "기간"]
    test_query = "신입사원 교육 기간이 어떻게 돼?"
    
    print(f"\n🔍 검색 쿼리: '{test_query}'")
    print(f"🔍 키워드: {test_keywords}")
    
    # 정규화된 하이브리드 서치 + BGE Reranker로 상위 3개 추출
    final_results = client.normalized_hybrid_search(
        keywords=test_keywords,
        query_text=test_query,
        top_k=10,           # 하이브리드 검색으로 10개 추출
        bm25_weight=0.3,    # BM25 가중치
        vector_weight=0.7,  # 벡터 가중치  
        use_rerank=True,    # BGE Reranker 사용
        rerank_top_k=3      # 최종 상위 3개 출력
    )
    
    if final_results:
        print(f"\n🎯 최종 검색 완료! 상위 {len(final_results)}개 문서를 찾았습니다.")
    else:
        print("\n❌ 검색 결과가 없습니다.")
    
    print("\n" + "="*80)
    print("시스템 실행 완료!")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n프로그램이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류 발생: {e}")
        logging.error(f"예상치 못한 오류: {e}", exc_info=True) 