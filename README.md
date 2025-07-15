# OpenSearch 클러스터 설치 및 실행 가이드

이 프로젝트는 Docker Compose를 사용하여 OpenSearch 클러스터를 구성하고 실행하는 환경을 제공합니다.

## 📋 목차
- [사전 요구사항](#사전-요구사항)
- [빠른 시작](#빠른-시작)
- [상세 설정](#상세-설정)
- [접속 정보](#접속-정보)
- [주요 명령어](#주요-명령어)
- [FastAPI 서버](#fastapi-서버)
- [트러블슈팅](#트러블슈팅)
- [클러스터 구성](#클러스터-구성)

## 🛠 사전 요구사항

### 1. Docker 설치
Windows에서 Docker Desktop을 설치해야 합니다:
1. [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) 다운로드
2. 설치 후 재부팅
3. Docker Desktop 실행 확인

### 2. Docker Compose 설치 확인
Docker Desktop에는 Docker Compose가 포함되어 있습니다:
```powershell
docker-compose --version
```

### 3. 시스템 요구사항
- **메모리**: 최소 4GB RAM (권장 8GB 이상)
- **디스크**: 최소 10GB 여유 공간
- **포트**: 9200, 9201, 9600, 9601, 5601 포트가 사용 가능해야 함

## 🚀 빠른 시작

### 1. 환경변수 설정
프로젝트 루트 디렉토리에 `.env` 파일을 생성합니다:

```powershell
echo "OPENSEARCH_ADMIN_PASSWORD=MyStrongPassword123!" > .env
```

> ⚠️ **보안 주의**: 실제 운영환경에서는 더 강력한 비밀번호를 사용하세요.

### 2. 플러그인 설정 (선택사항)
플러그인을 설치하려면 `plugins.txt` 파일을 생성합니다:

```powershell
echo "# OpenSearch 플러그인 목록" > plugins.txt
echo "# 예시: analysis-nori" >> plugins.txt
```

### 3. OpenSearch 클러스터 실행

#### 백그라운드에서 실행:
```powershell
docker-compose up -d
```

#### 포그라운드에서 실행 (로그 확인):
```powershell
docker-compose up
```

### 4. 실행 상태 확인
```powershell
docker-compose ps
```

## ⚙️ 상세 설정

### 환경변수 옵션
`.env` 파일에서 다음 설정을 변경할 수 있습니다:

```env
# 관리자 비밀번호 (필수)
OPENSEARCH_ADMIN_PASSWORD=MyStrongPassword123!

# 클러스터 이름 (선택사항)
CLUSTER_NAME=opensearch-cluster

# Java 힙 메모리 설정 (선택사항)
OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
```

### 메모리 설정 조정
시스템 사양에 따라 `docker-compose.yml`에서 메모리 설정을 조정할 수 있습니다:

```yaml
# Java 힙 메모리 (시스템 RAM의 50% 권장)
OPENSEARCH_JAVA_OPTS: -Xms1g -Xmx1g

# 컨테이너 메모리 제한 (Java 힙보다 크게 설정)
deploy:
  resources:
    limits:
      memory: 2g
```

## 🌐 접속 정보

### OpenSearch API
- **주 노드**: https://localhost:9200
- **보조 노드**: https://localhost:9201
- **사용자명**: admin
- **비밀번호**: `.env` 파일에 설정한 값

### OpenSearch Dashboards (Kibana 대체)
- **URL**: http://localhost:5601
- **사용자명**: admin
- **비밀번호**: `.env` 파일에 설정한 값

### 접속 테스트
```powershell
# PowerShell에서 API 테스트 (인증서 검증 무시)
curl -k -u admin:MyStrongPassword123! https://localhost:9200

# 클러스터 상태 확인
curl -k -u admin:MyStrongPassword123! https://localhost:9200/_cluster/health
```

## 📝 주요 명령어

### 클러스터 관리
```powershell
# 클러스터 시작
docker-compose up -d

# 클러스터 중지
docker-compose down

# 클러스터 재시작
docker-compose restart

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그 확인
docker-compose logs -f opensearch-node1
```

### 데이터 관리
```powershell
# 데이터 볼륨 포함 완전 삭제
docker-compose down -v

# 컨테이너 이미지 재빌드
docker-compose build --no-cache
```

### 상태 확인
```powershell
# 실행 중인 컨테이너 확인
docker-compose ps

# 리소스 사용량 확인
docker stats
```

## 🔧 트러블슈팅

### 1. 메모리 부족 오류
**증상**: `max virtual memory areas vm.max_map_count [65530] is too low`

**해결방법 (Windows WSL2)**:
```powershell
# WSL2에서 실행
wsl -d docker-desktop
sysctl -w vm.max_map_count=262144
```

### 2. 포트 충돌
**증상**: `port is already allocated`

**해결방법**:
```powershell
# 포트 사용 확인
netstat -ano | findstr :9200

# 프로세스 종료 (PID 확인 후)
taskkill /F /PID <PID번호>
```

### 3. 디스크 공간 부족
**해결방법**:
```powershell
# 사용하지 않는 Docker 리소스 정리
docker system prune -a -f

# 볼륨 정리
docker volume prune -f
```

### 4. 인증서 오류
**증상**: SSL certificate problem

**해결방법**: curl에 `-k` 옵션 사용 또는 HTTPS 대신 HTTP 사용

### 5. 컨테이너 빌드 실패
**원인**: `plugins.txt` 파일이 없는 경우

**해결방법**:
```powershell
# 빈 플러그인 파일 생성
echo "# No plugins" > plugins.txt
```

## 🏗 클러스터 구성

### 노드 구성
- **opensearch-node1**: 마스터 노드 (포트 9200, 9600)
- **opensearch-node2**: 데이터 노드 (포트 9201, 9601)
- **opensearch-dashboards**: 대시보드 (포트 5601)

### 네트워크
- **네트워크 이름**: opensearch-net
- **드라이버**: bridge

### 스토리지
- **opensearch-data1**: 노드1 데이터 볼륨
- **opensearch-data2**: 노드2 데이터 볼륨

## 📊 성능 모니터링

### Performance Analyzer 접속
- **노드1**: http://localhost:9600/_plugins/_performanceanalyzer/
- **노드2**: http://localhost:9601/_plugins/_performanceanalyzer/

### 주요 지표 확인
```bash
# 클러스터 상태
curl -k -u admin:password https://localhost:9200/_cluster/health?pretty

# 노드 정보
curl -k -u admin:password https://localhost:9200/_nodes?pretty

# 인덱스 정보
curl -k -u admin:password https://localhost:9200/_cat/indices?v
```

## 🌐 FastAPI 서버

OpenSearch 클러스터와 상호작용하는 REST API 서버도 제공됩니다.

### 서버 설치 및 실행

#### 1. Python 의존성 설치
```powershell
# 가상환경 생성 (권장)
python -m venv venv
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

#### 2. FastAPI 서버 실행
```powershell
# 개발 모드
python main.py

# 또는 uvicorn 직접 실행
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### API 엔드포인트

#### 기본 엔드포인트
- `GET /` - 서버 상태 확인
- `GET /health` - OpenSearch 연결 상태 확인
- `GET /docs` - API 문서 (Swagger UI)

#### 주요 API
- `POST /search` - 하이브리드 검색 (BM25 + 벡터 + 리랭크)
- `POST /documents` - 단일 문서 색인
- `POST /documents/bulk` - 여러 문서 일괄 색인
- `POST /index` - 인덱스 생성
- `DELETE /index/{index_name}` - 인덱스 삭제
- `POST /load-jsonl` - JSONL 파일 로드 및 색인

### API 사용 예제

#### 검색 API 호출
```powershell
# PowerShell 예제
$searchData = @{
    keywords = @("의료기기", "안전")
    query_text = "의료기기 안전 관리 규정을 찾아주세요"
    top_k = 5
    use_rerank = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/search" -Method Post -Body $searchData -ContentType "application/json"
```

#### Python 클라이언트 사용
```powershell
# 전체 기능 테스트
python test_client.py

# 대화형 검색 테스트
python test_client.py interactive
```

### API 접속 정보
- **서버 URL**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **대안 문서**: http://localhost:8000/redoc

---

## 📞 지원

문제가 발생하면 다음을 확인하세요:
1. [OpenSearch 공식 문서](https://opensearch.org/docs/)
2. [Docker Compose 문서](https://docs.docker.com/compose/)
3. 로그 파일: `docker-compose logs`

---

**참고**: 이 설정은 개발 및 테스트 환경용입니다. 운영 환경에서는 보안 설정을 강화하고 성능 튜닝을 수행하세요. 