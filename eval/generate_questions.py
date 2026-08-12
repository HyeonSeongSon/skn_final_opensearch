"""
data/processed/*.jsonl의 각 조항(청크)마다 평가용 질의를 2개씩 생성한다.
  - exact 유형: 조항의 키워드/조 제목을 그대로 활용한 직접적인 질문
  - paraphrase 유형: 같은 내용을 다른 표현으로 묻는 질문

OpenSearchClient(opensearch.py)는 인스턴스화하지 않는다 (SentenceTransformer,
BGE reranker 로딩과 OpenSearch 연결까지 강제되어 느려짐). ChatOpenAI를
opensearch.py의 get_keyword()와 동일한 방식(ChatPromptTemplate.from_template
-> format_messages -> llm.invoke -> .content)으로만 사용한다.

사용 예:
    python eval/generate_questions.py
    python eval/generate_questions.py --limit 5 --output eval/generated_questions.sample.jsonl
"""
import argparse
import glob
import json
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

QUESTION_TEMPLATE = """
당신은 사내 규정 검색 시스템의 평가용 질문을 생성하는 챗봇입니다.
아래는 사내 규정 문서의 한 조각(chunk)입니다.

문서명: {문서명}
장: {장}
조: {조}
내용: {문서내용}

이 내용을 검색하면 찾아낼 수 있어야 하는 사용자 질문을 반드시 2개 생성하세요.

1번 질문(exact 유형): 위 내용에 등장하는 핵심 단어(조 제목, 고유명사, 숫자 등)를 그대로 활용한 직접적인 질문으로 작성하세요.
2번 질문(paraphrase 유형): 위 내용과 같은 것을 묻되, 핵심 단어를 그대로 쓰지 말고 동의어나 일상적인 말투로 바꿔서 작성하세요.

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

REPAIR_TEMPLATE = """
아래는 JSON 파싱에 실패한 이전 응답입니다.

{previous_response}

다시 한 번, 오직 유효한 JSON 배열만 출력하세요. 마크다운 코드블록이나 설명 문구는 절대 포함하지 마세요.
배열 길이는 정확히 2여야 하며, 첫 번째 원소의 "query_type"은 "exact", 두 번째 원소는 "paraphrase"여야 합니다.
각 원소는 "query_type", "query_text", "keywords" 키를 가져야 합니다.
"""

CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def load_source_rows(input_glob: str) -> list[dict]:
    """input_glob에 매칭되는 모든 jsonl 파일을 읽어 순서를 보존한 행 리스트로 반환한다.
    장과 조가 둘 다 null인 순수 제목 placeholder 행은 제외한다."""
    rows = []
    for path in sorted(glob.glob(input_glob)):
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                if doc.get("장") is None and doc.get("조") is None:
                    continue
                doc = dict(doc)
                doc["_source_file"] = os.path.basename(path)
                doc["_line_no"] = line_no
                rows.append(doc)
    return rows


def group_siblings(rows: list[dict]) -> dict[tuple, list[dict]]:
    """(문서명, 장, 조)가 같은 행들을 묶는다."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row.get("문서명"), row.get("장"), row.get("조"))
        groups.setdefault(key, []).append(row)
    return groups


def compute_unique_snippet(row: dict, siblings: list[dict], min_len: int = 8, max_len: int = 60) -> str:
    """형제 행들의 문서내용에는 등장하지 않는 row 문서내용의 최소 고유 접두사를 찾는다."""
    content = (row.get("문서내용") or "").strip()
    other_contents = [(s.get("문서내용") or "").strip() for s in siblings if s is not row]

    if not other_contents:
        return content[:max_len] if len(content) > max_len else content

    length = min_len
    while length <= max_len:
        candidate = content[:length]
        if candidate and not any(candidate in oc for oc in other_contents):
            return candidate
        length += 4

    logger.warning(
        "[AMBIGUOUS-SNIPPET] %s:%s (%s/%s/%s) - %d자까지도 형제 항목과 구분되지 않아 전체 내용을 사용합니다.",
        row.get("_source_file"), row.get("_line_no"),
        row.get("문서명"), row.get("장"), row.get("조"), max_len,
    )
    return content[:max_len] if len(content) > max_len else content


def strip_code_fence(text: str) -> str:
    return CODE_FENCE_RE.sub("", text.strip()).strip()


def parse_llm_json(raw_text: str) -> list[dict] | None:
    """LLM 응답을 파싱하고 스키마를 검증한다. 위반 시 None을 반환한다 (예외를 던지지 않음)."""
    try:
        data = json.loads(strip_code_fence(raw_text))
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list) or len(data) != 2:
        return None

    seen_types = []
    for item in data:
        if not isinstance(item, dict):
            return None
        query_type = item.get("query_type")
        query_text = item.get("query_text")
        keywords = item.get("keywords")
        if query_type not in ("exact", "paraphrase"):
            return None
        if not isinstance(query_text, str) or not query_text.strip():
            return None
        if not isinstance(keywords, list) or not (2 <= len(keywords) <= 4):
            return None
        if not all(isinstance(k, str) and k.strip() for k in keywords):
            return None
        seen_types.append(query_type)

    if seen_types != ["exact", "paraphrase"]:
        return None

    return data


def call_llm_for_questions(
    llm: ChatOpenAI,
    template: ChatPromptTemplate,
    repair_template: ChatPromptTemplate,
    row: dict,
) -> list[dict] | None:
    messages = template.format_messages(
        문서명=row.get("문서명") or "",
        장=row.get("장") or "",
        조=row.get("조") or "",
        문서내용=row.get("문서내용") or "",
    )
    response = llm.invoke(messages)
    parsed = parse_llm_json(response.content)
    if parsed is not None:
        return parsed

    repair_messages = repair_template.format_messages(previous_response=response.content)
    repair_response = llm.invoke(repair_messages)
    return parse_llm_json(repair_response.content)


def main() -> None:
    parser = argparse.ArgumentParser(description="평가용 질의를 LLM으로 생성한다.")
    parser.add_argument("--input-glob", default="data/processed/*.jsonl")
    parser.add_argument("--output", default="eval/generated_questions.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="처리할 소스 행 개수 제한 (스모크 테스트용)")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--sleep", type=float, default=0.0, help="LLM 호출 사이 대기 시간(초)")
    args = parser.parse_args()

    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

    input_glob = args.input_glob if os.path.isabs(args.input_glob) else str(REPO_ROOT / args.input_glob)
    rows = load_source_rows(input_glob)
    logger.info("대상 행 %d개를 로드했습니다.", len(rows))

    groups = group_siblings(rows)

    target_rows = rows if args.limit is None else rows[: args.limit]

    llm = ChatOpenAI(model=args.model, temperature=0)
    template = ChatPromptTemplate.from_template(QUESTION_TEMPLATE)
    repair_template = ChatPromptTemplate.from_template(REPAIR_TEMPLATE)

    out_records = []
    skipped = []

    for row in target_rows:
        key = (row.get("문서명"), row.get("장"), row.get("조"))
        siblings = groups[key]

        parsed = call_llm_for_questions(llm, template, repair_template, row)
        if parsed is None:
            logger.warning(
                "[SKIP] %s:%s - JSON 파싱 실패 (재시도 포함 2회)",
                row.get("_source_file"), row.get("_line_no"),
            )
            skipped.append((row.get("_source_file"), row.get("_line_no")))
            if args.sleep:
                time.sleep(args.sleep)
            continue

        snippet = compute_unique_snippet(row, siblings)
        assert snippet in (row.get("문서내용") or ""), "snippet은 반드시 원본 문서내용의 부분문자열이어야 합니다."

        for item in parsed:
            query_id = f"{row['_source_file'].removesuffix('.jsonl')}-{row['_line_no']}-{item['query_type']}"
            out_records.append({
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

        if args.sleep:
            time.sleep(args.sleep)

    output_path = REPO_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in out_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(
        "%d개 행 처리, %d개 질문 생성, %d개 행 스킵 -> %s",
        len(target_rows), len(out_records), len(skipped), output_path,
    )
    if skipped:
        logger.info("스킵된 행: %s", skipped)


if __name__ == "__main__":
    main()
