"""
data/*.jsonl 원본을 검사하여, 헤더(예: "결혼:", "지원 내용:")나 빈 항목 라벨
(예: "나.")만 담긴 조각 라인을 다음 라인에 결합한 뒤 data/processed/ 에 저장한다.

대상 케이스:
  - good_pharma_welfare_structured.jsonl 제4조(경조사 지원): 결혼:/출산:/사망:/기타:
  - good_pharma_welfare_structured.jsonl 제5조(학자금 지원): 지원 내용:
  - good_pharma_compliance_structured.jsonl 제14조(자사제품설명회): "나." 단독 라인

같은 조(문서명+장+조) 안에서만 헤더를 전파하며, 조가 바뀌면 초기화한다.
원본 파일은 건드리지 않는다.
"""
import glob
import json
import os
import re

SRC_PATTERN = "data/*.jsonl"
DST_DIR = "data/processed"

# "결혼:", "지원 내용:" 처럼 콜론으로 끝나는 짧은 헤더 라인
HEADER_RE = re.compile(r"^.{1,20}[:：]$")
# "나.", "1)" 처럼 내용 없이 항목 번호만 있는 라인
LABEL_ONLY_RE = re.compile(r"^[가-힣a-zA-Z0-9]{1,3}[.)]$")

# 헤더가 몇 개의 뒤따르는 항목까지 적용되는지 (실데이터 검토를 통해 확정된 값).
# 매핑에 없는 헤더가 새로 발견되면 안전하게 1개 항목에만 적용하고 경고를 출력한다.
HEADER_ITEM_COUNTS = {
    "결혼:": 2,      # 본인, 자녀
    "출산:": 1,      # 배우자
    "사망:": 4,      # 배우자/부모, 자녀, 조부모, 형제자매
    "기타:": 1,      # 회갑/고희
    "지원 내용:": 2,  # 중학교/고등학교, 대학교
}


def process_file(path: str) -> tuple[list[dict], int]:
    docs = []
    with open(path, encoding="utf-8") as f:
        raw_lines = [json.loads(line) for line in f if line.strip()]

    header_prefix = None
    header_remaining = 0
    label_prefix = None
    active_key = None
    merged_count = 0

    for doc in raw_lines:
        key = (doc.get("문서명"), doc.get("장"), doc.get("조"))
        content = (doc.get("문서내용") or "").strip()

        # 조가 바뀌면 이전에 남아있던 헤더/라벨 조각은 버린다 (붙일 대상이 없으므로)
        if key != active_key:
            header_prefix = None
            header_remaining = 0
            label_prefix = None
            active_key = None

        if HEADER_RE.match(content):
            count = HEADER_ITEM_COUNTS.get(content)
            if count is None:
                print(f"  [경고] 매핑에 없는 헤더 '{content}' 발견 - 다음 1개 항목에만 적용합니다.")
                count = 1
            header_prefix = content
            header_remaining = count
            active_key = key
            merged_count += 1
            continue

        if LABEL_ONLY_RE.match(content):
            label_prefix = content
            active_key = key
            merged_count += 1
            continue

        prefixes = [p for p in (header_prefix if header_remaining > 0 else None, label_prefix) if p]
        if prefixes and active_key == key:
            doc = dict(doc)
            doc["문서내용"] = " ".join(prefixes + [content])

        if header_remaining > 0:
            header_remaining -= 1
            if header_remaining == 0:
                header_prefix = None
        label_prefix = None

        docs.append(doc)

    return docs, merged_count


def main():
    os.makedirs(DST_DIR, exist_ok=True)
    total_merged = 0

    for src_path in sorted(glob.glob(SRC_PATTERN)):
        docs, merged_count = process_file(src_path)
        dst_path = os.path.join(DST_DIR, os.path.basename(src_path))

        with open(dst_path, "w", encoding="utf-8") as f:
            for doc in docs:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")

        total_merged += merged_count
        print(f"{src_path} -> {dst_path} ({len(docs)}건, 조각 {merged_count}건 병합)")

    print(f"완료. 총 {total_merged}건의 조각 라인을 병합했습니다.")


if __name__ == "__main__":
    main()
