# Development Roadmap

각 milestone은 앞 단계의 작은 수직 절편이다. 상세 작업과 완료 여부는 `TODO.md`가 기준이다.

## M0 — 최소 기반 (완료)

Python package, pytest, 최소 `Instrument`, UTC timestamp, `Bar`, `MarketDataProvider`를 만든다.

## M1 / M1.5 — 시장 데이터와 Backtest dataset (완료)

Upbit 공개 일봉을 표준 Bar로 변환해 SQLite에 저장한다. Pagination, 증분 수집, 오류·품질 검사, closed candle 조회와 dataset summary를 제공한다.

## M2 — Rule-based 판단 흐름 (완료)

SMA crossover Strategy와 Signal, Strategy Profile, OrderIntent, position sizing, BasicRiskManager를 분리해 연결한다.

## M3 — Deterministic Backtest / Analysis / Reproducibility (완료)

Historical next-Bar execution, 비용, Portfolio 회계, Equity/Trade Metrics, benchmark를 구현한다. 실행조건 metadata와 deterministic configuration fingerprint로 동일 입력의 재현성을 검증한다.

## M4 — Paper Trading (완료)

Order lifecycle, Broker contract, PaperBroker account execution, Clock와 polling scheduler를 구현한다. SQLite에 config·decision·Order·Fill·cursor를 영속화하고 idempotency, restart recovery, reconciliation, stale-data guard, kill switch, structured logging과 Paper CLI를 연결한다.

M4 baseline은 `1 Paper DB = 1 account = 1 session config`인 단일 Instrument session이다. Upbit 공개 데이터와 simulated Fill만 사용하며 실제 거래소 주문은 발생하지 않는다. Paper 비용은 Backtest와 같은 Decimal 계산을 재사용하고, 구현체가 하나뿐인 현재는 fee/slippage model port를 두지 않는다.

## M5 — Upbit Live Trading (다음 단계)

Upbit authenticated Broker, 실제 잔고·주문·체결 변환, partial fill/status polling, 거래 단위와 최소 주문 규칙, 안전한 retry 및 외부 exchange reconciliation을 구현한다. 실제 Upbit 비용 정책과 Paper/Live 정책 교체 요구가 확인될 때만 fee/slippage model port를 추출한다. Dry-run과 명시적 enable을 거쳐 소액·단일 Instrument부터 운영한다.

## M6 이후 — 확장

Bithumb과 미국 주식/ETF adapter, 주식 calendar, 수수료·세금·결제, 배당·분할을 추가한다. AI 분석은 core trading과 분리된 선택적 feature/report 계층으로만 확장한다.
