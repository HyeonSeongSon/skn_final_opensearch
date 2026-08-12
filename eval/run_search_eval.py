"""
eval/generated_questions.jsonl + eval/collision_questions.jsonl을 읽어
실행 중인 FastAPI 서버의 POST /search를 호출하고 Recall@1/3/5, MRR을
query_type별(exact/paraphrase/collision)로 집계한다.

주의: opensearch.py의 normalized_hybrid_search()는 BM25/벡터 검색 결과를
합칠 때 doc_id = 문서명+장+조 (문서내용 미포함)를 키로 쓰는 딕셔너리에
무조건 덮어쓰기를 한다. 즉 같은 조 밑에 여러 형제 항목(예: welfare 제4조의
결혼/출산/사망/기타)이 있으면 그중 하나만 결과에 남을 수 있고, 어느 것이
남는지는 관련도가 아니라 OpenSearch가 반환한 순서에 따른 우연이다.
collision 유형의 Recall이 낮게 나오면 이게 전처리(헤더 병합) 실패 때문인지
이 doc_id 충돌 때문인지 eval_results.jsonl의 returned_top5를 직접 봐서
구분해야 한다. 이 스크립트는 이 버그를 고치지 않는다 (범위 밖).

사용 예:
    python eval/run_search_eval.py
    python eval/run_search_eval.py --limit 5
"""
import argparse
import json
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
QUERY_TYPE_ORDER = ["ALL", "exact", "paraphrase", "collision"]


def load_eval_records(paths: list[str]) -> list[dict]:
    """여러 jsonl 파일을 읽어 이어붙인다. 필수 키가 없는 줄은 건너뛰고 경고한다."""
    required_keys = {"query_id", "query_type", "query_text", "keywords", "relevant"}
    records = []
    for path_str in paths:
        path = REPO_ROOT / path_str
        if not path.exists():
            logger.warning("[SKIP-FILE] %s가 존재하지 않습니다.", path)
            continue
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                missing = required_keys - record.keys()
                if missing or not record.get("relevant"):
                    logger.warning(
                        "[SKIP-RECORD] %s:%d - 필수 필드 누락 또는 relevant가 비어있음 (%s)",
                        path_str, line_no, missing,
                    )
                    continue
                records.append(record)
    return records


def call_search(
    session: requests.Session,
    base_url: str,
    record: dict,
    top_k: int,
    rerank_top_k: int,
    use_rerank: bool,
    timeout: float,
    index_name: str,
) -> dict | None:
    payload = {
        "keywords": record["keywords"],
        "query_text": record["query_text"],
        "top_k": top_k,
        "rerank_top_k": rerank_top_k,
        "use_rerank": use_rerank,
        "index_name": index_name,
    }
    try:
        response = session.post(f"{base_url}/search", json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        if not body.get("success", True):
            logger.warning("[SEARCH-FAIL] %s - %s", record["query_id"], body.get("message"))
            return None
        return body
    except requests.RequestException as e:
        logger.warning("[SEARCH-ERROR] %s - %s", record["query_id"], e)
        return None


def is_match(hit_source: dict, relevant_item: dict) -> bool:
    if (hit_source.get("문서명") or None) != (relevant_item.get("문서명") or None):
        return False
    if (hit_source.get("장") or None) != (relevant_item.get("장") or None):
        return False
    if (hit_source.get("조") or None) != (relevant_item.get("조") or None):
        return False
    snippet = relevant_item.get("snippet") or ""
    return snippet in (hit_source.get("문서내용") or "")


def evaluate_record(record: dict, results: list[dict]) -> dict:
    rank_of_first_hit = None
    for i, hit in enumerate(results):
        source = hit.get("source", {})
        if any(is_match(source, r) for r in record["relevant"]):
            rank_of_first_hit = i + 1
            break

    reciprocal_rank = 1.0 / rank_of_first_hit if rank_of_first_hit else 0.0

    top5_preview = []
    for hit in results[:5]:
        source = hit.get("source", {})
        content = source.get("문서내용") or ""
        top5_preview.append({
            "문서명": source.get("문서명"),
            "장": source.get("장"),
            "조": source.get("조"),
            "문서내용_preview": content[:60],
            "combined_score": hit.get("combined_score"),
            "rerank_score": hit.get("rerank_score"),
        })

    return {
        "query_id": record["query_id"],
        "query_type": record["query_type"],
        "query_text": record["query_text"],
        "keywords": record["keywords"],
        "relevant": record["relevant"],
        "error": False,
        "error_detail": None,
        "hit_at_1": rank_of_first_hit is not None and rank_of_first_hit <= 1,
        "hit_at_3": rank_of_first_hit is not None and rank_of_first_hit <= 3,
        "hit_at_5": rank_of_first_hit is not None and rank_of_first_hit <= 5,
        "rank_of_first_hit": rank_of_first_hit,
        "reciprocal_rank": reciprocal_rank,
        "returned_top5": top5_preview,
    }


def make_error_row(record: dict, error_detail: str) -> dict:
    return {
        "query_id": record["query_id"],
        "query_type": record["query_type"],
        "query_text": record["query_text"],
        "keywords": record["keywords"],
        "relevant": record["relevant"],
        "error": True,
        "error_detail": error_detail,
        "hit_at_1": False,
        "hit_at_3": False,
        "hit_at_5": False,
        "rank_of_first_hit": None,
        "reciprocal_rank": 0.0,
        "returned_top5": [],
    }


def aggregate(eval_rows: list[dict]) -> dict:
    def summarize(rows: list[dict]) -> dict:
        n = len(rows)
        if n == 0:
            return {"n": 0, "recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0, "mrr": 0.0}
        return {
            "n": n,
            "recall_at_1": sum(r["hit_at_1"] for r in rows) / n,
            "recall_at_3": sum(r["hit_at_3"] for r in rows) / n,
            "recall_at_5": sum(r["hit_at_5"] for r in rows) / n,
            "mrr": sum(r["reciprocal_rank"] for r in rows) / n,
        }

    agg = {"ALL": summarize(eval_rows)}
    for qtype in ("exact", "paraphrase", "collision"):
        agg[qtype] = summarize([r for r in eval_rows if r["query_type"] == qtype])
    return agg


def print_summary_table(agg: dict, error_count: int) -> None:
    header = f"{'query_type':<12}{'N':>5}{'Recall@1':>10}{'Recall@3':>10}{'Recall@5':>10}{'MRR':>8}"
    print(header)
    print("-" * len(header))
    for qtype in QUERY_TYPE_ORDER:
        stats = agg.get(qtype)
        if stats is None or stats["n"] == 0:
            continue
        print(
            f"{qtype:<12}{stats['n']:>5}"
            f"{stats['recall_at_1']:>10.3f}{stats['recall_at_3']:>10.3f}"
            f"{stats['recall_at_5']:>10.3f}{stats['mrr']:>8.3f}"
        )
    print("-" * len(header))
    print(f"요청 실패(에러)로 처리된 질의 수: {error_count} (미스로 집계에 포함됨)")
    if agg.get("collision", {}).get("n", 0) > 0:
        print(
            "\n[참고] normalized_hybrid_search()는 같은 (문서명,장,조)를 가진 형제 항목이 여러 개일 때 "
            "doc_id 충돌로 인해 그중 하나만 결과에 남을 수 있습니다(opensearch.py). "
            "collision 유형 Recall이 낮다면 eval_results.jsonl의 returned_top5를 직접 확인해 "
            "전처리(헤더 병합) 실패 때문인지 이 doc_id 충돌 때문인지 구분하세요."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 API에 대해 평가 질의셋을 실행하고 Recall/MRR을 계산한다.")
    parser.add_argument(
        "--input", nargs="+",
        default=["eval/generated_questions.jsonl", "eval/collision_questions.jsonl"],
    )
    parser.add_argument("--base-url", default="http://localhost:8010")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--rerank-top-k", type=int, default=10)
    parser.add_argument("--no-rerank", action="store_true", help="BGE 리랭커를 끄고 하이브리드 combined_score 순위만으로 평가")
    parser.add_argument("--index-name", default="internal_regulations_index")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", default="eval/eval_results.jsonl")
    args = parser.parse_args()

    records = load_eval_records(args.input)
    logger.info("평가 질의 %d개를 로드했습니다.", len(records))
    if args.limit is not None:
        records = records[: args.limit]

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    eval_rows = []
    error_count = 0

    for record in records:
        body = call_search(
            session, args.base_url, record,
            top_k=args.top_k, rerank_top_k=args.rerank_top_k,
            use_rerank=not args.no_rerank, timeout=args.timeout,
            index_name=args.index_name,
        )
        if body is None:
            eval_rows.append(make_error_row(record, "요청 실패 또는 success=False"))
            error_count += 1
            continue
        eval_rows.append(evaluate_record(record, body.get("results", [])))

    output_path = REPO_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for row in eval_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("상세 결과를 %s에 기록했습니다.", output_path)

    agg = aggregate(eval_rows)
    print()
    print_summary_table(agg, error_count)


if __name__ == "__main__":
    main()
