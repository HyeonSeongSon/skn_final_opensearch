"""
eval/generated_questions.jsonl에서 같은 조(문서명+장+조) 안의 서로 다른 행이
동일한 query_text를 갖게 된 경우(모호한 질문)를 찾아 재생성한다.

generate_questions.py의 기본 프롬프트는 한 청크만 보고 질문을 만들기 때문에,
가/나/다 같은 짧은 나열 항목에서 "제N조 OOO에 대해 설명해주세요"처럼 조 제목만
반복하는 두루뭉술한 질문이 여러 형제 항목에 중복 생성될 수 있다. 이 스크립트는
문제가 된 행에 한해 "같은 조의 다른 항목들"을 프롬프트에 함께 제공하고, 그
항목들과 겹치지 않는 질문을 명시적으로 요구해서 재생성한다.

사용 예:
    python eval/fix_ambiguous_questions.py
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
    load_source_rows,
    group_siblings,
    compute_unique_snippet,
    parse_llm_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

DISAMBIGUATION_TEMPLATE = """
당신은 사내 규정 검색 시스템의 평가용 질문을 생성하는 챗봇입니다.
아래는 사내 규정 문서의 한 조각(chunk)입니다. 같은 조 안에 여러 항목이 있으므로,
반드시 이 항목만의 고유한 내용을 활용해 질문을 만들어야 합니다.

문서명: {문서명}
장: {장}
조: {조}

[이번에 질문을 만들 항목]
{문서내용}

[같은 조 안의 다른 항목들 - 질문이 이 항목들에도 똑같이 적용될 수 있으면 안 됨]
{sibling_contents}

이 항목만을 검색하면 찾아낼 수 있어야 하는, 다른 항목들과는 명확히 구분되는 사용자 질문을 반드시 2개 생성하세요.

1번 질문(exact 유형): 이 항목에만 등장하는 구체적인 단어(숫자, 고유명사, 세부 조건 등)를 반드시 포함한 직접적인 질문으로 작성하세요.
"제N조 OOO에 대해 설명해주세요/알고 싶습니다"처럼 조 제목만 반복하는 두루뭉술한 질문은 절대 금지합니다.
2번 질문(paraphrase 유형): 같은 것을 다른 표현으로 묻되, 여전히 이 항목만을 가리켜야 하며 다른 항목에도 똑같이 적용될 수 있는 일반적인 질문이면 안 됩니다.

각 질문마다 검색에 쓸 만한 키워드를 2개에서 4개까지 뽑으세요.

아래 조건을 반드시 만족해서 출력하세요.

1. 반드시 JSON 배열(리스트) 형태로만 출력하세요. 배열의 길이는 정확히 2여야 합니다.
2. 배열의 첫 번째 원소는 반드시 "query_type"이 "exact"여야 하고, 두 번째 원소는 반드시 "paraphrase"여야 합니다.
3. 각 원소는 "query_type", "query_text"(문자열), "keywords"(문자열 리스트, 2~4개) 키를 가진 JSON 객체여야 합니다.
4. 마크다운 코드블록(```), 설명, 주석 등 JSON 이외의 어떤 텍스트도 출력하지 마세요.
5. 문서에 없는 사실을 지어내지 마세요.

출력 예시:
[{{"query_type": "exact", "query_text": "...", "keywords": ["...", "..."]}}, {{"query_type": "paraphrase", "query_text": "...", "keywords": ["...", "..."]}}]
"""


def load_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def find_ambiguous_row_keys(records: list[dict]) -> set[tuple]:
    """같은 (문서명,장,조) 그룹 안에서 query_text가 겹치는 행들의
    (source_file, source_line) 키 집합을 반환한다."""
    from collections import defaultdict

    by_group_and_type = defaultdict(list)
    for r in records:
        rel = r["relevant"][0]
        group_key = (rel.get("문서명"), rel.get("장"), rel.get("조"), r["query_type"])
        by_group_and_type[group_key].append(r)

    bad_keys = set()
    for group_key, group_records in by_group_and_type.items():
        texts = [gr["query_text"] for gr in group_records]
        if len(texts) != len(set(texts)):
            seen = {}
            for gr in group_records:
                if seen.get(gr["query_text"]) or texts.count(gr["query_text"]) > 1:
                    bad_keys.add((gr["source_file"], gr["source_line"]))
                seen[gr["query_text"]] = True
    return bad_keys


def build_sibling_contents_text(row: dict, siblings: list[dict]) -> str:
    others = [s for s in siblings if s is not row]
    if not others:
        return "(형제 항목 없음)"
    return "\n".join(f"- {(s.get('문서내용') or '').strip()}" for s in others)


def try_generate(
    llm: ChatOpenAI,
    template: ChatPromptTemplate,
    row: dict,
    siblings: list[dict],
    forbidden_texts: set[str],
    max_attempts: int,
) -> list[dict] | None:
    sibling_contents = build_sibling_contents_text(row, siblings)
    for attempt in range(1, max_attempts + 1):
        messages = template.format_messages(
            문서명=row.get("문서명") or "",
            장=row.get("장") or "",
            조=row.get("조") or "",
            문서내용=row.get("문서내용") or "",
            sibling_contents=sibling_contents,
        )
        response = llm.invoke(messages)
        parsed = parse_llm_json(response.content)
        if parsed is None:
            logger.warning("[FIX-PARSE-FAIL] %s:%s (attempt %d/%d)",
                            row.get("_source_file"), row.get("_line_no"), attempt, max_attempts)
            continue
        if any(item["query_text"] in forbidden_texts for item in parsed):
            logger.warning("[FIX-STILL-DUP] %s:%s (attempt %d/%d) - 여전히 형제 항목과 겹침",
                            row.get("_source_file"), row.get("_line_no"), attempt, max_attempts)
            continue
        logger.info("[FIX-OK] %s:%s (attempt %d/%d)",
                     row.get("_source_file"), row.get("_line_no"), attempt, max_attempts)
        return parsed
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="같은 조 안에서 중복된 query_text를 재생성한다.")
    parser.add_argument("--input-glob", default="data/processed/*.jsonl")
    parser.add_argument("--questions-file", default="eval/generated_questions.jsonl")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

    questions_path = REPO_ROOT / args.questions_file
    records = load_records(questions_path)
    logger.info("기존 질의 %d개를 로드했습니다.", len(records))

    bad_keys = find_ambiguous_row_keys(records)
    if not bad_keys:
        logger.info("중복된 query_text가 없습니다. 수정할 게 없습니다.")
        return
    logger.info("중복 그룹에 속한 행 %d개를 재생성합니다: %s", len(bad_keys), sorted(bad_keys))

    input_glob = args.input_glob if os.path.isabs(args.input_glob) else str(REPO_ROOT / args.input_glob)
    all_rows = load_source_rows(input_glob)
    groups = group_siblings(all_rows)
    rows_by_key = {(r["_source_file"], r["_line_no"]): r for r in all_rows}

    # 그대로 남길(정상) 레코드와, 재생성 대상이라 제거할 레코드를 분리한다.
    kept_records = [r for r in records if (r["source_file"], r["source_line"]) not in bad_keys]
    removed_records = [r for r in records if (r["source_file"], r["source_line"]) in bad_keys]
    logger.info("정상 레코드 %d개 유지, %d개 레코드(재생성 대상 %d개 행) 제거.",
                len(kept_records), len(removed_records), len(bad_keys))

    llm = ChatOpenAI(model=args.model, temperature=args.temperature)
    template = ChatPromptTemplate.from_template(DISAMBIGUATION_TEMPLATE)

    new_records = list(kept_records)
    still_bad = []

    for key in sorted(bad_keys):
        row = rows_by_key.get(key)
        if row is None:
            logger.warning("[FIX-MISSING-SOURCE] %s - data/processed에서 해당 행을 찾을 수 없습니다.", key)
            continue

        group_key = (row.get("문서명"), row.get("장"), row.get("조"))
        siblings = groups[group_key]

        # 지금까지 살아남은(정상) 형제 질문 + 이번 배치에서 이미 새로 만든 형제 질문과 겹치면 안 됨
        forbidden_texts = {
            r["query_text"] for r in new_records
            if (r["relevant"][0].get("문서명"), r["relevant"][0].get("장"), r["relevant"][0].get("조")) == group_key
        }

        parsed = try_generate(llm, template, row, siblings, forbidden_texts, args.max_attempts)
        if parsed is None:
            still_bad.append(key)
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

    with open(questions_path, "w", encoding="utf-8") as f:
        for record in new_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("%s를 %d개 레코드로 다시 기록했습니다.", questions_path, len(new_records))

    remaining_bad = find_ambiguous_row_keys(new_records)
    if remaining_bad:
        logger.warning("여전히 중복이 남은 행: %s", sorted(remaining_bad))
    else:
        logger.info("모든 중복이 해소되었습니다.")
    if still_bad:
        logger.warning("끝까지 재생성 실패한 행(정상 레코드 없이 제거됨): %s", still_bad)


if __name__ == "__main__":
    main()
