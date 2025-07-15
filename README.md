# 제약회사 문서 검색 시스템 (PharmaTech Document Search System)

OpenSearch 기반 하이브리드 검색 시스템으로, 제약회사 내부 규정 문서를 효과적으로 검색할 수 있는 FastAPI 애플리케이션입니다.

## 🚀 주요 기능

- **3노드 OpenSearch 클러스터** - 고가용성 및 확장성 지원
- **하이브리드 검색** - BM25 + 벡터 검색 결합
- **BGE Reranker** - 검색 결과 품질 향상
- **한국어 임베딩** - KURE-v1 모델 사용
- **FastAPI 기반 RESTful API**
- **매핑 예제 API** - 제약회사 문서 전용 인덱스 매핑 템플릿 제공
- **Swagger UI** - 자동 API 문서화
- **Docker Compose** - 원클릭 배포

## 📋 설치 및 실행 순서

### 1. Python 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 입력:

```env
OPENSEARCH_ADMIN_PASSWORD=MyStrongPassword123!
```

### 3. Docker 컨테이너 시작
```bash
docker-compose up -d
```

### 4. 시스템 초기화 대기
**약 10분 정도 기다려주세요.**
- OpenSearch 클러스터 초기화
- FastAPI 의존성 설치 
- 임베딩 모델 다운로드 및 로딩

### 5. FastAPI 서비스 재시작
```bash
docker-compose restart fastapi-search
```

### 6. 서비스 접속 확인
- **FastAPI 문서**: http://localhost:8010/docs
- **OpenSearch Dashboard**: http://localhost:5601

## 🐳 컨테이너 포트 및 설명

| 컨테이너 | 포트 | 설명 |
|----------|------|------|
| **opensearch-node1** | 9200 | OpenSearch 메인 API 포트 |
| **opensearch-node1** | 9600 | Performance Analyzer |
| **opensearch-node2** | 9201 | OpenSearch 노드2 API 포트 |
| **opensearch-node2** | 9601 | Performance Analyzer |
| **opensearch-node3** | 9202 | OpenSearch 노드3 API 포트 |
| **opensearch-node3** | 9602 | Performance Analyzer |
| **opensearch-dashboards** | 5601 | OpenSearch 대시보드 (Kibana 대체) |
| **fastapi-search** | 8010 | FastAPI 애플리케이션 서버 |

## 🌐 주요 접속 URL

- **FastAPI Swagger UI**: http://localhost:8010/docs
- **FastAPI ReDoc**: http://localhost:8010/redoc
- **매핑 예제 API**: http://localhost:8010/mapping/examples
- **OpenSearch API**: http://localhost:9200
- **OpenSearch Dashboard**: http://localhost:5601

## 📚 API 메소드 설명

### 🔍 검색 관련 API

#### `GET /` - API 정보
- **설명**: 시스템 기본 정보 및 상태 확인
- **응답**: API 버전, 시스템 상태

#### `GET /health` - 시스템 상태 확인
- **설명**: OpenSearch 연결 상태 및 시스템 건강성 점검
- **응답**: 상태 메시지, 연결 정보

#### `POST /search` - 하이브리드 검색 + BGE Reranker
- **설명**: 메인 검색 기능 - BM25와 벡터 검색을 결합한 하이브리드 검색
- **요청 파라미터**:
  - `keywords`: 검색 키워드 리스트
  - `query_text`: 검색 쿼리 텍스트
  - `top_k`: 하이브리드 검색 결과 수 (기본: 10)
  - `bm25_weight`: BM25 가중치 (기본: 0.3)
  - `vector_weight`: 벡터 가중치 (기본: 0.7)
  - `use_rerank`: BGE Reranker 사용 여부 (기본: true)
  - `rerank_top_k`: 최종 결과 수 (기본: 3)
- **응답**: 검색 결과, 점수, 메타데이터

#### `POST /test-search` - 테스트 검색
- **설명**: 간단한 테스트용 검색 기능
- **요청 파라미터**: 검색 키워드
- **응답**: 기본 검색 결과

### 📊 인덱스 관리 API

#### `POST /index/create` - 인덱스 생성
- **설명**: 새로운 OpenSearch 인덱스 생성
- **요청 파라미터**:
  - `index_name`: 생성할 인덱스명
  - `mapping`: 인덱스 매핑 정보
- **응답**: 생성 결과 및 상태

#### `DELETE /index/{index_name}` - 인덱스 삭제
- **설명**: 지정된 인덱스 삭제
- **경로 파라미터**: `index_name` - 삭제할 인덱스명
- **응답**: 삭제 결과 및 상태

#### `GET /index/{index_name}/stats` - 인덱스 통계
- **설명**: 인덱스 통계 정보 조회
- **경로 파라미터**: `index_name` - 조회할 인덱스명
- **응답**: 문서 수, 크기, 샤드 정보 등

#### `GET /mapping/examples` - 매핑 예제 조회
- **설명**: 제약회사 문서 검색에 최적화된 인덱스 매핑 예제 제공
- **요청 파라미터**: 없음
- **응답**: 3가지 매핑 예제 및 사용법
  - **예제 1**: 기본 텍스트 매핑 (벡터 검색 없음)
  - **예제 2**: 벡터 검색 지원 매핑 (권장) - BM25 + 벡터 하이브리드 검색
  - **예제 3**: 완전 매핑 (추가 메타데이터 필드 포함)
- **사용법**: `POST /index/create`의 `mapping` 파라미터에 직접 사용 가능

### 📄 문서 관리 API

#### `POST /document/index` - 단일 문서 색인
- **설명**: 개별 문서를 OpenSearch에 색인
- **요청 파라미터**:
  - `index_name`: 색인할 인덱스명
  - `document`: 색인할 문서 데이터
  - `refresh`: 색인 후 즉시 반영 여부
- **응답**: 색인 결과 및 문서 ID

#### `POST /documents/load` - 문서 로드 및 색인
- **설명**: JSONL 파일들을 읽어서 대량 문서 색인
- **요청 파라미터**:
  - `index_name`: 색인할 인덱스명 (기본: "internal_regulations_index")
  - `jsonl_pattern`: JSONL 파일 패턴 (기본: "data/*.jsonl")
- **응답**: 색인된 문서 수, 처리된 파일 목록

## 🔧 관리 명령어

### Docker Compose 명령어
```bash
# 모든 서비스 시작
docker-compose up -d

# 특정 서비스 재시작
docker-compose restart fastapi-search

# 로그 확인
docker-compose logs -f fastapi-search

# 상태 확인
docker-compose ps

# 모든 서비스 중지
docker-compose down

# 볼륨까지 삭제
docker-compose down -v
```

### 개별 서비스 테스트
```bash
# OpenSearch 연결 테스트
curl http://localhost:9200

# FastAPI 헬스 체크
curl http://localhost:8010/health

# 검색 API 테스트
curl -X POST "http://localhost:8010/search" \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": ["규정", "준수"],
    "query_text": "의약품 제조 규정",
    "top_k": 5,
    "rerank_top_k": 3
  }'

# 매핑 예제 조회
curl -X GET "http://localhost:8010/mapping/examples"

# 매핑 예제를 사용한 인덱스 생성
curl -X POST "http://localhost:8010/index/create" \
  -H "Content-Type: application/json" \
  -d '{
    "index_name": "test_index",
    "mapping": {
      "settings": {"index": {"knn": true}},
      "mappings": {
        "properties": {
          "문서명": {"type": "keyword"},
          "문서내용": {"type": "text"},
          "content_vector": {
            "type": "knn_vector",
            "dimension": 1024,
            "method": {
              "name": "hnsw",
              "space_type": "cosinesimil",
              "engine": "lucene"
            }
          }
        }
      }
    }
  }'
```

## 📁 프로젝트 구조

```
final/
├── data/                              # JSONL 데이터 파일들
│   ├── good_pharma_code_structured.jsonl
│   ├── good_pharma_compliance_structured.jsonl
│   ├── good_pharma_disclosure_structured.jsonl
│   ├── good_pharma_ethics_structured.jsonl
│   └── good_pharma_welfare_structured.jsonl
├── opensearch.py                      # OpenSearch 클라이언트 클래스
├── opensearch_api.py                  # FastAPI 애플리케이션
├── test_run.py                        # API 사용 예시 스크립트
├── docker-compose.yml                 # Docker Compose 설정
├── requirements.txt                   # Python 의존성
├── .env                              # 환경변수 (사용자 생성)
└── README.md                         # 본 문서
```

## 🛠️ 기술 스택

- **검색 엔진**: OpenSearch 3.1.0
- **웹 프레임워크**: FastAPI 0.111.0
- **임베딩 모델**: KURE-v1 (Korean Universal Representation Encoder)
- **리랭킹 모델**: BGE Reranker
- **컨테이너화**: Docker & Docker Compose
- **언어**: Python 3.11

## 🔍 사용 예시

### 1. 기본 검색
```python
import requests

response = requests.post("http://localhost:8010/search", json={
    "keywords": ["의약품", "제조", "규정"],
    "query_text": "의약품 제조 시설 관리 규정",
    "top_k": 10,
    "rerank_top_k": 3
})

results = response.json()
```

### 2. 문서 로드
```python
response = requests.post("http://localhost:8010/documents/load", json={
    "index_name": "internal_regulations_index",
    "jsonl_pattern": "data/*.jsonl"
})
```

### 3. 매핑 예제 조회 및 인덱스 생성
```python
# 매핑 예제 조회
response = requests.get("http://localhost:8010/mapping/examples")
examples = response.json()["examples"]

# 권장 매핑 (예제 2번) 사용하여 인덱스 생성
recommended_mapping = examples["2"]["mapping"]
response = requests.post("http://localhost:8010/index/create", json={
    "index_name": "my_pharma_index",
    "mapping": recommended_mapping
})
```

## 📋 API 사용 예시 스크립트 (test_run.py)

`test_run.py`는 PharmaTech Document Search System의 모든 API 엔드포인트 사용법을 보여주는 **완전한 예시 스크립트**입니다. 초보자부터 전문가까지 누구나 쉽게 API를 학습하고 활용할 수 있도록 설계되었습니다.

### 🎯 주요 특징

- **6가지 API 사용 예시**: 시스템 상태 확인부터 하이브리드 검색까지
- **curl & Python 예시**: 각 API별로 curl 명령어와 Python requests 사용법 제공
- **상세한 설명**: 각 단계별 파라미터 설명과 주의사항 포함
- **에러 해결 가이드**: 자주 발생하는 오류와 해결 방법 제시
- **다양한 실행 모드**: 필요에 따라 개별 기능만 테스트 가능

### 🚀 실행 방법

#### 1. 전체 API 사용 예시 실행
```bash
python test_run.py
```
모든 API 엔드포인트를 순차적으로 실행하며 사용법을 보여줍니다.

#### 2. 개별 기능 테스트
```bash
# 시스템 상태 확인만
python test_run.py --health

# 검색 테스트만
python test_run.py --search

# 매핑 예제 조회만
python test_run.py --mapping

# 사용법 도움말
python test_run.py --help
```

### 📚 포함된 API 사용 예시

| 예시 | API 엔드포인트 | 설명 | 학습 내용 |
|------|---------------|------|----------|
| **예시 1** | `GET /health` | 시스템 상태 확인 | OpenSearch 연결 상태 점검 |
| **예시 2** | `GET /mapping/examples` | 매핑 예제 조회 | 인덱스 매핑 설정 방법 |
| **예시 3** | `POST /index/create` | 인덱스 생성 | 벡터 검색 인덱스 생성 |
| **예시 4** | `POST /documents/load` | 문서 로드 및 색인 | 대량 문서 색인 처리 |
| **예시 5** | `GET /index/{name}/stats` | 인덱스 통계 | 색인 상태 모니터링 |
| **예시 6** | `POST /search` | 하이브리드 검색 | BM25 + 벡터 검색 활용 |

### 💡 각 예시별 학습 포인트

#### 예시 1: 시스템 상태 확인
```bash
# curl 사용법
curl -X GET 'http://localhost:8010/health'

# Python 사용법
response = requests.get('http://localhost:8010/health')
```
**학습 내용**: OpenSearch 연결 상태, 임베딩 모델 로딩 상태 확인

#### 예시 2: 매핑 예제 조회
```bash
# 3가지 매핑 템플릿 조회
curl -X GET 'http://localhost:8010/mapping/examples'
```
**학습 내용**: 제약회사 문서에 최적화된 인덱스 매핑 구조 이해

#### 예시 3: 인덱스 생성
```python
# 벡터 검색 지원 인덱스 생성
create_data = {
    "index_name": "pharma_test_index",
    "mapping": {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "문서명": {"type": "keyword"},
                "문서내용": {"type": "text"},
                "content_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene"
                    }
                }
            }
        }
    }
}
response = requests.post('http://localhost:8010/index/create', json=create_data)
```
**학습 내용**: KURE-v1 벡터 차원(1024), HNSW 알고리즘 설정

#### 예시 4: 문서 로드 및 색인
```python
# data/ 폴더의 JSONL 파일 자동 처리
load_data = {
    "index_name": "pharma_test_index",
    "jsonl_pattern": "data/*.jsonl"
}
response = requests.post('http://localhost:8010/documents/load', json=load_data)
```
**학습 내용**: 대량 문서 처리, 자동 임베딩 생성, 벡터 색인

#### 예시 5: 인덱스 통계
```python
# 색인 완료 후 통계 확인
response = requests.get('http://localhost:8010/index/pharma_test_index/stats')
```
**학습 내용**: 색인된 문서 수, 인덱스 크기 모니터링

#### 예시 6: 하이브리드 검색
```python
# 고급 검색 파라미터 설정
search_data = {
    "keywords": ["신입사원", "교육", "기간"],
    "query_text": "신입사원 교육 기간이 어떻게 돼?",
    "index_name": "pharma_test_index",
    "top_k": 10,              # 하이브리드 검색 결과 수
    "bm25_weight": 0.3,       # BM25 가중치 (30%)
    "vector_weight": 0.7,     # 벡터 가중치 (70%)
    "use_rerank": True,       # BGE Reranker 사용
    "rerank_top_k": 3         # 최종 결과 수
}
response = requests.post('http://localhost:8010/search', json=search_data)
```
**학습 내용**: 하이브리드 검색 파라미터 튜닝, 리랭킹 활용

### 🔧 실행 전 준비사항

1. **OpenSearch 클러스터 시작**
   ```bash
   docker-compose up -d
   ```

2. **FastAPI 서버 실행**
   ```bash
   python opensearch_api.py
   ```

3. **데이터 파일 준비**
   ```bash
   # data/ 폴더에 JSONL 파일들이 있는지 확인
   ls data/*.jsonl
   ```

### 📊 예상 실행 결과

```bash
🏥 제약회사 문서 검색 시스템 API 사용 예시
📌 FastAPI 서버 포트: 8010
🔄 모든 API 엔드포인트 사용법을 단계별로 보여드립니다

================================================================================
🔷 예시 1: 시스템 상태 확인 (GET /health)
================================================================================
✅ 성공: 시스템 상태 확인 완료
📊 opensearch_connected: True
📊 embedding_dimension: 1024

================================================================================
🔷 예시 2: 매핑 예제 조회 (GET /mapping/examples)
================================================================================
✅ 성공: 매핑 예제 조회 완료
📊 total_examples: 3

... (중략) ...

================================================================================
🎉 API 사용 예시 완료!
⏱️ 총 소요시간: 45.3초
📊 생성된 인덱스: pharma_test_index
🔗 추가 정보:
  - API 문서: http://localhost:8010/docs
  - ReDoc: http://localhost:8010/redoc
  - 매핑 예제: http://localhost:8010/mapping/examples
================================================================================
```

### 🎓 학습 활용 방법

1. **초보자**: 전체 스크립트 실행 후 각 단계별 결과 확인
2. **개발자**: 개별 API 예시를 복사하여 자신의 코드에 적용
3. **시스템 관리자**: `--health` 모드로 시스템 상태 점검
4. **연구자**: `--search` 모드로 다양한 검색 파라미터 실험

### 🌟 추가 활용 팁

- **커스텀 검색**: `example_6_hybrid_search()` 함수를 수정하여 자신만의 검색 쿼리 테스트
- **배치 처리**: 스크립트를 참고하여 대량 문서 처리 자동화
- **모니터링**: 정기적으로 `--health` 모드 실행하여 시스템 상태 점검
- **개발 참고**: 각 API 호출 코드를 복사하여 자신의 애플리케이션에 통합

## 🚨 문제 해결

### FastAPI 서비스가 시작되지 않는 경우
1. 10분 정도 기다린 후 재시작: `docker-compose restart fastapi-search`
2. 로그 확인: `docker-compose logs fastapi-search`
3. 메모리 부족 시 Docker 메모리 할당량 증가

### OpenSearch 연결 오류
1. 환경변수 확인: `.env` 파일의 `OPENSEARCH_ADMIN_PASSWORD`
2. 포트 충돌 확인: 9200, 9201, 9202 포트 사용 여부
3. Docker 서비스 재시작: `docker-compose restart`

### 모델 로딩 오류
1. 인터넷 연결 확인 (HuggingFace 모델 다운로드)
2. 충분한 디스크 공간 확보 (최소 5GB)
3. 시스템 메모리 확인 (최소 8GB 권장)

## 📞 지원

문제 발생 시 다음 정보와 함께 문의하세요:
- 오류 메시지
- `docker-compose logs` 출력
- 시스템 사양 (메모리, 디스크)
- 네트워크 환경

---

**🎯 Happy Searching! 효과적인 문서 검색을 위한 PharmaTech 시스템을 활용하세요.** 