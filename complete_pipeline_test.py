"""
완전한 하이브리드 검색 파이프라인 테스트

이 스크립트는 FastAPI를 통해 다음 파이프라인을 실행합니다:
1. 인덱스 생성 (벡터 검색 지원)
2. /data 폴더의 모든 JSONL 파일 로드 및 임베딩 색인
3. Search Pipeline 생성
4. 사용자 질문에서 키워드 추출
5. 하이브리드 검색 수행
6. BGE Reranker로 재정렬하여 상위 3개 반환

테스트 질문: '임직원 교육은 어떤게 있나요?'
"""

import requests
import json
import time
import sys
from typing import Dict, Any, Optional, List


class HybridSearchPipelineTest:
    """완전한 하이브리드 검색 파이프라인 테스트 클래스"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        파이프라인 테스트 클라이언트 초기화
        
        Args:
            base_url: FastAPI 서버 URL
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.index_name = "pharma_hybrid_index"
        self.pipeline_id = "hybrid-minmax-pipeline"
        self.test_question = "임직원 교육은 어떤게 있나요?"
        
    def print_step(self, step_num: int, title: str):
        """단계별 제목 출력"""
        print(f"\n{'='*80}")
        print(f"🚀 단계 {step_num}: {title}")
        print(f"{'='*80}")
    
    def print_result(self, success: bool, message: str, data: Optional[Dict] = None):
        """결과 출력"""
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{status}: {message}")
        
        if data and isinstance(data, dict):
            # 중요한 정보 출력
            for key in ['total_documents', 'indexed_documents', 'vector_dimension', 'keywords']:
                if key in data:
                    print(f"  📊 {key}: {data[key]}")
    
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
    
    def step_1_health_check(self) -> bool:
        """1단계: 시스템 상태 확인"""
        self.print_step(1, "시스템 상태 확인")
        
        result = self.make_request("GET", "/health")
        
        if "error" in result:
            self.print_result(False, f"서버 연결 실패: {result['message']}")
            print("\n💡 해결방법:")
            print("  1. FastAPI 서버 실행: python opensearch_hybrid_api.py")
            print("  2. OpenSearch 컨테이너 확인: docker-compose ps")
            return False
        
        success = result.get("status") == "healthy"
        self.print_result(success, "시스템 상태 확인 완료")
        return success
    
    def step_2_create_index(self) -> bool:
        """2단계: 벡터 검색 지원 인덱스 생성"""
        self.print_step(2, f"인덱스 생성: {self.index_name}")
        
        # 매핑 예제 조회
        mapping_result = self.make_request("GET", "/mapping/examples")
        if "error" in mapping_result or not mapping_result.get("success"):
            self.print_result(False, "매핑 예제 조회 실패")
            return False
        
        # 권장 매핑 (2번) 사용
        mapping = mapping_result["examples"]["2"]["mapping"]
        
        # 기존 인덱스 삭제
        self.make_request("DELETE", f"/index/{self.index_name}")
        print(f"🗑️ 기존 인덱스 '{self.index_name}' 삭제 시도")
        
        # 새 인덱스 생성
        create_data = {
            "index_name": self.index_name,
            "mapping": mapping
        }
        
        result = self.make_request("POST", "/index/create", create_data)
        
        if "error" in result:
            self.print_result(False, f"인덱스 생성 실패: {result['message']}")
            return False
        
        success = result.get("success", False)
        self.print_result(success, f"인덱스 '{self.index_name}' 생성 완료")
        return success
    
    def step_3_load_and_index_documents(self) -> bool:
        """3단계: /data 폴더의 모든 JSONL 파일 로드 및 임베딩 색인"""
        self.print_step(3, "/data 폴더 JSONL 파일들 로드 및 색인")
        
        # 1단계: JSONL 파일들에서 문서 로드
        print("📁 1단계: JSONL 패턴에서 문서 로드")
        load_data = {"jsonl_pattern": "data/*.jsonl"}
        
        load_result = self.make_request("POST", "/load-jsonl-pattern", load_data)
        
        if "error" in load_result:
            self.print_result(False, f"문서 로드 실패: {load_result['message']}")
            print("\n💡 해결방법:")
            print("  1. data/ 폴더에 JSONL 파일이 있는지 확인")
            print("  2. 파일 형식이 올바른지 확인")
            return False
        
        if not load_result.get("success"):
            self.print_result(False, "문서 로드 실패")
            return False
        
        documents = load_result.get("data", {}).get("documents", [])
        jsonl_files = load_result.get("data", {}).get("jsonl_files", [])
        
        print(f"✅ 로드 완료: {len(documents)}개 문서, {len(jsonl_files)}개 파일")
        for file in jsonl_files:
            print(f"  📄 {file}")
        
        if not documents:
            self.print_result(False, "로드된 문서가 없습니다")
            return False
        
        # 2단계: 임베딩 생성 및 일괄 색인
        print(f"\n🧮 2단계: 임베딩 생성 및 일괄 색인")
        print("⏰ 임베딩 생성 중... (시간이 걸릴 수 있습니다)")
        
        index_data = {
            "index_name": self.index_name,
            "documents": documents,
            "refresh": True
        }
        
        index_result = self.make_request("POST", "/index/bulk", index_data)
        
        if "error" in index_result:
            self.print_result(False, f"문서 색인 실패: {index_result['message']}")
            return False
        
        success = index_result.get("success", False)
        if success:
            data = index_result.get("data", {})
            print(f"✅ 색인 완료:")
            print(f"  - 총 문서: {data.get('total_documents', 0)}개")
            print(f"  - 임베딩 문서: {data.get('embedded_documents', 0)}개")
            print(f"  - 벡터 차원: {data.get('vector_dimension', 0)}")
        
        self.print_result(success, "문서 로드 및 색인 완료", index_result.get("data"))
        return success
    
    def step_4_create_pipeline(self) -> bool:
        """4단계: Search Pipeline 생성"""
        self.print_step(4, f"Search Pipeline 생성: {self.pipeline_id}")
        
        pipeline_data = {"pipeline_id": self.pipeline_id}
        
        result = self.make_request("POST", "/pipeline/create", pipeline_data)
        
        if "error" in result:
            self.print_result(False, f"파이프라인 생성 실패: {result['message']}")
            return False
        
        success = result.get("success", False)
        self.print_result(success, f"Search Pipeline '{self.pipeline_id}' 생성 완료")
        return success
    
    def step_5_extract_keywords(self) -> Optional[List[str]]:
        """5단계: 사용자 질문에서 키워드 추출"""
        self.print_step(5, f"키워드 추출")
        
        print(f"🔍 테스트 질문: '{self.test_question}'")
        
        extract_data = {"user_input": self.test_question}
        
        result = self.make_request("POST", "/extract-keywords", extract_data)
        
        if "error" in result:
            self.print_result(False, f"키워드 추출 실패: {result['message']}")
            return None
        
        if not result.get("success"):
            self.print_result(False, "키워드 추출 실패")
            return None
        
        keywords = result.get("data", {}).get("keywords", [])
        
        # 이미 API에서 파싱된 키워드 리스트를 받음
        if not isinstance(keywords, list):
            # 혹시 문자열로 온 경우를 위한 fallback
            keywords_str = str(keywords)
            try:
                import ast
                if keywords_str.startswith('[') and keywords_str.endswith(']'):
                    keywords = ast.literal_eval(keywords_str)
                else:
                    keywords = [k.strip().strip('"\'') for k in keywords_str.split(',')]
            except:
                keywords = [k.strip() for k in keywords_str.replace('[', '').replace(']', '').replace('"', '').split(',')]
        
        # 빈 키워드 제거
        keywords = [k for k in keywords if k and k.strip()]
        
        print(f"✅ 추출된 키워드: {keywords}")
        self.print_result(True, "키워드 추출 완료", {"keywords": keywords})
        return keywords
    
    def step_6_hybrid_search(self, keywords: List[str]) -> bool:
        """6단계: 하이브리드 검색 및 리랭크"""
        self.print_step(6, "하이브리드 검색 및 리랭크")
        
        search_data = {
            "query_text": self.test_question,
            "keywords": keywords,
            "pipeline_id": self.pipeline_id,
            "index_name": self.index_name,
            "top_k": 10,  # 하이브리드 검색으로 10개 추출
            "use_rerank": True,  # BGE Reranker 사용
            "rerank_top_k": 3  # 최종 3개 반환
        }
        
        print(f"🔍 검색 파라미터:")
        print(f"  - 질문: '{self.test_question}'")
        print(f"  - 키워드: {keywords}")
        print(f"  - 파이프라인: {self.pipeline_id}")
        print(f"  - 하이브리드 검색: 상위 {search_data['top_k']}개")
        print(f"  - 리랭크: 최종 {search_data['rerank_top_k']}개")
        
        result = self.make_request("POST", "/search", search_data)
        
        if "error" in result:
            self.print_result(False, f"검색 실패: {result['message']}")
            return False
        
        success = result.get("success", False)
        if not success:
            self.print_result(False, "검색 실패")
            return False
        
        results = result.get("results", [])
        total_count = result.get("total_count", 0)
        
        print(f"\n🎯 검색 결과: {total_count}개 문서")
        print("="*60)
        
        for i, doc in enumerate(results, 1):
            source = doc.get('source', {})
            rerank_score = doc.get('rerank_score', 0)
            
            print(f"\n{i}. {source.get('문서명', 'N/A')} - {source.get('장', 'N/A')}")
            print(f"   🏆 리랭크 점수: {rerank_score:.6f}")
            print(f"   📝 내용: {source.get('문서내용', 'N/A')[:100]}...")
            print(f"   📁 출처: {source.get('출처파일', 'N/A')}")
        
        self.print_result(success, f"하이브리드 검색 완료 - 상위 {total_count}개 반환")
        return success
    
    def run_complete_pipeline(self) -> bool:
        """전체 파이프라인 실행"""
        print("🏥 완전한 하이브리드 검색 파이프라인 테스트")
        print(f"📋 테스트 질문: '{self.test_question}'")
        print(f"🎯 목표: 키워드 추출 → 하이브리드 검색 → 리랭크 → 상위 3개 반환")
        
        start_time = time.time()
        
        # 1단계: 시스템 상태 확인
        if not self.step_1_health_check():
            return False
        
        # 2단계: 인덱스 생성
        if not self.step_2_create_index():
            return False
        
        # 3단계: 문서 로드 및 색인
        if not self.step_3_load_and_index_documents():
            return False
        
        # 4단계: Search Pipeline 생성
        if not self.step_4_create_pipeline():
            return False
        
        # 잠시 대기 (색인 안정화)
        print("\n⏳ 색인 안정화 대기 중... (3초)")
        time.sleep(3)
        
        # 5단계: 키워드 추출
        keywords = self.step_5_extract_keywords()
        if not keywords:
            return False
        
        # 6단계: 하이브리드 검색 및 리랭크
        if not self.step_6_hybrid_search(keywords):
            return False
        
        # 완료 메시지
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\n{'='*80}")
        print("🎉 완전한 하이브리드 검색 파이프라인 테스트 완료!")
        print(f"⏱️ 총 소요시간: {duration:.1f}초")
        print(f"🔍 테스트 질문: '{self.test_question}'")
        print(f"📊 생성된 인덱스: {self.index_name}")
        print(f"🔧 사용된 파이프라인: {self.pipeline_id}")
        print("✅ 모든 단계가 성공적으로 완료되었습니다!")
        print(f"{'='*80}")
        
        return True


def main():
    """메인 함수"""
    print("🚀 완전한 하이브리드 검색 파이프라인 테스트 시작")
    
    pipeline_test = HybridSearchPipelineTest()
    
    try:
        success = pipeline_test.run_complete_pipeline()
        if success:
            print("\n🎯 테스트가 성공적으로 완료되었습니다!")
            print("💡 이제 동일한 방식으로 다른 질문들도 테스트해보세요.")
        else:
            print("\n❌ 테스트 중 오류가 발생했습니다.")
            print("🔧 로그를 확인하고 문제를 해결해주세요.")
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