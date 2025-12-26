import json

def extract_specific_fields(input_file, output_file):
    """
    JSONL 파일에서 특정 필드만 추출합니다.

    Args:
        input_file: 입력 JSONL 파일 경로
        output_file: 출력 JSONL 파일 경로
    """
    # 추출할 필드 목록
    fields_to_extract = ['product_id', 'tag', '브랜드', '상품명', 'document', '페르소나태그']

    extracted_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        for line in infile:
            # 빈 줄 건너뛰기
            if not line.strip():
                continue

            # JSON 파싱
            data = json.loads(line)

            # 지정된 필드만 추출
            extracted_data = {}
            for field in fields_to_extract:
                if field in data:
                    extracted_data[field] = data[field]

            # JSON 문자열로 변환하여 파일에 쓰기
            json_line = json.dumps(extracted_data, ensure_ascii=False)
            outfile.write(json_line + '\n')

            extracted_count += 1

    print(f"완료! {extracted_count}개의 데이터 처리됨")
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")
    print(f"추출된 필드: {', '.join(fields_to_extract)}")

if __name__ == "__main__":
    # 파일 경로 설정
    input_file = "2512252207_with_product_id.jsonl"
    output_file = "2512252207_extracted_fields.jsonl"

    # 실행
    extract_specific_fields(input_file, output_file)
