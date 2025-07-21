"""
제약회사 문서 검색 시스템 FastAPI 사용 예시 코드

이 파일은 PharmaTech Document Search System의 FastAPI 서버(8010포트)를 
사용하는 방법을 보여주는 예시 코드입니다.

주요 API 엔드포인트 사용법:
- GET /health: 시스템 상태 확인
- GET /mapping/examples: 매핑 예제 조회
- POST /index/create: 인덱스 생성
- POST /documents/load: 문서 로드 및 색인
- GET /index/{index_name}/stats: 인덱스 통계 조회
- POST /search: 하이브리드 검색 수행

사용 전 준비사항:
1. docker-compose up -d 실행
2. FastAPI 서버 실행: python opensearch_api.py
3. data/ 폴더에 JSONL 파일 준비
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Optional

class PharmSearchAPIExample:
    """제약회사 문서 검색 API 사용 예시 클래스"""
    
    def __init__(self, base_url: str = "http://localhost:8010"):
        """
        API 클라이언트 초기화
        
        Args:
            base_url: FastAPI 서버 URL (기본값: http://localhost:8010)
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.index_name = "pharma_test_index"
        
    def print_step(self, step_num: int, title: str):
        """단계별 제목 출력"""
        print(f"\n{'='*80}")
        print(f"🔷 예시 {step_num}: {title}")
        print(f"{'='*80}")
    
    def print_result(self, success: bool, message: str, data: Optional[Dict] = None):
        """
        API 응답 결과를 보기 좋게 출력
        
        Args:
            success: 성공 여부
            message: 결과 메시지
            data: 응답 데이터 (선택사항)
        """
        status = "✅ 성공" if success else "❌ 실패"
        print(f"\n{status}: {message}")
        
        if data:
            if isinstance(data, dict):
                # 중요한 정보만 출력
                important_keys = ['message', 'total_count', 'indexed_documents', 'total_documents', 'vector_dimension', 'total_examples']
                for key in important_keys:
                    if key in data:
                        print(f"  📊 {key}: {data[key]}")
                
                # 색인된 문서 샘플 출력
                if 'sample_documents' in data and data['sample_documents']:
                    print(f"\n  📋 색인된 문서 샘플 (상위 3개):")
                    for doc in data['sample_documents']:
                        print(f"    {doc['순번']}. {doc['문서명']} - {doc['장']}")
                        print(f"       📝 내용: {doc['문서내용']}")
                        print(f"       📁 출처: {doc['출처파일']}")
                        print(f"       🧮 벡터: {doc['content_vector']}")
                        print()
                
                # 검색 결과 미리보기
                if 'results' in data and data['results']:
                    print(f"  🔍 검색 결과 미리보기 (상위 {min(len(data['results']), 2)}개):")
                    for i, result in enumerate(data['results'][:2], 1):
                        # 올바른 구조로 접근 (source 필드 안에 문서 정보가 있음)
                        source = result.get('source', {})
                        print(f"    {i}. {source.get('문서명', 'N/A')} - {source.get('장', 'N/A')}")
                        
                        # 점수 정보 표시
                        if 'rerank_score' in result:
                            print(f"       리랭크 점수: {result['rerank_score']:.4f}")
                        elif 'combined_score' in result:
                            print(f"       하이브리드 점수: {result['combined_score']:.4f}")
                        elif 'final_score' in result:
                            print(f"       점수: {result['final_score']:.4f}")
                        
                        # 내용 미리보기
                        content = source.get('문서내용', '')
                        if content:
                            preview = content[:50] + "..." if len(content) > 50 else content
                            print(f"       내용: {preview}")
            else:
                print(f"  📄 데이터: {data}")
    
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        API 요청을 수행하고 결과를 반환
        
        Args:
            method: HTTP 메서드 (GET, POST, DELETE)
            endpoint: API 엔드포인트
            data: 요청 데이터 (POST 요청 시)
            
        Returns:
            Dict: API 응답 또는 오류 정보
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            elif method.upper() == "DELETE":
                response = self.session.delete(url)
            else:
                raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.ConnectionError:
            return {"error": "connection_failed", "message": f"서버 연결 실패: {url}"}
        except requests.exceptions.RequestException as e:
            try:
                error_detail = response.json() if hasattr(response, 'json') else str(e)
                return {"error": "request_failed", "message": f"API 요청 실패: {error_detail}"}
            except:
                return {"error": "request_failed", "message": f"API 요청 실패: {str(e)}"}
    
    def example_1_health_check(self) -> bool:
        """
        예시 1: 시스템 상태 확인 (GET /health)
        
        OpenSearch 연결 상태와 시스템 건강성을 확인합니다.
        """
        self.print_step(1, "시스템 상태 확인 (GET /health)")
        
        print("📋 사용법:")
        print("  curl -X GET 'http://localhost:8010/health'")
        print("  또는 Python requests 사용:")
        print("  response = requests.get('http://localhost:8010/health')")
        
        result = self.make_request("GET", "/health")
        
        if "error" in result:
            self.print_result(False, f"서버 연결 실패: {result['message']}")
            print("\n💡 해결방법:")
            print("  1. OpenSearch 컨테이너 확인: docker-compose ps")
            print("  2. FastAPI 서버 실행: python opensearch_api.py")
            print("  3. 포트 확인: netstat -ano | findstr :8010")
            return False
        
        success = result.get("opensearch_connected", False)
        self.print_result(success, "시스템 상태 확인 완료", result)
        
        if success:
            print("\n🎯 다음 단계: 매핑 예제 조회")
        
        return success
    
    def example_2_mapping_examples(self) -> Optional[Dict]:
        """
        예시 2: 매핑 예제 조회 (GET /mapping/examples)
        
        인덱스 생성 시 사용할 수 있는 매핑 예제들을 조회합니다.
        """
        self.print_step(2, "매핑 예제 조회 (GET /mapping/examples)")
        
        print("📋 사용법:")
        print("  curl -X GET 'http://localhost:8010/mapping/examples'")
        print("  또는 Python requests 사용:")
        print("  response = requests.get('http://localhost:8010/mapping/examples')")
        
        result = self.make_request("GET", "/mapping/examples")
        
        if "error" in result:
            self.print_result(False, f"매핑 예제 조회 실패: {result['message']}")
            return None
        
        success = result.get("success", False)
        self.print_result(success, "매핑 예제 조회 완료", result)
        
        if success and "examples" in result:
            print("\n💡 매핑 예제 설명:")
            examples = result["examples"]
            for key, example in examples.items():
                print(f"  {key}. {example.get('name', 'N/A')}")
                print(f"     설명: {example.get('description', 'N/A')}")
            
            print("\n🎯 다음 단계: 예제 2번 매핑을 사용하여 인덱스 생성")
            return result["examples"]
        
        return None
    
    def example_3_create_index(self, mapping_examples: Dict) -> bool:
        """
        예시 3: 인덱스 생성 (POST /index/create)
        
        제약회사 문서 검색에 최적화된 인덱스를 생성합니다.
        """
        self.print_step(3, f"인덱스 생성 (POST /index/create)")
        
        print("📋 사용법:")
        print("  curl -X POST 'http://localhost:8010/index/create' \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"index_name\": \"my_index\", \"mapping\": {...}}'")
        print("  또는 Python requests 사용:")
        print("  response = requests.post('http://localhost:8010/index/create', json=data)")
        
        # 권장 매핑 (예제 2번) 사용
        if "2" not in mapping_examples:
            self.print_result(False, "권장 매핑 예제를 찾을 수 없습니다.")
            return False

        # 벡터 검색 지원 매핑 (권장)
        mapping_example = {
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
                        "dimension": 1024,              # 임베딩 모델 차원
                        "method": {
                            "name": "hnsw",             # Hierarchical Navigable Small World
                            "space_type": "cosinesimil", # 코사인 유사도 사용
                            "engine": "lucene"          # 검색 엔진
                        }
                    }
                }
            }
        }
        
        print(f"\n📝 사용할 매핑 예제: {mapping_examples['2']['name']}")
        print(f"설명: {mapping_examples['2']['description']}")
        
        # 기존 인덱스 삭제 (있다면)
        print(f"\n🗑️ 기존 인덱스 삭제 시도: {self.index_name}")
        delete_result = self.make_request("DELETE", f"/index/{self.index_name}")
        if "error" not in delete_result:
            print(f"  기존 인덱스 삭제됨")
        
        # 새 인덱스 생성
        create_data = {
            "index_name": self.index_name,
            "mapping": mapping_example
        }
        
        result = self.make_request("POST", "/index/create", create_data)
        
        if "error" in result:
            self.print_result(False, f"인덱스 생성 실패: {result['message']}")
            return False
        
        success = result.get("success", False)
        self.print_result(success, f"인덱스 '{self.index_name}' 생성 완료", result)
        
        if success:
            print("\n🎯 다음 단계: JSONL 파일에서 문서 로드")
        
        return success
    
    def example_4_load_documents(self) -> bool:
        """
        예시 4: 문서 로드 및 색인 (POST /documents/load)
        
        data/ 폴더의 JSONL 파일들을 읽어서 문서를 색인합니다.
        """
        self.print_step(4, "문서 로드 및 색인 (POST /documents/load)")
        
        print("📋 사용법:")
        print("  curl -X POST 'http://localhost:8010/documents/load' \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"index_name\": \"my_index\", \"jsonl_pattern\": \"data/*.jsonl\"}'")
        print("  또는 Python requests 사용:")
        print("  response = requests.post('http://localhost:8010/documents/load', json=data)")
        
        load_data = {
            "index_name": self.index_name,
            "jsonl_pattern": "data/*.jsonl"
        }
        
        print(f"\n📁 처리할 파일 패턴: {load_data['jsonl_pattern']}")
        print("⏰ 이 작업은 시간이 걸릴 수 있습니다 (임베딩 생성 포함)...")
        print("📊 진행 상황: 각 문서마다 1024차원 벡터 생성 중...")
        
        result = self.make_request("POST", "/documents/load", load_data)
        
        if "error" in result:
            self.print_result(False, f"문서 로드 실패: {result['message']}")
            print("\n💡 해결방법:")
            print("  1. data/ 폴더에 JSONL 파일 존재 확인")
            print("  2. 파일 권한 확인")
            print("  3. JSONL 파일 형식 확인")
            return False
        
        success = result.get("success", False)
        self.print_result(success, "문서 로드 및 색인 완료", result)
        
        if success:
            indexed_count = result.get("indexed_documents", 0)
            jsonl_files = result.get("jsonl_files", [])
            print(f"\n📚 처리 결과:")
            print(f"  - 총 색인된 문서: {indexed_count}개")
            print(f"  - 처리된 파일: {len(jsonl_files)}개")
            for file in jsonl_files:
                print(f"    ✓ {file}")
            
            print("\n🎯 다음 단계: 인덱스 통계 확인")
        
        return success
    
    def example_5_index_stats(self) -> bool:
        """
        예시 5: 인덱스 통계 확인 (GET /index/{index_name}/stats)
        
        생성된 인덱스의 문서 수와 통계 정보를 확인합니다.
        """
        self.print_step(5, "인덱스 통계 확인 (GET /index/{index_name}/stats)")
        
        print("📋 사용법:")
        print(f"  curl -X GET 'http://localhost:8010/index/{self.index_name}/stats'")
        print("  또는 Python requests 사용:")
        print(f"  response = requests.get('http://localhost:8010/index/{self.index_name}/stats')")
        
        result = self.make_request("GET", f"/index/{self.index_name}/stats")
        
        if "error" in result:
            self.print_result(False, f"인덱스 통계 조회 실패: {result['message']}")
            return False
        
        success = "total_documents" in result
        self.print_result(success, f"인덱스 '{self.index_name}' 통계 조회 완료", result)
        
        if success:
            print("\n🎯 다음 단계: 하이브리드 검색 테스트")
        
        return success
    
    def example_6_hybrid_search(self) -> bool:
        """
        예시 6: 하이브리드 검색 (POST /search)
        
        BM25 + 벡터 검색을 결합한 하이브리드 검색을 수행합니다.
        """
        self.print_step(6, "하이브리드 검색 (POST /search)")
        
        print("📋 사용법:")
        print("  curl -X POST 'http://localhost:8010/search' \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"keywords\": [\"키워드1\", \"키워드2\"], \"query_text\": \"검색 쿼리\"}'")
        print("  또는 Python requests 사용:")
        print("  response = requests.post('http://localhost:8010/search', json=search_data)")
        
        # 다양한 검색 쿼리 예시
        test_queries = [
            {
                "name": "신입사원 교육 관련 검색",
                "keywords": ["신입사원", "교육", "기간"],
                "query_text": "신입사원 교육 기간이 어떻게 돼?",
                "description": "키워드 검색 + 자연어 질의를 결합한 예시"
            },
            {
                "name": "의약품 제조 규정 검색",
                "keywords": ["의약품", "제조", "규정"],
                "query_text": "의약품 제조 관련 규정은 어떻게 되나요?",
                "description": "규제 관련 문서 검색 예시"
            },
            {
                "name": "품질 관리 절차 검색",
                "keywords": ["품질", "관리", "절차"],
                "query_text": "품질 관리 절차에 대해 알려주세요",
                "description": "프로세스 관련 문서 검색 예시"
            }
        ]
        
        all_success = True
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n🔍 검색 예시 {i}: {query['name']}")
            print(f"📝 설명: {query['description']}")
            
            # 검색 파라미터 설정
            search_data = {
                "keywords": query["keywords"],
                "query_text": query["query_text"],
                "index_name": self.index_name,
                "top_k": 10,          # 하이브리드 검색으로 10개 추출
                "bm25_weight": 0.3,   # BM25 가중치 (30%)
                "vector_weight": 0.7, # 벡터 가중치 (70%)
                "use_rerank": True,   # BGE Reranker 사용
                "rerank_top_k": 3     # 최종 3개 결과 반환
            }
            
            print(f"📊 검색 파라미터:")
            print(f"  - 키워드: {query['keywords']}")
            print(f"  - 쿼리: '{query['query_text']}'")
            print(f"  - BM25 가중치: {search_data['bm25_weight']}")
            print(f"  - 벡터 가중치: {search_data['vector_weight']}")
            print(f"  - 리랭크 사용: {search_data['use_rerank']}")
            
            result = self.make_request("POST", "/search", search_data)
            
            if "error" in result:
                self.print_result(False, f"검색 실패: {result['message']}")
                all_success = False
                continue
            
            success = result.get("success", False)
            message = f"검색 완료 - 쿼리: '{query['query_text']}'"
            self.print_result(success, message, result)
            
            if not success:
                all_success = False
        
        return all_success
    
    def run_all_examples(self):
        """
        모든 API 사용 예시를 순차적으로 실행
        
        실제 프로덕션 환경에서는 필요한 부분만 선택적으로 사용하세요.
        """
        print("🏥 제약회사 문서 검색 시스템 API 사용 예시")
        print("📌 FastAPI 서버 포트: 8010")
        print("🔄 모든 API 엔드포인트 사용법을 단계별로 보여드립니다")
        
        start_time = time.time()
        
        # 예시 1: 시스템 상태 확인
        if not self.example_1_health_check():
            print("\n❌ 시스템 상태 확인 실패. 다음 단계를 확인해주세요:")
            print("💡 해결방법:")
            print("  1. docker-compose up -d")
            print("  2. python opensearch_api.py")
            print("  3. 10분 정도 대기 후 재시도")
            return False
        
        # 예시 2: 매핑 예제 조회
        mapping_examples = self.example_2_mapping_examples()
        if not mapping_examples:
            print("\n❌ 매핑 예제 조회 실패. API 서버 상태를 확인해주세요.")
            return False
        
        # 예시 3: 인덱스 생성
        if not self.example_3_create_index(mapping_examples):
            print("\n❌ 인덱스 생성 실패. OpenSearch 연결을 확인해주세요.")
            return False
        
        # 예시 4: 문서 로드 및 색인
        if not self.example_4_load_documents():
            print("\n❌ 문서 로드 실패. data/ 폴더의 JSONL 파일을 확인해주세요.")
            return False
        
        # 잠시 대기 (색인 완료 대기)
        print("\n⏳ 색인 완료 대기 중... (3초)")
        time.sleep(3)
        
        # 예시 5: 인덱스 통계 확인
        self.example_5_index_stats()
        
        # 예시 6: 하이브리드 검색
        search_success = self.example_6_hybrid_search()
        if not search_success:
            print("\n⚠️ 일부 검색 예시에서 오류가 발생했습니다.")
        
        # 완료 메시지
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n{'='*80}")
        print("🎉 API 사용 예시 완료!")
        print(f"⏱️ 총 소요시간: {duration:.1f}초")
        print(f"📊 생성된 인덱스: {self.index_name}")
        print("🔗 추가 정보:")
        print(f"  - API 문서: http://localhost:8010/docs")
        print(f"  - ReDoc: http://localhost:8010/redoc")
        print(f"  - 매핑 예제: http://localhost:8010/mapping/examples")
        print(f"{'='*80}")
        
        return True

def main():
    """
    메인 함수 - 다양한 실행 모드 지원
    """
    print("🚀 제약회사 문서 검색 시스템 API 사용 예시")
    print("📖 이 스크립트는 FastAPI 서버 사용법을 보여주는 예시입니다")
    
    # 실행 모드 체크
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
        if mode == "--health":
            print("⚡ 빠른 상태 확인 모드")
            example = PharmSearchAPIExample()
            example.example_1_health_check()
            return
        
        elif mode == "--search":
            print("🔍 검색 테스트 모드")
            example = PharmSearchAPIExample()
            example.example_6_hybrid_search()
            return
        
        elif mode == "--mapping":
            print("📋 매핑 예제 조회 모드")
            example = PharmSearchAPIExample()
            example.example_2_mapping_examples()
            return
        
        elif mode == "--help":
            print("🔧 사용법:")
            print("  python test_run.py           : 모든 예시 실행")
            print("  python test_run.py --health  : 상태 확인만")
            print("  python test_run.py --search  : 검색 테스트만")
            print("  python test_run.py --mapping : 매핑 예제 조회만")
            print("  python test_run.py --help    : 도움말")
            return
    
    # 전체 예시 실행
    example = PharmSearchAPIExample()
    
    try:
        success = example.run_all_examples()
        if success:
            print("\n🎯 모든 API 사용 예시가 성공적으로 완료되었습니다!")
            print("💡 이제 각 API를 활용하여 자신만의 검색 시스템을 구축해보세요.")
            print("📚 자세한 API 문서: http://localhost:8010/docs")
        else:
            print("\n❌ 일부 예시에서 오류가 발생했습니다.")
            print("🔧 문제 해결을 위해 로그를 확인해주세요.")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⏸️ 사용자에 의해 예시 실행이 중단되었습니다.")
        return 1
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 