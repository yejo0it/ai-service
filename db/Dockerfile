# PostgreSQL 16 + pgvector (여행 정보 검색 RAG의 벡터 검색, Issue #49)
# 기존 데이터 디렉터리와 호환되도록 같은 postgres:16-alpine 위에 pgvector만 빌드해 얹는다.
FROM postgres:16-alpine

ARG PGVECTOR_VERSION=v0.8.7

# with_llvm=no: JIT 비트코드(clang/llvm 필요)는 만들지 않는다. 빌드 도구는 설치 후 지운다.
RUN apk add --no-cache --virtual .build-deps git build-base \
    && git clone --branch "${PGVECTOR_VERSION}" --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make with_llvm=no OPTFLAGS="" \
    && make install with_llvm=no \
    && cd / \
    && rm -rf /tmp/pgvector \
    && apk del .build-deps
