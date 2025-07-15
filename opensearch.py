from opensearchpy import OpenSearch, exceptions, helpers
from sentence_transformers import SentenceTransformer
from FlagEmbedding import FlagReranker
from dotenv import load_dotenv
import numpy as np
from typing import List, Dict, Any, Union
import logging
import json
import os
import math

# .env 파일에서 환경 변수 로드
load_dotenv()

class OpenSearchClient:
    def __init__(self):
        """
        OpenSearch 클라이언트 초기화 및 연결 설정
        Args:
            None
        Returns:
            None
        """
        try:
            # 환경 변수 디버깅
            password = os.getenv("OPENSEARCH_ADMIN_PASSWORD")
            if not password:
                logging.warning("환경 변수 OPENSEARCH_ADMIN_PASSWORD가 설정되지 않았습니다. 기본값을 사용합니다.")
                password = "StrongP@ssw0rd123!"
            
            logging.info(f"OpenSearch 연결 시도 중... (비밀번호 길이: {len(password)})")
            
            # 환경변수에서 호스트 정보 가져오기 (docker-compose 환경 지원)
            host = os.getenv("OPENSEARCH_HOST", "localhost")
            port = int(os.getenv("OPENSEARCH_PORT", "9200"))
            
            logging.info(f"OpenSearch 연결 대상: {host}:{port}")
            
            self.client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                # 보안이 비활성화되어 있으므로 인증 없이 연결
                timeout=30, # 연결 타임아웃 설정
            )
            # 연결 확인
            if not self.client.ping():
                raise exceptions.ConnectionError("OpenSearch에 연결할 수 없습니다.")
            logging.info("OpenSearch에 성공적으로 연결되었습니다.")
        except exceptions.OpenSearchException as e:
            logging.error(f"OpenSearch 클라이언트 초기화 중 오류 발생: {e}")
            self.client = None

        # 임베딩 및 리랭크 모델 초기화
        self.model = self.embeddings_model()
        self.reranker = self.rerank_model()

    def rerank_model(self):
        """
        BGE Reranker 모델 초기화 (리랭크용)
        Args:
            None
        Returns:
            reranker: BGE Reranker 모델
        """
        print("BGE Reranker 모델 로드 중...")
        reranker = FlagReranker('BAAI/bge-reranker-base', use_fp16=True)
        print("BGE Reranker 모델 로드 완료")
        return reranker

    def embeddings_model(self):
        """
        임베딩 모델 초기화
        Args:
            None
        Returns:
            model: 임베딩 모델
        """
        model = SentenceTransformer("nlpai-lab/KURE-v1") 
        vec_dim = len(model.encode("dummy_text"))
        print(f"모델 차원: {vec_dim}")
        return model

    def delete_index(self, index_name: str) -> None:
        """
        인덱스를 삭제합니다.

        Args:
            index_name: 삭제할 인덱스 이름
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

        Args:
            index_name: 색인할 인덱스 이름
            document: 색인할 문서 데이터
            refresh: 색인 작업 후 결과를 즉시 반환할지 여부
        Returns:
            dict | None: 색인 결과 또는 None (실패 시)
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 색인할 수 없습니다.")
            return None
        try:
            # refresh 매개변수를 URL 쿼리 파라미터로 전달
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
        
        Args:
            index_name: 색인할 인덱스 이름
            documents: 색인할 문서 데이터 리스트
            refresh: 색인 작업 후 결과를 즉시 반환할지 여부
        Returns:
            bool: 색인 성공 여부
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 색인할 수 없습니다.")
            return False

        # bulk API에 맞는 형식으로 데이터 생성
        actions = [
            {"_index": index_name, "_source": doc}
            for doc in documents
        ]

        try:
            success, failed = helpers.bulk(self.client, actions, refresh=refresh)
            logging.info(f"Bulk 작업 완료: 성공 {success}건, 실패 {len(failed)}건")
            return not failed # 실패한 목록이 비어있으면 True를 반환합니다.
        except exceptions.OpenSearchException as e:
            logging.error(f"Bulk 색인 중 예상치 못한 오류 발생: {e}")
            return False
    
    def search_document(self, index_name: str, query: dict) -> list[dict]:
        """
        주어진 쿼리로 인덱스에서 문서를 검색합니다.
        
        Args:
            index_name: 검색할 인덱스 이름
            query: 검색 쿼리 딕셔너리
        Returns:
            list[dict]: 검색 결과 목록
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 문서를 검색할 수 없습니다.")
            return []
        try:
            response = self.client.search(index=index_name, body=query)
            hits = response["hits"]["hits"]
            logging.info(f"'{index_name}' 인덱스에서 {len(hits)}개의 문서를 찾았습니다.")
            # _source 뿐만 아니라 검색 점수(_score)도 함께 반환
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
        
        Args:
            index_name: 생성할 인덱스 이름
            mapping: 인덱스 매핑 딕셔너리
        Returns:
            bool: 인덱스 생성 성공 여부
        """
        if not self.client:
            logging.error("클라이언트가 초기화되지 않아 인덱스를 생성할 수 없습니다.")
            return False
        try:
            if not self.client.indices.exists(index=index_name):
                self.client.indices.create(index=index_name, body=mapping)
                logging.info(f"'{index_name}' 인덱스를 매핑과 함께 생성했습니다.")
                return True
            # 인덱스가 이미 존재하면, 생성할 필요가 없으므로 성공으로 간주합니다.
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
        
        Args:
            file_path: JSONL 파일 경로
        Returns:
            list[dict]: 로드된 문서들의 리스트
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
    
    def normalize_scores(self, scores):
        """
        점수를 Min-Max 정규화 (0~1 범위)
        
        Args:
            scores: 점수 리스트
        """
        if not scores:
            return []
        
        scores_array = np.array(scores)
        
        # Min-Max 정규화 (0~1 범위)
        min_score = np.min(scores_array)
        max_score = np.max(scores_array)
        if max_score == min_score:
            return [0.5] * len(scores)
        return ((scores_array - min_score) / (max_score - min_score)).tolist()

    def rerank_documents(self, query_text, documents, top_k=3):
        """
        BGE Reranker를 사용하여 문서를 리랭크
        
        Args:
            query_text: 검색 쿼리
            documents: 하이브리드 검색 결과 문서 리스트
            top_k: 리랭크 후 반환할 문서 수
        """
        print(f"\n=== BGE Reranker 리랭크 시작 ===")
        print(f"리랭크 대상 문서: {len(documents)}개")
        print(f"리랭크 후 반환: 상위 {top_k}개")
        
        if not documents:
            return []
        
        # 쿼리-문서 쌍 생성
        query_doc_pairs = []
        for doc in documents:
            # 문서 텍스트 생성 (제목, 장, 조, 내용 결합)
            doc_text = f"{doc['source'].get('문서명', '')} {doc['source'].get('장', '')} {doc['source'].get('조', '')} {doc['source'].get('문서내용', '')}"
            query_doc_pairs.append([query_text, doc_text])
        
        # BGE Reranker로 점수 계산
        rerank_scores = self.reranker.compute_score(query_doc_pairs)
        
        # Tensor를 list로 변환
        if rerank_scores is None:
            print("리랭크 점수 계산에 실패했습니다.")
            return documents[:top_k]
        elif isinstance(rerank_scores, np.ndarray):
            rerank_scores = rerank_scores.tolist()
        elif hasattr(rerank_scores, 'tolist'):
            rerank_scores = rerank_scores.tolist()
        else:
            # 이미 list 형태인 경우 그대로 사용
            rerank_scores = list(rerank_scores)
        
        print(f"리랭크 점수 범위: {min(rerank_scores):.6f} ~ {max(rerank_scores):.6f}")
        
        # 문서에 리랭크 점수 추가
        for i, doc in enumerate(documents):
            doc['rerank_score'] = rerank_scores[i]
        
        # 리랭크 점수로 정렬하여 상위 top_k개 반환
        reranked_results = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)[:top_k]
        
        return reranked_results

    def normalized_hybrid_search(self, keywords, query_text, top_k=5, bm25_weight=0.3, vector_weight=0.7, use_rerank=True, rerank_top_k=3):
        """
        정규화된 하이브리드 서치 (0~1 점수 범위, Min-Max 정규화 사용)
        
        Args:
            keywords: 키워드 리스트 또는 단일 키워드
            query_text: 벡터 유사도 계산용 쿼리 텍스트
            top_k: 반환할 결과 수
            bm25_weight: BM25 점수 가중치 (0~1)
            vector_weight: 벡터 점수 가중치 (0~1)
            use_rerank: BGE Reranker 리랭크 사용 여부
            rerank_top_k: 리랭크 후 반환할 문서 수
        """
        print(f"\n=== 정규화된 하이브리드 서치 ===")
        print(f"키워드: {keywords}")
        print(f"쿼리: '{query_text}'")
        print(f"BM25 가중치: {bm25_weight}, Vector 가중치: {vector_weight}")
        print(f"정규화 방법: Min-Max")
        if use_rerank:
            print(f"리랭크: BGE Reranker 사용 (상위 {rerank_top_k}개 출력)")
        
        # 1. BM25 키워드 검색
        if isinstance(keywords, list):
            keyword_queries = []
            for keyword in keywords:
                keyword_queries.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["문서내용^2", "문서명^1.5", "장^1.2", "조^1.0"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                })
            
            bm25_query = {
                "query": {
                    "bool": {
                        "should": keyword_queries,
                        "minimum_should_match": 1
                    }
                },
                "size": 10,  # BM25로 10개 문서 추출
                "_source": {"excludes": ["content_vector"]}
            }
        else:
            bm25_query = {
                "query": {
                    "multi_match": {
                        "query": keywords,
                        "fields": ["문서내용^2", "문서명^1.5", "장^1.2", "조^1.0"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                },
                "size": 10,  # BM25로 10개 문서 추출
                "_source": {"excludes": ["content_vector"]}
            }
        
        # 2. Vector 유사도 검색 (코사인 유사도 사용)
        query_vector = self.model.encode(query_text)
        
        vector_query = {
            "size": 10,  # 벡터 검색으로 10개 문서 추출
            "query": {
                "knn": {
                    "content_vector": {
                        "vector": query_vector.tolist(),  # type: ignore
                        "k": 10
                    }
                }
            },
            "_source": {"excludes": ["content_vector"]}
        }
        
        try:
            # BM25 검색 실행
            bm25_results = self.search_document("internal_regulations_index", bm25_query)
            print(f"BM25 검색 결과: {len(bm25_results)}개")
            
            # Vector 검색 실행
            vector_results = self.search_document("internal_regulations_index", vector_query)
            print(f"Vector 검색 결과: {len(vector_results)}개")
            
            # 벡터 검색 디버깅
            if vector_results:
                print(f"첫 번째 벡터 검색 결과 점수: {vector_results[0]['score']}")
                print(f"벡터 검색 점수 범위: {min([r['score'] for r in vector_results])} ~ {max([r['score'] for r in vector_results])}")
            else:
                print("⚠️ 벡터 검색 결과가 없습니다!")
            
            # 문서 ID를 키로 하는 딕셔너리 생성
            combined_results = {}
            
            # BM25 결과 처리
            if bm25_results:
                bm25_scores = [result['score'] for result in bm25_results]
                normalized_bm25_scores = self.normalize_scores(bm25_scores)
                
                for i, result in enumerate(bm25_results):
                    doc_id = (result['source'].get('문서명') or '') + (result['source'].get('장') or '') + (result['source'].get('조') or '')
                    combined_results[doc_id] = {
                        'source': result['source'],
                        'bm25_score': normalized_bm25_scores[i],
                        'vector_score': 0.0,
                        'combined_score': 0.0
                    }
            
            # Vector 결과 처리
            if vector_results:
                vector_scores = [result['score'] for result in vector_results]
                normalized_vector_scores = self.normalize_scores(vector_scores)
                
                for i, result in enumerate(vector_results):
                    doc_id = (result['source'].get('문서명') or '') + (result['source'].get('장') or '') + (result['source'].get('조') or '')
                    if doc_id in combined_results:
                        combined_results[doc_id]['vector_score'] = normalized_vector_scores[i]
                    else:
                        combined_results[doc_id] = {
                            'source': result['source'],
                            'bm25_score': 0.0,
                            'vector_score': normalized_vector_scores[i],
                            'combined_score': 0.0
                        }
            
            # 가중치 적용하여 최종 점수 계산
            for doc_id in combined_results:
                doc = combined_results[doc_id]
                doc['combined_score'] = (doc['bm25_score'] * bm25_weight + 
                                    doc['vector_score'] * vector_weight)
            
            # 점수 순으로 정렬
            sorted_results = sorted(combined_results.values(), 
                                key=lambda x: x['combined_score'], 
                                reverse=True)[:top_k]
            
            # 리랭크 적용
            if use_rerank and sorted_results:
                final_results = self.rerank_documents(query_text, sorted_results, rerank_top_k)
                result_title = f"BGE Reranker 리랭크 최종 결과 (상위 {len(final_results)}개)"
            else:
                final_results = sorted_results
                result_title = f"정규화된 하이브리드 검색 결과 (최종 {len(final_results)}개)"
            
            print(f"\n=== {result_title} ===")
            
            for i, doc in enumerate(final_results):
                source = doc['source']
                
                # 매칭된 키워드 확인
                matched_keywords = []
                doc_text = f"{source.get('문서명') or ''} {source.get('장') or ''} {source.get('조') or ''} {source.get('문서내용') or ''}"
                
                if isinstance(keywords, list):
                    for kw in keywords:
                        if kw in doc_text:
                            matched_keywords.append(kw)
                else:
                    if keywords in doc_text:
                        matched_keywords.append(keywords)
                
                # 점수 정보 표시
                if use_rerank and 'rerank_score' in doc:
                    print(f"\n{i+1}. 리랭크 점수: {doc['rerank_score']:.6f}")
                    print(f"   - 하이브리드 점수: {doc['combined_score']:.6f} (BM25: {doc['bm25_score']:.6f}, Vector: {doc['vector_score']:.6f})")
                else:
                    print(f"\n{i+1}. 최종 점수: {doc['combined_score']:.6f} (0~1 범위)")
                    print(f"   - BM25 점수: {doc['bm25_score']:.6f} (가중치: {bm25_weight})")
                    print(f"   - Vector 점수: {doc['vector_score']:.6f} (가중치: {vector_weight})")
                
                print(f"   매치된 키워드: {matched_keywords}")
                print(f"   문서명: {source.get('문서명') or 'N/A'}")
                print(f"   장: {source.get('장') or 'N/A'}")
                print(f"   조: {source.get('조') or 'N/A'}")
                print(f"   출처파일: {source.get('출처파일') or 'N/A'}")
                print(f"   내용: {source.get('문서내용') or 'N/A'}")
            
            return final_results
            
        except Exception as e:
            print(f"정규화된 하이브리드 서치 오류: {e}")
            return []

        