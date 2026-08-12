"""
'문서명+장+조+문서내용'을 결합한 텍스트로 임베딩을 계산해 별도 인덱스에 색인한다.

기존 opensearch_api.py, opensearch.py, 기존 인덱스(internal_regulations_index)는
전혀 건드리지 않는다. 완전히 독립된 스크립트로, OpenSearchClient(opensearch.py)도
가져다 쓰지 않고 OpenSearch/SentenceTransformer를 직접 연결해서 새 인덱스
(기본: internal_regulations_index_combined)에 색인한다.

문서내용 필드 자체는 원본 그대로 저장한다(BM25 검색 조건을 기존 인덱스와
동일하게 유지하기 위해). 오직 content_vector를 계산할 때 쓰는 입력 텍스트만
'문서명 장 조 문서내용'으로 결합해서, 벡터 임베딩 입력 텍스트 구성 방식의
효과만 순수하게 비교할 수 있게 한다.

이 스크립트는 sentence-transformers 모델을 로드해야 하므로, 로컬 호스트가
아니라 이미 의존성이 설치되어 있는 fastapi-search 컨테이너 안에서 실행한다:
    docker compose exec fastapi-search python eval/index_combined_embedding.py
"""
import argparse
import glob
import json
import os

import numpy as np
from dotenv import load_dotenv
from opensearchpy import OpenSearch, helpers
from sentence_transformers import SentenceTransformer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAPPING = {
    "settings": {"index": {"knn": True}},
    "mappings": {
        "properties": {
            "문서명": {"type": "keyword"},
            "장": {"type": "text"},
            "조": {"type": "text"},
            "문서내용": {"type": "text"},
            "출처파일": {"type": "keyword"},
            "content_vector": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
            },
        }
    },
}


def load_rows(input_glob: str) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(input_glob)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                doc["출처파일"] = path
                rows.append(doc)
    return rows


def build_embedding_text(doc: dict) -> str:
    parts = [doc.get("문서명") or "", doc.get("장") or "", doc.get("조") or "", doc.get("문서내용") or ""]
    return " ".join(p for p in parts if p).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="문서명+장+조+문서내용 결합 임베딩으로 별도 인덱스를 만든다.")
    parser.add_argument("--input-glob", default="data/processed/*.jsonl")
    parser.add_argument("--index-name", default="internal_regulations_index_combined")
    parser.add_argument("--recreate", action="store_true", help="인덱스가 이미 있으면 삭제 후 재생성")
    args = parser.parse_args()

    load_dotenv(dotenv_path=os.path.join(REPO_ROOT, ".env"))

    host = os.getenv("OPENSEARCH_HOST", "localhost")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))
    print(f"OpenSearch 연결 대상: {host}:{port}")

    client = OpenSearch(hosts=[{"host": host, "port": port}], timeout=30)
    if not client.ping():
        raise SystemExit("OpenSearch에 연결할 수 없습니다.")

    if client.indices.exists(index=args.index_name):
        if args.recreate:
            client.indices.delete(index=args.index_name)
            print(f"기존 인덱스 '{args.index_name}' 삭제됨.")
        else:
            raise SystemExit(f"인덱스 '{args.index_name}'가 이미 존재합니다. --recreate로 재생성하세요.")

    client.indices.create(index=args.index_name, body=MAPPING)
    print(f"인덱스 '{args.index_name}' 생성 완료.")

    input_glob = args.input_glob if os.path.isabs(args.input_glob) else os.path.join(REPO_ROOT, args.input_glob)
    rows = load_rows(input_glob)
    print(f"대상 문서 {len(rows)}건 로드.")

    print("SentenceTransformer(nlpai-lab/KURE-v1) 로드 중...")
    model = SentenceTransformer("nlpai-lab/KURE-v1")

    embed_texts = [build_embedding_text(doc) for doc in rows]
    print("임베딩 계산 중 (배치)...")
    embeddings = model.encode(embed_texts, batch_size=32, show_progress_bar=True)

    for doc, emb in zip(rows, embeddings):
        doc["content_vector"] = np.array(emb).tolist()

    actions = [{"_index": args.index_name, "_source": doc} for doc in rows]
    success, failed = helpers.bulk(client, actions, refresh=True)
    print(f"색인 완료: 성공 {success}건, 실패 {len(failed) if failed else 0}건")


if __name__ == "__main__":
    main()
