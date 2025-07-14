# 베이스 이미지 버전을 인자로 받도록 설정
ARG OPENSEARCH_VERSION=3.1.0
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}

# 파일 권한 문제를 해결하기 위해 root 사용자로 전환
USER root

# 플러그인 목록 파일을 컨테이너에 복사
COPY plugins.txt /tmp/plugins.txt

# Windows의 CRLF 줄바꿈 문자를 Linux의 LF로 변환하여 호환성 문제 해결
RUN sed -i 's/\r$//' /tmp/plugins.txt

# 각 플러그인을 개별적으로 설치하여 오류 추적을 용이하게 함
RUN while IFS= read -r plugin; do \
        if [ -n "$plugin" ] && [ "${plugin:0:1}" != "#" ]; then \
            echo "Installing plugin: $plugin"; \
            /usr/share/opensearch/bin/opensearch-plugin install --batch "$plugin" || exit 1; \
        fi; \
    done < /tmp/plugins.txt

# 설치된 플러그인과 데이터 디렉토리의 소유권을 opensearch 사용자로 변경
RUN chown -R opensearch:opensearch /usr/share/opensearch/plugins

# 보안을 위해 다시 opensearch 사용자로 전환
USER opensearch