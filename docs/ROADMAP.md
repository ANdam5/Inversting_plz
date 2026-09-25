# Development Roadmap

각 milestone은 앞 단계의 작은 수직 절편이며, 완료 조건을 만족한 뒤 다음 단계로 진행한다.

## M0 — 최소 기반

- Python package와 pytest 기반을 만들고, OHLCV 수집에 필요한 최소 `Instrument`, UTC timestamp, `Bar`, `MarketDataProvider`만 정의한다.
- 완료 조건: package smoke test와 fake provider의 Bar 조회 테스트가 통과한다.

## M1 — Upbit OHLCV 수집

- Upbit 공개 API의 KRW-BTC candle을 표준 Bar로 변환해 로컬에 저장하고 CLI로 실행하는 첫 vertical slice를 만든다.
- 첫 실행 흐름이 동작한 뒤 pagination, 증분 수집, 오류 처리와 데이터 품질 검사를 추가한다.
- 완료 조건: 실제 공개 데이터를 CLI로 수집할 수 있고 같은 구간을 재수집해도 중복 없이 동일 결과이며 네트워크 없는 테스트도 통과한다.

## M2 — 최초 Rule-based Strategy

- 단순 추세/이동평균 전략 하나와 instrument별 parameter profile을 구현한다.
- position sizing과 기본 위험 제한을 분리한다.
- 완료 조건: BTC와 가상 ETF fixture에 같은 전략, 다른 파라미터를 적용하는 단위 테스트가 통과한다.

## M3 — 결정론적 Backtest

- event replay, simulated clock/broker, fee/slippage, portfolio accounting, 핵심 성과 지표를 구현한다.
- look-ahead 방지와 재현성 검사를 추가한다.
- 완료 조건: 동일 입력/설정에서 주문·체결·지표가 항상 같고 수수료가 반영된다.

## M4 — Paper Trading

- 실시간 polling, paper broker, 상태 저장/복구, 구조화 로그와 알림을 추가한다.
- 완료 조건: 재시작 후 중복 주문 없이 이어지고 장애 시 신규 주문이 안전하게 중단된다.

## M5 — Upbit Live Trading

- 인증 broker adapter, 주문 정규화, idempotency, reconciliation, cancel/retry와 kill switch를 구현한다.
- 소액/단일 instrument로 단계적 운영한다.
- 완료 조건: dry-run과 paper 검증을 거쳐 주문 생명주기와 잔고가 Upbit 상태와 일치한다.

## M6 — 운영 강화 및 다중 Crypto

- 데이터 신선도, 위험 한도, 감사 기록, 백업/복구와 운영 runbook을 강화한다.
- Bithumb adapter의 contract test를 추가한 뒤 필요할 때 연결한다.
- 완료 조건: provider 교체 시 코어/전략 변경 없이 동일 contract suite가 통과한다.

## M7 — 미국 주식/ETF

- 주식 데이터/브로커 어댑터, 거래 캘린더, corporate action, 주식 수수료·세금·결제 규칙을 추가한다.
- 완료 조건: 기존 전략을 ETF fixture와 paper broker에서 재사용하고 휴장·분할·배당 시나리오가 검증된다.

## M8 — 보조 AI 분석

- 뉴스/국면 feature와 매매 사후 분석 파이프라인을 별도 모듈로 추가한다.
- feature provenance, 시점, 모델 버전을 저장하고 장애 시 core trading을 보호한다.
- 완료 조건: AI를 비활성화해도 핵심 거래가 동일하게 동작하며 AI 결과를 재현·감사할 수 있다.
