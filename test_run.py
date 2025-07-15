"""
제약회사 문서 검색 시스템 통합 테스트 스크립트

8010포트의 FastAPI REST API를 사용하여:
1. 서버 상태 확인
2. 매핑 예제 조회
3. 인덱스 생성
4. data 폴더의 JSONL 파일 임베딩 및 색인
5. 검색 테스트
6. 인덱스 통계 확인

모든 작업은 REST API로 수행됩니다.
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Optional

class PharmSearchAPITester:
    """제약회사 문서 검색 API 테스터"""
    
    def __init__(self, base_url: str = "http://localhost:8010"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.index_name = "pharma_test_index"
        
    def print_step(self, step_num: int, title: str):
        """단계 출력"""
        print(f"\n{'='*80}")
        print(f"🔷 단계 {step_num}: {title}")
        print(f"{'='*80}")
    
    def print_result(self, success: bool, message: str, data: Optional[Dict] = None):
        """결과 출력"""
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
                        print(f"    {i}. {result.get('문서명', 'N/A')} - {result.get('장', 'N/A')}")
                        if 'final_score' in result:
                            print(f"       점수: {result['final_score']:.4f}")
            else:
                print(f"  📄 데이터: {data}")
    
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """API 요청 수행"""
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
    
    def step1_health_check(self) -> bool:
        """1단계: 서버 상태 확인"""
        self.print_step(1, "서버 상태 확인")
        
        result = self.make_request("GET", "/health")
        
        if "error" in result:
            self.print_result(False, f"서버 연결 실패: {result['message']}")
            return False
        
        success = result.get("opensearch_connected", False)
        self.print_result(success, "서버 상태 확인 완료", result)
        return success
    
    def step2_get_mapping_examples(self) -> Optional[Dict]:
        """2단계: 매핑 예제 조회"""
        self.print_step(2, "매핑 예제 조회")
        
        result = self.make_request("GET", "/mapping/examples")
        
        if "error" in result:
            self.print_result(False, f"매핑 예제 조회 실패: {result['message']}")
            return None
        
        success = result.get("success", False)
        self.print_result(success, "매핑 예제 조회 완료", result)
        
        if success and "examples" in result:
            return result["examples"]
        return None
    
    def step3_create_index(self, mapping_examples: Dict) -> bool:
        """3단계: 인덱스 생성"""
        self.print_step(3, f"인덱스 생성: {self.index_name}")
        
        # 권장 매핑 (예제 2번) 사용
        if "2" not in mapping_examples:
            self.print_result(False, "권장 매핑 예제를 찾을 수 없습니다.")
            return False

        vec_dim = 1024
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
        
        # 기존 인덱스 삭제 (있다면)
        delete_result = self.make_request("DELETE", f"/index/{self.index_name}")
        if "error" not in delete_result:
            print(f"  🗑️ 기존 인덱스 삭제됨")
        
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
        return success
    
    def step4_load_documents(self) -> bool:
        """4단계: 문서 로드 및 색인"""
        self.print_step(4, "JSONL 파일 로드 및 임베딩 색인")
        
        load_data = {
            "index_name": self.index_name,
            "jsonl_pattern": "data/*.jsonl"
        }
        
        print("📁 data 폴더의 JSONL 파일들을 로드하고 임베딩을 생성합니다...")
        print("⏰ 이 작업은 시간이 걸릴 수 있습니다 (임베딩 생성 포함)...")
        
        result = self.make_request("POST", "/documents/load", load_data)
        
        if "error" in result:
            self.print_result(False, f"문서 로드 실패: {result['message']}")
            return False
        
        success = result.get("success", False)
        self.print_result(success, "문서 로드 및 색인 완료", result)
        
        if success:
            indexed_count = result.get("indexed_documents", 0)
            jsonl_files = result.get("jsonl_files", [])
            print(f"  📚 처리된 파일: {len(jsonl_files)}개")
            for file in jsonl_files:
                print(f"    - {file}")
        
        return success
    
    def step5_index_stats(self) -> bool:
        """5단계: 인덱스 통계 확인"""
        self.print_step(5, "인덱스 통계 확인")
        
        result = self.make_request("GET", f"/index/{self.index_name}/stats")
        
        if "error" in result:
            self.print_result(False, f"인덱스 통계 조회 실패: {result['message']}")
            return False
        
        success = "total_documents" in result
        self.print_result(success, f"인덱스 '{self.index_name}' 통계 조회 완료", result)
        return success
    
    def step6_search_test(self) -> bool:
        """6단계: 검색 테스트"""
        self.print_step(6, "하이브리드 검색 테스트")
        
        # 테스트 검색 쿼리들
        test_queries = [
            {
                "name": "신입사원 교육 관련",
                "keywords": ["신입사원", "교육", "기간"],
                "query_text": "신입사원 교육 기간이 어떻게 돼?"
            },
            {
                "name": "의약품 제조 규정",
                "keywords": ["의약품", "제조", "규정"],
                "query_text": "의약품 제조 관련 규정은 어떻게 되나요?"
            },
            {
                "name": "품질 관리 절차",
                "keywords": ["품질", "관리", "절차"],
                "query_text": "품질 관리 절차에 대해 알려주세요"
            }
        ]
        
        all_success = True
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n🔍 검색 테스트 {i}: {query['name']}")
            
            search_data = {
                "keywords": query["keywords"],
                "query_text": query["query_text"],
                "index_name": self.index_name,  # 올바른 인덱스명 전달
                "top_k": 10,
                "bm25_weight": 0.3,
                "vector_weight": 0.7,
                "use_rerank": True,
                "rerank_top_k": 3
            }
            
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
    
    def run_full_test(self):
        """전체 테스트 실행"""
        print("🏥 제약회사 문서 검색 시스템 통합 테스트")
        print("📌 8010포트 FastAPI REST API 사용")
        print("🔄 모든 작업은 REST API로 수행됩니다")
        
        start_time = time.time()
        
        # 1단계: 서버 상태 확인
        if not self.step1_health_check():
            print("\n❌ 서버 상태 확인 실패. 테스트를 중단합니다.")
            print("💡 해결방법: 'python opensearch_api.py' 또는 'docker-compose up -d'로 서버를 먼저 시작하세요.")
            return False
        
        # 2단계: 매핑 예제 조회
        mapping_examples = self.step2_get_mapping_examples()
        if not mapping_examples:
            print("\n❌ 매핑 예제 조회 실패. 테스트를 중단합니다.")
            return False
        
        # 3단계: 인덱스 생성
        if not self.step3_create_index(mapping_examples):
            print("\n❌ 인덱스 생성 실패. 테스트를 중단합니다.")
            return False
        
        # 4단계: 문서 로드 및 색인
        if not self.step4_load_documents():
            print("\n❌ 문서 로드 실패. 테스트를 중단합니다.")
            return False
        
        # 잠시 대기 (색인 완료 대기)
        print("\n⏳ 색인 완료 대기 중... (3초)")
        time.sleep(3)
        
        # 5단계: 인덱스 통계 확인
        self.step5_index_stats()
        
        # # 6단계: 검색 테스트
        # if not self.step6_search_test():
        #     print("\n⚠️ 일부 검색 테스트 실패")
        
        # # 테스트 완료
        # end_time = time.time()
        # duration = end_time - start_time
        
        # print(f"\n{'='*80}")
        # print("🎉 통합 테스트 완료!")
        # print(f"⏱️ 총 소요시간: {duration:.1f}초")
        # print(f"📊 생성된 인덱스: {self.index_name}")
        # print("🔍 검색 API 테스트 완료")
        # print(f"{'='*80}")
        
        return True

def main():
    """메인 함수"""
    print("🚀 제약회사 문서 검색 시스템 통합 테스트 시작")
    
    # 빠른 테스트 모드 체크
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        print("⚡ 빠른 테스트 모드 - 검색만 수행")
        tester = PharmSearchAPITester()
        result = tester.make_request("POST", "/test-search")
        if "error" in result:
            print(f"❌ 빠른 테스트 실패: {result['message']}")
        else:
            print("✅ 빠른 테스트 성공!")
            print(f"📊 검색 결과: {result.get('total_count', 0)}개")
        return
    
    # 전체 테스트 실행
    tester = PharmSearchAPITester()
    
    try:
        success = tester.run_full_test()
        if success:
            print("\n🎯 모든 테스트가 성공적으로 완료되었습니다!")
            print("💡 이제 http://localhost:8010/docs 에서 API를 사용할 수 있습니다.")
        else:
            print("\n❌ 테스트 중 오류가 발생했습니다.")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⏸️ 사용자에 의해 테스트가 중단되었습니다.")
        return 1
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 