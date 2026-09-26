# Development Roadmap

각 milestone은 앞 단계의 작은 수직 절편이다. 상세 작업과 완료 여부의 기준은 `TODO.md`다.

## M0 — 최소 기반 (완료)

Python package, pytest, 최소 `Instrument`, UTC timestamp, `Bar`, `MarketDataProvider`를 만든다.

## M1 / M1.5 — 시장 데이터와 Backtest dataset (완료)

Upbit 공개 KRW-BTC 일봉을 표준 Bar로 변환해 SQLite에 중복 없이 저장한다. Pagination, 증분 수집, 오류·품질 검사, closed candle 조회와 dataset summary를 제공한다.

## M2 — 최초 Rule-based 판단 흐름 (완료)

SMA crossover Strategy와 Signal, Strategy Profile, OrderIntent, position sizing, BasicRiskManager를 분리해 연결한다. 동일 Strategy를 여러 Instrument와 parameter로 재사용한다.

## M3-A — Minimal deterministic backtest (완료)

Historical closed Bar를 시간순으로 재생한다. Signal은 다음 Bar open에서 sizing·Risk를 거쳐 simulated Fill이 되며, target-state와 look-ahead 방지 규칙을 검증한다.

## M3-B1 — Execution Cost Realism (완료)

Deterministic adverse slippage, fee-aware Fill과 cash accounting, 최소 거래금액 및 zero-cost 회귀를 검증한다.

## M3-B2 — Performance Analysis (완료)

Equity Curve, Total Return, CAGR, MDD와 Passive 10%, BTC 100% Buy & Hold 비교 기준을 제공한다.

## M3-B3 — Configuration Resolution (완료)

Strategy parameter를 `default < instrument/profile < runtime override` 순서로 병합하고 최종 설정을 검증한다.

## M3-B4 — Portfolio Accounting / Trade Metrics (완료)

평균단가, 실현·미실현 손익, flat→position→flat ClosedTrade ledger와 기본 aggregate Trade Metrics를 계산한다.

## M3-C — Backtest Metadata / Reproducibility (완료)

Dataset·Strategy·sizing·Risk·cost·version 실행조건을 immutable metadata로 기록한다. Canonical metadata JSON의 SHA-256 fingerprint와 동일 입력의 결과 재현성을 검증한다.

## M4 — Paper Trading (다음 단계)

Clock, Order/OrderStatus, Broker contract, PaperBroker, Storage repository를 실제 Paper 요구사항에 맞춰 추가한다. Idempotency, 주문·체결 영속화, 재시작 복구, reconciliation, stale data 차단, 로그와 kill switch를 단계적으로 검증한다.

## M5 — Upbit Live Trading

Upbit 인증 Broker adapter, 잔고·주문·체결 변환, 거래 단위와 최소 주문 규칙, 안전한 retry와 시작 시 reconciliation을 구현한다. Dry-run과 명시적 enable을 거쳐 소액·단일 Instrument부터 운영한다.

## M6 이후 — 확장

Bithumb과 미국 주식/ETF adapter, 주식 calendar, 수수료·세금·결제, 배당·분할을 추가한다. AI 분석은 core trading과 분리된 선택적 feature/report 계층으로만 확장한다.
