# syntax=docker/dockerfile:1
# 지식·추론 서비스 (Python 3.12). 멀티스테이지 + temurin JRE(HermiT 용).
# 이미지 변형: INCLUDE_ML=false(기본, 경량 mock 임베딩) / true(local sentence-transformers).
#   docker build -t pkms-knowledge .                          # 경량
#   docker build --build-arg INCLUDE_ML=true -t pkms-knowledge:full .   # full(ML)

ARG INCLUDE_ML=false

# ── temurin JRE(headless) 소스 스테이지 ──
FROM eclipse-temurin:21-jre-jammy AS jre

# ── builder: 의존성 설치(venv) ──
FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1
COPY requirements.txt requirements-ml.txt ./
ARG INCLUDE_ML
RUN python -m venv /venv \
 && /venv/bin/pip install -U pip \
 && /venv/bin/pip install -r requirements.txt \
 && if [ "$INCLUDE_ML" = "true" ]; then /venv/bin/pip install -r requirements-ml.txt; fi

# ── runtime ──
FROM python:3.12-slim AS runtime
# temurin JRE — HermiT(owlready2)가 java 를 찾는다.
COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PATH="/opt/java/openjdk/bin:/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EMBEDDING_PROVIDER=mock
COPY --from=builder /venv /venv
WORKDIR /app
COPY . .
EXPOSE 8000
# healthcheck 는 compose(T-81)에서 정의(reasoner=ok=JRE 증거).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
