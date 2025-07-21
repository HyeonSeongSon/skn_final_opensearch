from opensearchpy import OpenSearch, exceptions, helpers
from sentence_transformers import SentenceTransformer
from FlagEmbedding import FlagReranker
from dotenv import load_dotenv
from typing import List, Dict, Any, Union
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import numpy as np
import logging
import json
import os
import math

load_dotenv()

class OpenSearchHybridClient:
    def __init__(self):
        """
        OpenSearch 클라이언트 초기화 및 연결 설정 (하이브리드 쿼리 기반)
        """
        try:
            password = os.getenv("OPENSEARCH_ADMIN_PASSWORD")
            if not password:
                logging.warning("환경 변수 OPENSEARCH_ADMIN_PASSWORD가 설정되지 않았습니다. 기본값을 사용합니다.")
                password = "StrongP@ssw0rd123!"
            
            logging.info(f"OpenSearch 연결 시도 중... (비밀번호 길이: {len(password)})")
            
            host = os.getenv("OPENSEARCH_HOST", "localhost")
            port = int(os.getenv("OPENSEARCH_PORT", "9200"))
            
            logging.info(f"OpenSearch 연결 대상: {host}:{port}")
            
            self.client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                timeout=30,
            )
            
            if not self.client.ping():
                raise exceptions.ConnectionError("OpenSearch에 연결할 수 없습니다.")
            logging.info("OpenSearch에 성공적으로 연결되었습니다.")
        except exceptions.OpenSearchException as e:
            logging.error(f"OpenSearch 클라이언트 초기화 중 오류 발생: {e}")
            self.client = None

        self.model = self.embeddings_model()
        self.reranker = self.rerank_model()
        self.llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
        self.keyword_prompt = {
            "prompts": {
                "keyword_extraction": """
                당신은 반드시 키워드를 추출하는 챗봇입니다.
                사용자의 질문에서 키워드를 반드시 추출하세요.

                "{user_question}"

                아래 조건을 만족해서 출력하세요.

                1. 키워드는 리스트 형태로 반드시 출력

                2. 문자열은 큰따옴표로 감싸서 출력하세요.

                3. 리스트외에는 아무것도 출력하지 마세요.

                4. 키워드는 최대 5개까지 추출하세요.

                5. 복합어는 분해해서 의미 있는 단어 단위로 나눠줘

                예를 들어 '임직원 교육기간'이라면 '임직원', '교육', '기간'처럼 나눠줘.
                """
            }
        }

    def rerank_model(self):
        """
        BGE Reranker 모델 초기화 (리랭크용)
        """
        print("BGE Reranker 모델 로드 중...")
        reranker = FlagReranker('dragonkue/bge-reranker-v2-m3-ko', use_fp16=True)
        print("BGE Reranker 모델 로드 완료")
        return reranker

    def embeddings_model(self):
        """
        임베딩 모델 초기화
        """
        model = SentenceTransformer("dragonkue/snowflake-arctic-embed-l-v2.0-ko") 
        vec_dim = len(model.encode("dummy_text"))
        print(f"모델 차원: {vec_dim}")
        return model
    
    def get_keyword(self, user_input):
        keyword_template = self.keyword_prompt.get("prompts", {}).get("keyword_extraction", "")
        template = ChatPromptTemplate.from_template(keyword_template)
        messages = template.format_messages(user_question=user_input)
        response = self.llm.invoke(messages)
        return response.content

    def delete_index(self, index_name: str) -> None:
        """
        인덱스를 삭제합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 인덱스를 삭제할 수 없습니다.")
            return
        try:
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logging.info(f"'{index_name}' 인덱스를 삭제했습니다.")
        except exceptions.OpenSearchException as e:
            logging.error(f"인덱스 삭제 중 예상치 못한 오류 발생: {e}")
    
    def index_document(self, index_name: str, document: dict, refresh: bool = False) -> dict | None:
        """
        주어진 인덱스에 문서를 색인합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 색인할 수 없습니다.")
            return None
        try:
            params = {"refresh": "true" if refresh else "false"}
            response = self.client.index(index=index_name, body=document, params=params)
            logging.info(f"'{index_name}' 인덱스에 문서 ID '{response['_id']}'로 색인되었습니다.")
            return response
        except exceptions.RequestError as e:
            logging.error(f"문서 색인 중 오류 발생 (잘못된 요청): {e}")
        except exceptions.OpenSearchException as e:
            logging.error(f"문서 색인 중 예상치 못한 오류 발생: {e}")
        return None

    def bulk_index_documents(self, index_name: str, documents: list[dict], refresh: bool = False) -> bool:
        """
        주어진 인덱스에 여러 문서를 bulk로 색인합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 색인할 수 없습니다.")
            return False

        actions = [
            {"_index": index_name, "_source": doc}
            for doc in documents
        ]

        try:
            success, failed = helpers.bulk(self.client, actions, refresh=refresh)
            logging.info(f"Bulk 작업 완료: 성공 {success}건, 실패 {len(failed)}건")
            return not failed
        except exceptions.OpenSearchException as e:
            logging.error(f"Bulk 색인 중 예상치 못한 오류 발생: {e}")
            return False
    
    def search_document(self, index_name: str, query: dict) -> list[dict]:
        """
        주어진 쿼리로 인덱스에서 문서를 검색합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 검색할 수 없습니다.")
            return []
        try:
            response = self.client.search(index=index_name, body=query)
            hits = response["hits"]["hits"]
            logging.info(f"'{index_name}' 인덱스에서 {len(hits)}개의 문서를 찾았습니다.")
            return [{"score": hit["_score"], "source": hit["_source"]} for hit in hits]
        except exceptions.NotFoundError:
            logging.warning(f"검색 실패: '{index_name}' 인덱스가 존재하지 않습니다.")
        except exceptions.RequestError as e:
            logging.error(f"문서 검색 중 오류 발생 (잘못된 쿼리): {e}")
        except exceptions.OpenSearchException as e:
            logging.error(f"문서 검색 중 예상치 못한 오류 발생: {e}")
        return []
    
    def create_index_with_mapping(self, index_name: str, mapping: dict) -> bool:
        """
        지정한 매핑으로 인덱스를 생성합니다.
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 인덱스를 생성할 수 없습니다.")
            return False
        try:
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(index=index_name, body=mapping)
                logging.info(f"'{index_name}' 인덱스를 매핑과 함께 생성했습니다.")
                return True
            logging.info(f"'{index_name}' 인덱스가 이미 존재합니다.")
            return True
        except exceptions.RequestError as e:
            logging.error(f"인덱스 생성 중 오류 발생 (잘못된 매핑): {e}")
        except exceptions.OpenSearchException as e:
            logging.error(f"인덱스 생성 중 예상치 못한 오류 발생: {e}")
        return False
    
    def load_documents_from_jsonl(self, file_path: str) -> list[dict]:
        """
        JSONL 파일에서 문서들을 로드합니다.
        """
        documents = []
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if line:
                        doc = json.loads(line)
                        documents.append(doc)
            logging.info(f"'{file_path}'에서 {len(documents)}개 문서를 로드했습니다.")
        except FileNotFoundError:
            logging.error(f"파일을 찾을 수 없습니다: {file_path}")
        except json.JSONDecodeError as e:
            logging.error(f"JSON 파싱 오류: {e}")
        except Exception as e:
            logging.error(f"파일 로드 중 예상치 못한 오류 발생: {e}")
        return documents

    def rerank_documents(self, query_text, documents, top_k=3):
        """
        BGE Reranker를 사용하여 문서를 리랭크
        """
        print(f"\n=== BGE Reranker 리랭크 시작 ===")
        print(f"리랭크 대상 문서: {len(documents)}개")
        print(f"리랭크 후 반환: 상위 {top_k}개")
        
        if not documents:
            return []
        
        query_doc_pairs = []
        for doc in documents:
            doc_text = f"{doc['source'].get('문서명', '')} {doc['source'].get('장', '')} {doc['source'].get('조', '')} {doc['source'].get('문서내용', '')}"
            query_doc_pairs.append([query_text, doc_text])
        
        rerank_scores = self.reranker.compute_score(query_doc_pairs)
        
        if rerank_scores is None:
            print("리랭크 점수 계산에 실패했습니다.")
            return documents[:top_k]
        elif isinstance(rerank_scores, np.ndarray):
            rerank_scores = rerank_scores.tolist()
        elif hasattr(rerank_scores, 'tolist'):
            rerank_scores = rerank_scores.tolist()
        else:
            rerank_scores = list(rerank_scores)
        
        print(f"리랭크 점수 범위: {min(rerank_scores):.6f} ~ {max(rerank_scores):.6f}")
        
        for i, doc in enumerate(documents):
            doc['rerank_score'] = rerank_scores[i]
        
        reranked_results = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)[:top_k]
        
        return reranked_results

    def create_search_pipeline(self, pipeline_id: str = "hybrid-minmax-pipeline"):
        """
        OpenSearch 3.0+ 호환 하이브리드 검색용 search pipeline 생성
        """
        pipeline_body = {
            "description": "하이브리드 점수 정규화 및 결합 파이프라인",
            "phase_results_processors": [
                {
                    "normalization-processor": {
                        "normalization": { 
                            "technique": "min_max" 
                        },
                        "combination": {
                            "technique": "arithmetic_mean",
                            "parameters": {
                                "weights": [0.3, 0.7]
                            }
                        }
                    }
                }
            ]
        }

        try:
            # 파이프라인 생성 또는 업데이트
            response = self.client.transport.perform_request(
                method="PUT",
                url=f"/_search/pipeline/{pipeline_id}",
                body=pipeline_body
            )
            print(f"✅ Search pipeline '{pipeline_id}' 생성/업데이트 완료")
            print(f"응답: {response}")
            return True
        except Exception as e:
            print(f"❌ Search pipeline 생성 실패: {e}")
            logging.error(f"Search pipeline 생성 오류: {e}")
            return False

    def get_search_pipeline(self, pipeline_id: str = "hybrid-minmax-pipeline"):
        """
        생성된 search pipeline 정보 조회
        """
        try:
            response = self.client.transport.perform_request(
                method="GET",
                url=f"/_search/pipeline/{pipeline_id}"
            )
            print(f"📋 Search pipeline '{pipeline_id}' 정보:")
            print(json.dumps(response, indent=2, ensure_ascii=False))
            return response
        except Exception as e:
            print(f"❌ Search pipeline 조회 실패: {e}")
            return None

    def delete_search_pipeline(self, pipeline_id: str = "hybrid-minmax-pipeline"):
        """
        search pipeline 삭제
        """
        try:
            response = self.client.transport.perform_request(
                method="DELETE",
                url=f"/_search/pipeline/{pipeline_id}"
            )
            print(f"🗑️ Search pipeline '{pipeline_id}' 삭제 완료")
            return True
        except Exception as e:
            print(f"❌ Search pipeline 삭제 실패: {e}")
            return False
    
    def search_with_pipeline(self, 
                           query_text: str,
                           keywords: Union[str, List[str]] = None, 
                           pipeline_id: str = "hybrid-minmax-pipeline", 
                           index_name: str = "pharma_test_index", 
                           top_k: int = 10,
                           use_rerank: bool = True,
                           rerank_top_k: int = 3):
        """
        Search pipeline을 사용한 하이브리드 검색
        
        Args:
            query_text (str): 검색 쿼리 텍스트
            keywords (Union[str, List[str]]): 키워드 또는 키워드 리스트
            pipeline_id (str): 사용할 search pipeline ID
            index_name (str): 검색 대상 인덱스
            top_k (int): 반환할 결과 수
            use_rerank (bool): 리랭커 사용 여부
            rerank_top_k (int): 리랭크 후 반환할 결과 수
            
        Returns:
            List[Dict]: 검색 결과 (리랭크 적용 시 리랭크된 결과)
        """
        print(f"\n=== Search Pipeline 기반 하이브리드 검색 시작 ===")
        print(f"Pipeline ID: {pipeline_id}")
        print(f"Query: {query_text}")
        print(f"Keywords: {keywords}")
        
        try:
            # 키워드 처리
            if keywords is None:
                keyword_text = query_text
            elif isinstance(keywords, list):
                keyword_text = " ".join(keywords)
            else:
                keyword_text = keywords
            
            # 벡터 임베딩 생성
            query_vector = self.model.encode(query_text).tolist()
            print(f"생성된 벡터 차원: {len(query_vector)}")
            
            # 하이브리드 쿼리 구성
            query_body = {
                "size": top_k,
                "query": {
                    "hybrid": {
                        "queries": [
                            {
                                "multi_match": {
                                    "query": keyword_text,
                                    "fields": ["문서내용^2", "문서명^1.5", "장^1.2", "조^1.0"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO"
                                }
                            },
                            {
                                "knn": {
                                    "content_vector": {
                                        "vector": query_vector,
                                        "k": top_k
                                    }
                                }
                            }
                        ]
                    }
                },
                "_source": {
                    "excludes": ["content_vector"]
                }
            }

            # Search pipeline 파라미터 설정
            params = {"search_pipeline": pipeline_id}
            
            # print(f"실행 중인 쿼리: {json.dumps(query_body, indent=2, ensure_ascii=False)}")

            # 검색 실행
            response = self.client.search(index=index_name, body=query_body, params=params)
            
            # 결과 처리
            hits = response.get("hits", {}).get("hits", [])
            results = []
            
            print(f"✅ Search pipeline 검색 완료: {len(hits)}개 결과")
            
            for i, hit in enumerate(hits):
                result = {
                    "score": hit["_score"],
                    "source": hit["_source"]
                }
                results.append(result)
                
                # 결과 출력
                source = hit["_source"]
                print(f"\n{i+1}. Pipeline 점수: {hit['_score']:.6f}")
                print(f"   문서명: {source.get('문서명', 'N/A')}")
                print(f"   장: {source.get('장', 'N/A')}")
                print(f"   조: {source.get('조', 'N/A')}")
                print(f"   내용: {source.get('문서내용', 'N/A')[:100]}...")
            
            # 리랭크 적용
            if use_rerank and results:
                print(f"\n🔄 BGE Reranker로 상위 {rerank_top_k}개 선별 중...")
                reranked_results = self.rerank_documents(query_text, results, rerank_top_k)
                
                print(f"\n=== BGE Reranker 최종 결과 (상위 {len(reranked_results)}개) ===")
                for i, doc in enumerate(reranked_results):
                    source = doc['source']
                    print(f"\n{i+1}. 리랭크 점수: {doc['rerank_score']:.6f}")
                    print(f"   Pipeline 점수: {doc['score']:.6f}")
                    print(f"   문서명: {source.get('문서명', 'N/A')}")
                    print(f"   장: {source.get('장', 'N/A')}")
                    print(f"   조: {source.get('조', 'N/A')}")
                    print(f"   내용: {source.get('문서내용', 'N/A')[:100]}...")
                
                return reranked_results
            
            return results
            
        except Exception as e:
            print(f"❌ Search pipeline 검색 오류: {e}")
            logging.error(f"Search pipeline 검색 상세 오류: {e}")
            return []


if __name__ == "__main__":
    # OpenSearch Hybrid Client 초기화
    client = OpenSearchHybridClient()
    
    # 사용할 인덱스와 파이프라인 ID 설정
    index_name = "pharma_test_index"  # 실제 인덱스명으로 변경
    pipeline_id = "hybrid-minmax-pipeline"
    
    print("=== OpenSearch 3.0+ Search Pipeline 하이브리드 검색 테스트 ===\n")
    
    # 1. Search Pipeline 생성
    print("1️⃣ Search Pipeline 생성 중...")
    pipeline_created = client.create_search_pipeline(pipeline_id)
    
    if pipeline_created:
        # 2. 생성된 Pipeline 확인
        print("\n2️⃣ 생성된 Search Pipeline 확인...")
        client.get_search_pipeline(pipeline_id)
        
        # 3. Search Pipeline을 사용한 하이브리드 검색 실행
        print("\n3️⃣ Search Pipeline 기반 하이브리드 검색 실행...")
        
        # 테스트 쿼리들
        test_queries = [
            {
                "query_text": "임직원 교육기간이 어떻게 돼?",
                "keywords": ["임직원", "교육", "기간"]
            },
            {
                "query_text": "회사 규정에 대해 알려줘",
                "keywords": ["회사", "규정"]
            }
        ]
        
        for i, test_query in enumerate(test_queries, 1):
            print(f"\n📋 테스트 쿼리 {i}: {test_query['query_text']}")
            
            # Search Pipeline 기반 검색 (리랭크 포함)
            final_results = client.search_with_pipeline(
                query_text=test_query["query_text"],
                keywords=test_query["keywords"],
                pipeline_id=pipeline_id,
                index_name=index_name,
                top_k=5,
                use_rerank=True,
                rerank_top_k=3
            )
            
            print(f"🎯 최종 결과: {len(final_results)}개 문서 반환")
            print("-" * 80)
            
    else:
        print("❌ Search Pipeline 생성에 실패했습니다.")
        print("OpenSearch 버전을 확인하고 search pipeline 기능이 지원되는지 확인해주세요.")
    
    print("\n=== 테스트 완료 ===")