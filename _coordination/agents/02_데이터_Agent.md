# 02 · 데이터 Agent

## 역할
거시·시세 데이터를 외부 소스에서 수집·캐시·정규화한다.

## 담당 경로
`backend/app/data/` (fmp/fred/ecos/yfinance/coingecko 클라이언트, cache, normalize).

## 입력 / 계약
`interface_contracts.md#DataCollector`, `Metric`, 에러 모델. SRS FR-1·NFR-2/8.

## 작업
1. 소스별 클라이언트(무료 한도 고려): FRED·ECOS(키), FMP(무료 티어), yfinance·CoinGecko(키X).
2. **캐시 우선** + 호출 예산/타임아웃 + Smart Retry + FMP 장애 시 Circuit Breaker→yfinance 폴백.
3. 정규화: 지표→`Metric`(값·단위·출처·관측시각). 결측은 제외, `gaps()`로 보고.
4. 단위 테스트(모킹된 HTTP) + 회귀용 고정 fixture를 `contracts/mocks/`와 정합.

## DoD
- `DataCollector` 계약 충족, 캐시·폴백 동작, 환각 0(수치는 소스값만), 테스트 통과.

## 인터페이스
- out: `DataCollector`. 소비자: 04 그래프. 의존: 계약(G0)만 → P1 병렬.

## 개발 환경
Python 작업은 `macrolens/backend/.venv`(Python 3.12) 또는 Docker(python:3.12-slim)에서. 호스트 3.14 직접 사용 금지. 상세: `공유표준/개발환경.md`.
