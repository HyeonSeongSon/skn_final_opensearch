import json
from collections import OrderedDict

def add_product_id_and_reorder(input_file, output_file, start_id=20251200001):
    """
    JSONL 파일에 product_id를 추가하고 키 순서를 재정렬합니다.

    Args:
        input_file: 입력 JSONL 파일 경로
        output_file: 출력 JSONL 파일 경로
        start_id: 시작 product_id (기본값: 20251200001)
    """

    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:

        current_id = start_id

        for line in infile:
            # 빈 줄 건너뛰기
            if not line.strip():
                continue

            # JSON 파싱
            data = json.loads(line)

            # 새로운 OrderedDict 생성 (키 순서 보장)
            ordered_data = OrderedDict()

            # 1. product_id (맨 앞)
            ordered_data['product_id'] = str(current_id)

            # 2. tag (두 번째)
            if 'tag' in data:
                ordered_data['tag'] = data['tag']

            # 3. 나머지 키들 (url, 브랜드, 상품명 등)
            # documenturl, 상품이미지, 상품상세_이미지는 제외
            exclude_keys = {'tag', 'url', '상품이미지', '상품상세_이미지'}
            for key in data:
                if key not in exclude_keys and key not in ordered_data:
                    ordered_data[key] = data[key]

            # 4. 마지막 3개: url(documenturl로 변경), 상품이미지, 상품상세_이미지
            if 'url' in data:
                ordered_data['documenturl'] = data['url']

            if '상품이미지' in data:
                ordered_data['상품이미지'] = data['상품이미지']

            if '상품상세_이미지' in data:
                ordered_data['상품상세_이미지'] = data['상품상세_이미지']

            # JSON 문자열로 변환하여 파일에 쓰기
            json_line = json.dumps(ordered_data, ensure_ascii=False)
            outfile.write(json_line + '\n')

            # product_id 증가
            current_id += 1

    print(f"완료! {current_id - start_id}개의 데이터 처리됨")
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")
    print(f"product_id 범위: {start_id} ~ {current_id - 1}")

if __name__ == "__main__":
    # 파일 경로 설정
    input_file = "2512252207.jsonl"
    output_file = "2512252207_with_product_id.jsonl"

    # 실행
    add_product_id_and_reorder(input_file, output_file)
