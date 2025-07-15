"""
사용예시
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any, Optional

class PharmSearchClient:
    """제약회사 문서 검색 시스템 API 클라이언트"""
    
    def __init__(self, base_url: str = "http://localhost:8010"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
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
            print(f"❌ 서버 연결 실패: {url}")
            print("📌 run2.py 서버가 실행 중인지 확인하세요: python run2.py")
            return {"error": "connection_failed"}
        except requests.exceptions.RequestException as e:
            print(f"❌ API 요청 실패: {e}")
            try:
                error_detail = response.json() if hasattr(response, 'json') else str(e)
                return {"error": error_detail}
            except:
                return {"error": str(e)}
    
    def check_health(self) -> Dict:
        """서버 상태 확인"""
        print("🏥 서버 헬스 체크 중...")
        return self._make_request("GET", "/health")
    
    def get_api_info(self) -> Dict:
        """API 정보 조회"""
        print("ℹ️ API 정보 조회 중...")
        return self._make_request("GET", "/")
    
    def initialize_system(self, index_name: str = "internal_regulations_index", 
                         recreate_index: bool = True) -> Dict:
        """시스템 전체 초기화 (run.py main() 함수와 동일)"""
        print("🚀 시스템 초기화 중...")
        print(f"📝 인덱스명: {index_name}")
        print(f"🔄 기존 인덱스 재생성: {recreate_index}")
        
        data = {
            "index_name": index_name,
            "recreate_index": recreate_index
        }
        
        return self._make_request("POST", "/initialize", data)
    
    def search_documents(self, keywords: List[str], query_text: str,
                        top_k: int = 10, bm25_weight: float = 0.3,
                        vector_weight: float = 0.7, use_rerank: bool = True,
                        rerank_top_k: int = 3) -> Dict:
        """문서 검색"""
        print("🔍 문서 검색 중...")
        print(f"📝 쿼리: {query_text}")
        print(f"🏷️ 키워드: {keywords}")
        
        data = {
            "keywords": keywords,
            "query_text": query_text,
            "top_k": top_k,
            "bm25_weight": bm25_weight,
            "vector_weight": vector_weight,
            "use_rerank": use_rerank,
            "rerank_top_k": rerank_top_k
        }
        
        return self._make_request("POST", "/search", data)
    
    def test_search(self) -> Dict:
        """테스트 검색 (run.py 예제와 동일)"""
        print("🧪 테스트 검색 실행 중...")
        return self._make_request("POST", "/test-search")
    
    def create_index(self, index_name: str, mapping: Dict) -> Dict:
        """인덱스 생성 (매핑 필수)"""
        print(f"🏗️ 인덱스 생성 중: {index_name}")
        print("📝 사용자 제공 매핑 사용")
        
        data = {
            "index_name": index_name,
            "mapping": mapping
        }
        return self._make_request("POST", "/index/create", data)
    
    def delete_index(self, index_name: str) -> Dict:
        """인덱스 삭제"""
        print(f"🗑️ 인덱스 삭제 중: {index_name}")
        return self._make_request("DELETE", f"/index/{index_name}")
    
    def load_documents(self, index_name: str = "internal_regulations_index",
                      jsonl_pattern: str = "data/*.jsonl") -> Dict:
        """문서 로드 및 색인"""
        print(f"📚 문서 로드 중...")
        print(f"📝 인덱스: {index_name}")
        print(f"📁 파일 패턴: {jsonl_pattern}")
        print("💡 기본적으로 data 폴더의 JSONL 파일들을 사용합니다.")
        
        data = {
            "index_name": index_name,
            "jsonl_pattern": jsonl_pattern
        }
        
        return self._make_request("POST", "/documents/load", data)
    
    def get_index_stats(self, index_name: str) -> Dict:
        """인덱스 통계 조회"""
        print(f"📊 인덱스 통계 조회: {index_name}")
        return self._make_request("GET", f"/index/{index_name}/stats")
    
    def get_mapping_examples_from_api(self) -> Dict:
        """API에서 매핑 예제 조회"""
        print("📋 매핑 예제 조회 중...")
        print("💡 인덱스 생성 시 참고할 수 있는 예제들을 가져옵니다.")
        return self._make_request("GET", "/mapping/examples")
    
    def index_single_document(self, index_name: str, document: Dict, refresh: bool = False) -> Dict:
        """단일 문서 색인"""
        print(f"📝 단일 문서 색인 중: {index_name}")
        print(f"🔄 즉시 반영: {refresh}")
        
        data = {
            "index_name": index_name,
            "document": document,
            "refresh": refresh
        }
        return self._make_request("POST", "/document/index", data)

def print_response(response: Dict, title: str = "응답"):
    """응답 결과를 예쁘게 출력"""
    print(f"\n{'='*60}")
    print(f"📋 {title}")
    print(f"{'='*60}")
    
    if "error" in response:
        print(f"❌ 오류: {response['error']}")
        return
    
    # 성공 여부 확인
    if "success" in response:
        status = "✅ 성공" if response["success"] else "❌ 실패"
        print(f"상태: {status}")
    
    # 메시지 출력
    if "message" in response:
        print(f"메시지: {response['message']}")
    
    # 검색 결과 출력
    if "results" in response and response["results"]:
        print(f"\n🔍 검색 결과 ({response.get('total_count', len(response['results']))}개):")
        for i, result in enumerate(response["results"][:3], 1):  # 상위 3개만 출력
            print(f"\n📄 {i}번째 문서:")
            print(f"   📝 문서명: {result.get('문서명', 'N/A')}")
            print(f"   📖 장: {result.get('장', 'N/A')}")
            print(f"   📑 조: {result.get('조', 'N/A')}")
            print(f"   📁 출처: {result.get('출처파일', 'N/A')}")
            content = result.get('문서내용', '')
            if content:
                content_preview = content[:100] + "..." if len(content) > 100 else content
                print(f"   📋 내용: {content_preview}")
            if 'final_score' in result:
                print(f"   📊 점수: {result['final_score']:.4f}")
    
    # 기타 정보 출력
    for key, value in response.items():
        if key not in ['success', 'message', 'results', 'total_count', 'error']:
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, ensure_ascii=False, indent=2)}")
            else:
                print(f"{key}: {value}")

def get_mapping_examples():
    """매핑 예제 제공"""
    vec_dim = 1024  # 벡터 차원 설정
    
    examples = {
        "1": {
            "name": "제약회사 문서 기본 매핑 (벡터 검색 없음)",
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
    return examples

def interactive_menu(client: PharmSearchClient):
    """대화형 메뉴"""
    while True:
        print(f"\n{'='*60}")
        print("🏥 제약회사 문서 검색 시스템 - 클라이언트")
        print(f"{'='*60}")
        print("1. 서버 상태 확인")
        print("2. API 정보 조회")
        print("3. 시스템 초기화 (run.py main()과 동일)")
        print("4. 문서 검색")
        print("5. 테스트 검색 (run.py 예제)")
        print("6. 인덱스 관리")
        print("7. 문서 관리")
        print("8. 인덱스 통계")
        print("9. 매핑 예제 조회")
        print("10. 전체 시나리오 실행")
        print("0. 종료")
        print(f"{'='*60}")
        
        choice = input("메뉴를 선택하세요 (0-10): ").strip()
        
        try:
            if choice == "0":
                print("👋 프로그램을 종료합니다.")
                break
            elif choice == "1":
                response = client.check_health()
                print_response(response, "서버 상태")
            elif choice == "2":
                response = client.get_api_info()
                print_response(response, "API 정보")
            elif choice == "3":
                response = client.initialize_system()
                print_response(response, "시스템 초기화")
            elif choice == "4":
                print("\n🔍 검색 옵션 입력:")
                query = input("검색어를 입력하세요: ").strip()
                keywords_input = input("키워드를 입력하세요 (쉼표로 구분): ").strip()
                keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
                
                if not query:
                    print("❌ 검색어를 입력해주세요.")
                    continue
                if not keywords:
                    keywords = query.split()
                
                response = client.search_documents(keywords, query)
                print_response(response, "검색 결과")
            elif choice == "5":
                response = client.test_search()
                print_response(response, "테스트 검색")
            elif choice == "6":
                print("\n🏗️ 인덱스 관리:")
                print("1. 인덱스 생성 (매핑 입력)")
                print("2. 인덱스 삭제")
                sub_choice = input("선택하세요 (1-2): ").strip()
                
                if sub_choice == "1":
                    index_name = input("생성할 인덱스명을 입력하세요: ").strip()
                    if index_name:
                        print("\n📝 매핑 입력 방법:")
                        print("1. 예제에서 선택")
                        print("2. 직접 JSON 입력")
                        mapping_choice = input("선택하세요 (1-2): ").strip()
                        
                        final_mapping = None
                        
                        if mapping_choice == "1":
                            # 예제에서 선택
                            print("\n📋 매핑 예제 소스 선택:")
                            print("1. 로컬 예제 (play.py)")
                            print("2. API 예제 (서버)")
                            source_choice = input("소스를 선택하세요 (1-2): ").strip()
                            
                            examples = None
                            if source_choice == "1":
                                examples = get_mapping_examples()
                            elif source_choice == "2":
                                api_response = client.get_mapping_examples_from_api()
                                if api_response.get("success") and "examples" in api_response:
                                    examples = api_response["examples"]
                                    print(f"✅ API에서 {api_response.get('total_examples', 0)}개 예제 로드됨")
                                    print(f"📐 벡터 차원: {api_response.get('vector_dimension', 'N/A')}")
                                else:
                                    print("❌ API에서 예제를 가져올 수 없습니다.")
                            
                            if examples:
                                print("\n📋 매핑 예제:")
                                for key, example in examples.items():
                                    print(f"{key}. {example['name']}")
                                    if 'description' in example:
                                        print(f"   - {example['description']}")
                                
                                example_choice = input("예제를 선택하세요: ").strip()
                                if example_choice in examples:
                                    final_mapping = examples[example_choice]["mapping"]
                                    print(f"✅ '{examples[example_choice]['name']}' 선택됨")
                                    print("📋 선택된 매핑:")
                                    print(json.dumps(final_mapping, ensure_ascii=False, indent=2))
                                else:
                                    print("❌ 잘못된 선택입니다.")
                        
                        elif mapping_choice == "2":
                            # 직접 JSON 입력
                            print("\n📋 JSON 매핑을 입력하세요:")
                            print("💡 예시: {\"settings\": {\"index\": {\"knn\": true}}, \"mappings\": {...}}")
                            mapping_input = input("매핑: ").strip()
                            
                            if mapping_input:
                                try:
                                    final_mapping = json.loads(mapping_input)
                                    print("✅ 매핑 파싱 성공")
                                except json.JSONDecodeError as e:
                                    print(f"❌ JSON 파싱 오류: {e}")
                        
                        else:
                            print("❌ 잘못된 선택입니다.")
                        
                        if final_mapping is not None:
                            response = client.create_index(index_name, final_mapping)
                            print_response(response, "인덱스 생성")
                        else:
                            print("❌ 매핑이 제공되지 않았습니다. 인덱스 생성을 취소합니다.")
                elif sub_choice == "2":
                    index_name = input("삭제할 인덱스명을 입력하세요: ").strip()
                    if index_name:
                        confirm = input(f"정말로 '{index_name}' 인덱스를 삭제하시겠습니까? (y/N): ").strip()
                        if confirm.lower() == 'y':
                            response = client.delete_index(index_name)
                            print_response(response, "인덱스 삭제")
            elif choice == "7":
                print("\n📚 문서 관리:")
                print("1. 단일 문서 색인")
                print("2. 벌크 문서 로드 (JSONL 파일)")
                sub_choice = input("선택하세요 (1-2): ").strip()
                
                if sub_choice == "1":
                    # 단일 문서 색인
                    index_name = input("인덱스명을 입력하세요: ").strip()
                    if index_name:
                        print("\n📝 문서 데이터 입력:")
                        print("💡 JSON 형태로 입력하세요 (예: {\"제목\": \"테스트\", \"내용\": \"테스트 내용\"})")
                        doc_input = input("문서 데이터: ").strip()
                        
                        if doc_input:
                            try:
                                document = json.loads(doc_input)
                                refresh = input("즉시 반영하시겠습니까? (y/N): ").strip().lower() == 'y'
                                response = client.index_single_document(index_name, document, refresh)
                                print_response(response, "단일 문서 색인")
                            except json.JSONDecodeError as e:
                                print(f"❌ JSON 파싱 오류: {e}")
                        else:
                            print("❌ 문서 데이터를 입력해주세요.")
                    else:
                        print("❌ 인덱스명을 입력해주세요.")
                
                elif sub_choice == "2":
                    # 벌크 문서 로드
                    response = client.load_documents()
                    print_response(response, "벌크 문서 로드")
                
                else:
                    print("❌ 올바른 메뉴 번호를 입력하세요.")
            elif choice == "8":
                index_name = input("통계를 조회할 인덱스명을 입력하세요 (기본: internal_regulations_index): ").strip()
                if not index_name:
                    index_name = "internal_regulations_index"
                response = client.get_index_stats(index_name)
                print_response(response, "인덱스 통계")
            elif choice == "9":
                run_full_scenario(client)
            else:
                print("❌ 올바른 메뉴 번호를 입력하세요.")
                
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            break
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
        
        input("\n⏸️ 계속하려면 Enter를 누르세요...")

def run_full_scenario(client: PharmSearchClient):
    """전체 시나리오 실행 (run.py와 동일한 플로우)"""
    print("\n🎬 전체 시나리오 실행 시작")
    print("📌 run.py와 동일한 플로우를 API로 실행합니다.")
    print("📁 data 폴더의 JSONL 파일들을 사용합니다.")
    
    # 1. 서버 상태 확인
    print("\n1️⃣ 서버 상태 확인...")
    health = client.check_health()
    if "error" in health:
        print("❌ 서버 연결 실패. 시나리오를 중단합니다.")
        return
    print("✅ 서버 연결 정상")
    
    # 2. 시스템 초기화
    print("\n2️⃣ 시스템 초기화 중...")
    init_response = client.initialize_system()
    print_response(init_response, "시스템 초기화 결과")
    
    if not init_response.get("success"):
        print("❌ 시스템 초기화 실패. 시나리오를 중단합니다.")
        return
    
    # 3. 잠시 대기
    print("\n3️⃣ 색인 완료 대기 중...")
    time.sleep(3)
    
    # 4. 테스트 검색 실행
    print("\n4️⃣ 테스트 검색 실행...")
    search_response = client.test_search()
    print_response(search_response, "테스트 검색 결과")
    
    # 5. 인덱스 통계 확인
    print("\n5️⃣ 인덱스 통계 확인...")
    stats_response = client.get_index_stats("internal_regulations_index")
    print_response(stats_response, "인덱스 통계")
    
    print("\n🎉 전체 시나리오 실행 완료!")

def quick_test():
    """빠른 테스트 실행"""
    print("🚀 빠른 테스트 모드")
    client = PharmSearchClient()
    
    # 서버 상태 확인
    health = client.check_health()
    if "error" in health:
        return
    
    print("✅ 서버 정상 연결")
    
    # 테스트 검색
    print("\n🔍 테스트 검색 실행...")
    response = client.test_search()
    print_response(response, "테스트 검색 결과")

def main():
    """메인 함수"""
    print("🏥 제약회사 문서 검색 시스템 클라이언트 v2.0")
    print("📌 run2.py FastAPI 서버와 통신합니다.")
    print("📁 JSONL 파일들은 data 폴더에서 읽어옵니다.")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_test()
        return
    
    client = PharmSearchClient()
    
    # 서버 연결 확인
    print("\n🔗 서버 연결 확인 중...")
    health = client.check_health()
    
    if "error" in health:
        print("\n❌ 서버에 연결할 수 없습니다.")
        print("📋 해결 방법:")
        print("1. 터미널에서 'python run2.py' 실행")
        print("2. 서버가 완전히 시작될 때까지 대기")
        print("3. 다시 'python play.py' 실행")
        return
    
    print("✅ 서버 연결 성공!")
    print_response(health, "서버 상태")
    
    # 대화형 메뉴 시작
    try:
        interactive_menu(client)
    except KeyboardInterrupt:
        print("\n\n👋 프로그램을 종료합니다.")

if __name__ == "__main__":
    main() 