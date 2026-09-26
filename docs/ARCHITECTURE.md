# Architecture

이 문서는 현재 존재하는 구현과 앞으로 만들 목표 구조를 구분한다. 현재 코드의 정확한 진행 상태는 `TODO.md`가 기준이다.

## A. Current implementation

현재 시스템은 하나의 Python 프로세스 안에서 동작하는 모듈형 모놀리스다. 구현된 핵심 흐름은 다음과 같다.

```text
Upbit public API
  → UpbitMarketDataProvider
  → normalized Bar
  → validation
  → SQLiteBarStore

Historical closed Bars
  → MovingAverageCrossoverStrategy
  → Signal
  → desired target state
  → next Bar open
  → position sizing
  → OrderIntent
  → BasicRiskManager
  → deterministic simulated Fill
  → BacktestPortfolio
  → equity, accounting, ClosedTrade, performance analysis
```

### 현재 모델과 모듈

| 모듈 | 현재 책임 |
|---|---|
| `domain` | `Instrument(venue, symbol)`, `Bar`, `OrderIntent`, UTC·Decimal 규칙 |
| `market_data` | provider 계약, candle 완료 판정, Bar 정렬·중복·gap 검증, dataset summary |
| `adapters` | Upbit 공개 candle HTTP 요청과 응답→Bar 변환 |
| `storage` | SQLite Bar 저장·조회·중복 방지·closed Bar 조회 |
| `indicators` | Decimal 종가 기반 SMA 계산 |
| `strategy` | closed Bar sequence를 받아 bullish/bearish/neutral `Signal` 생성, Strategy Profile과 parameter resolution |
| `application` | 수집 조정과 목표 비중→OrderIntent position sizing |
| `risk` | 주문금액·종목비중·현금 한도로 OrderIntent 승인·축소·거부 |
| `backtest` | historical replay, next-bar execution, fee/slippage, 단일 종목 Portfolio 회계, 지표·benchmark·metadata·fingerprint |

현재 Strategy parameter 우선순위는 다음과 같다.

```text
default < instrument/profile < runtime override
```

병합된 최종 fast/slow parameter는 기존 validation을 통과해야 한다. Strategy 내부에는 symbol별 분기가 없다.

### 현재 Backtest의 경계

- Strategy는 `closed Bars → Signal`만 담당한다.
- bullish/bearish Signal은 runner의 desired target state를 바꾼다.
- Position sizing과 `BasicRiskManager`는 기존 공통 구현을 재사용한다.
- Signal은 같은 Bar가 아니라 다음 Bar open에서 실행되어 look-ahead를 막는다.
- runner가 deterministic historical replay 과정에서 simulated `Fill`을 직접 생성한다.
- 현재 Backtest에는 Broker 또는 Clock abstraction이 없다.
- `BacktestPortfolio`는 cash, position quantity, average cost, realized PnL을 유지하며 현재 가격으로 unrealized PnL을 계산한다.
- `ClosedTrade`는 flat→position→flat의 완료된 lifecycle이며 마지막 open position은 포함하지 않는다.
- 실행 조건은 `BacktestRunMetadata`에 기록되고 canonical metadata JSON의 SHA-256으로 configuration fingerprint를 만든다.

Fingerprint의 `dataset_version`과 `code_version`은 호출자가 제공하는 label이다. 따라서 현재 fingerprint는 기록된 metadata 조건을 식별하지만 SQLite 내용 hash나 Git commit 증명은 아니다.

## B. Target architecture / future direction

M4 이후에도 모듈형 모놀리스와 현재 코어 재사용 원칙을 유지한다. 실제 필요가 생길 때 다음 경계를 추가한다.

| 향후 모듈/경계 | 목표 책임 |
|---|---|
| Order / OrderStatus | 제출 이후 주문 lifecycle의 표준 상태 |
| Broker port | 잔고·주문·체결을 위한 provider-neutral 계약 |
| PaperBroker | 외부 실주문 없이 Broker 계약을 검증하는 Paper 구현 |
| Clock | Paper/Live polling과 시간 결정을 명시적으로 주입 |
| Storage repository | Bar 이외 주문·체결·상태의 영속화와 재시작 복구 |
| Execution | 제출, idempotency, 상태 동기화, 재시도 정책 조정 |
| Reconciliation | 저장 상태와 Broker 상태의 불일치 탐지·복구 |
| Observability | 구조화 로그, correlation ID, 운영 알림과 kill switch |

이 항목들은 현재 구현된 컴포넌트가 아니라 M4 Paper Trading부터 추가할 목표다. 세부 계약은 실제 Paper 요구사항이 생길 때 정의한다.

## 의존성 원칙

- 도메인과 Strategy는 Upbit SDK, SQLite, 자격 증명, 네트워크를 직접 호출하지 않는다.
- 공급자 응답과 오류는 adapter가 표준 모델과 오류로 변환한다.
- Strategy, position sizing, Risk는 Backtest/Paper/Live에서 가능한 한 재사용한다.
- Portfolio의 상태 변화는 Signal이 아니라 Fill을 기준으로 계산한다.
- 외부 주문은 항상 Risk Manager를 통과해야 한다.
- 범용 framework나 분산 구조는 실제 필요가 생기기 전에 도입하지 않는다.
- AI는 향후 선택적 분석 입력이나 리포트로만 추가하며 Risk와 주문 권한을 우회하지 않는다.

## Crypto와 Stock 확장 방향

Upbit 외 거래소와 주식 지원에서도 현재 `Instrument`, `Bar`, Strategy, sizing, Risk 및 분석 로직을 가능한 범위에서 재사용한다. 별도로 필요한 것은 provider/broker adapter와 시장별 calendar, 거래 단위, 수수료·세금·결제, 배당·분할 규칙이다.

현재 `Instrument` 필드는 `venue`와 `symbol`뿐이다. asset class, quote currency, timezone, 내부 ID 같은 추가 정보는 실제 주식·다중시장 요구가 생겼을 때 호환성을 검토하며 확장한다.
