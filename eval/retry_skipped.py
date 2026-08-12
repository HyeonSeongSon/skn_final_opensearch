"""
generate_questions.py 실행 후 JSON 파싱 실패로 스킵된 행만 골라 재시도한다.

data/processed/*.jsonl의 전체 대상 행과 eval/generated_questions.jsonl에 이미
있는 (source_file, source_line) 쌍을 비교해서 빠진 행을 자동으로 찾아낸다.
generate_questions.py와 달리 temperature를 높여(기본 0.5) 시도마다 다른 응답을
받도록 해서, 동일 프롬프트가 temperature=0으로 계속 같은 형식으로 실패하는
상황을 피한다. 성공하면 eval/generated_questions.jsonl에 이어서(append) 기록한다.

사용 예:
    python eval/retry_skipped.py
    python eval/retry_skipped.py --max-attempts 5
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_questions import (  # noqa: E402
    QUESTION_TEMPLATE,
    load_source_rows,
    group_siblings,
    compute_unique_snippet,
    parse_llm_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_existing_keys(output_path: Path) -> set[tuple]:
    """output_path에 이미 기록된 (source_file, source_line) 쌍을 모은다."""
    keys = set()
    if not output_path.exists():
        return keys
    with open(output_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            keys.add((record.get("source_file"), record.get("source_line")))
    return keys


def try_generate(
    llm: ChatOpenAI, template: ChatPromptTemplate, row: dict, max_attempts: int,
) -> list[dict] | None:
    for attempt in range(1, max_attempts + 1):
        messages = template.format_messages(
            문서명=row.get("문서명") or "",
            장=row.get("장") or "",
            조=row.get("조") or "",
            문서내용=row.get("문서내용") or "",
        )
        response = llm.invoke(messages)
        parsed = parse_llm_json(response.content)
        if parsed is not None:
            logger.info("[RETRY-OK] %s:%s (attempt %d/%d)",
                        row.get("_source_file"), row.get("_line_no"), attempt, max_attempts)
            return parsed
        logger.warning(
            "[RETRY-FAIL] %s:%s (attempt %d/%d) - JSON 파싱 실패",
            row.get("_source_file"), row.get("_line_no"), attempt, max_attempts,
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="generate_questions.py에서 스킵된 행만 재시도한다.")
    parser.add_argument("--input-glob", default="data/processed/*.jsonl")
    parser.add_argument("--output", default="eval/generated_questions.jsonl")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--max-attempts", type=int, default=5)
    args = parser.parse_args()

    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

    input_glob = args.input_glob if os.path.isabs(args.input_glob) else str(REPO_ROOT / args.input_glob)
    rows = load_source_rows(input_glob)
    groups = group_siblings(rows)

    output_path = REPO_ROOT / args.output
    existing_keys = load_existing_keys(output_path)

    missing_rows = [r for r in rows if (r["_source_file"], r["_line_no"]) not in existing_keys]

    if not missing_rows:
        logger.info("스킵된 행이 없습니다. 재시도할 게 없습니다.")
        return

    logger.info(
        "스킵된 행 %d개를 재시도합니다: %s",
        len(missing_rows), [(r["_source_file"], r["_line_no"]) for r in missing_rows],
    )

    llm = ChatOpenAI(model=args.model, temperature=args.temperature)
    template = ChatPromptTemplate.from_template(QUESTION_TEMPLATE)

    new_records = []
    still_failing = []

    for row in missing_rows:
        key = (row.get("문서명"), row.get("장"), row.get("조"))
        siblings = groups[key]

        parsed = try_generate(llm, template, row, args.max_attempts)
        if parsed is None:
            still_failing.append((row["_source_file"], row["_line_no"]))
            continue

        snippet = compute_unique_snippet(row, siblings)
        assert snippet in (row.get("문서내용") or ""), "snippet은 반드시 원본 문서내용의 부분문자열이어야 합니다."

        for item in parsed:
            query_id = f"{row['_source_file'].removesuffix('.jsonl')}-{row['_line_no']}-{item['query_type']}"
            new_records.append({
                "query_id": query_id,
                "query_type": item["query_type"],
                "query_text": item["query_text"],
                "keywords": item["keywords"],
                "relevant": [{
                    "문서명": row.get("문서명"),
                    "장": row.get("장"),
                    "조": row.get("조"),
                    "snippet": snippet,
                }],
                "source_file": row["_source_file"],
                "source_line": row["_line_no"],
                "model": args.model,
                "notes": None,
            })

    if new_records:
        with open(output_path, "a", encoding="utf-8") as f:
            for record in new_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("%d개 질문을 %s에 추가했습니다.", len(new_records), output_path)

    if still_failing:
        logger.warning("끝까지 실패한 행: %s", still_failing)
    else:
        logger.info("모든 스킵된 행을 성공적으로 복구했습니다.")


if __name__ == "__main__":
    main()
