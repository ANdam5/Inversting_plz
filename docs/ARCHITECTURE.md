# Architecture

이 문서는 현재 구현과 앞으로의 방향을 구분한다. 세부 완료 상태는 `TODO.md`가 기준이다.

## A. Current implementation

시스템은 하나의 Python 프로세스에서 동작하는 모듈형 모놀리스다. 도메인과 Strategy는 Upbit, SQLite, 자격 증명에 의존하지 않고 실행 모드별 application과 adapter가 조립한다.

### 공통 판단 흐름

```text
closed Bars
  → MovingAverageCrossoverStrategy
  → Signal
  → desired target
  → position sizing
  → OrderIntent
  → BasicRiskManager
```

`OrderIntent`는 Risk 검사 전후의 내부 주문 후보다. Risk를 통과해 Broker에 제출된 뒤에는 ID와 상태를 가진 immutable `Order`가 된다. 현재 `OrderStatus`는 `PENDING`, `FILLED`, `CANCELED`, `REJECTED`다.

Strategy parameter 우선순위는 `default < instrument/profile < runtime override`다.

### Backtest 경계

```text
Historical closed Bars
  → Strategy / sizing / Risk
  → next-Bar open deterministic Fill
  → BacktestPortfolio
  → equity, accounting, ClosedTrade, metrics, benchmark
```

- Historical replay와 next-Bar-open 체결은 Backtest 전용이다.
- runner가 Backtest `Fill`을 직접 만들며 Broker와 Clock을 사용하지 않는다.
- fee와 deterministic adverse slippage는 provider-neutral Decimal 함수로 계산한다.
- Portfolio는 cash, quantity, average cost, realized PnL을 유지하고 현재 가격으로 unrealized PnL을 계산한다.
- `ClosedTrade`, Trade Metrics, Equity Curve, Total Return, CAGR, MDD와 benchmark를 제공한다.
- `BacktestRunMetadata`와 canonical JSON SHA-256 fingerprint는 기록된 실행조건을 식별한다. DB 내용 hash나 Git commit 증명은 아니다.

### Paper runtime 경계

```text
Upbit public daily candles
  → closed-Bar filter
  → polling scheduler / new-Bar gate
  → Strategy / sizing / Risk
  → durable decision check
  → Broker.submit() → Order(PENDING)
  → Upbit public current price
  → PaperBroker simulated ExecutionFill
  → cash / position
  → SQLite Order / Fill / cursor persistence
```

| 영역 | 현재 책임 |
|---|---|
| `domain` | `Instrument`, `Bar`, `OrderIntent`, `Order`, `OrderStatus`, UTC·Decimal 규칙 |
| `broker` | Broker contract, in-memory fake, `PaperBroker`, `ExecutionFill`, account projection |
| `clock` | `Clock` protocol, `FixedClock`, UTC `SystemClock` |
| `execution` | Backtest와 Paper가 공유하는 fee와 fixed adverse slippage 계산 |
| `application.paper_cycle` | 한 closed-Bar decision의 Strategy→Risk→submit→execution 흐름 |
| `application.paper_scheduler` | poll cadence, 최신 closed Bar gate, in-memory cursor |
| `storage.paper*` | session config, Order, Fill, decision, cursor의 SQLite 영속화 |
| `application.paper_recovery` | persisted Fill로 cash/position을 재구성하고 runtime 복구 |
| `application.paper_reconciliation` | durable state와 Broker 비교, 불일치/PENDING 시 fail-closed |
| `application.paper_safety` | daily closed-Bar freshness와 manual kill switch 검사 |
| `runtime_identity`, `structured_logging` | restart-safe UUID ID, correlation context, JSON logging |
| `application.paper_runtime`, `cli` | production 조립, `--once`/continuous loop, Ctrl+C 종료 |

Paper는 Upbit 공개 candle과 ticker만 사용한다. 금융 JSON 숫자는 float를 거치지 않고 Decimal로 읽는다. 인증 API나 실제 거래소 주문은 호출하지 않는다.

### Paper DB와 session invariant

M4 baseline은 다음으로 제한한다.

```text
1 SQLite Paper DB
= 1 Paper account
= 1 PaperSessionConfig
= 1 instrument + strategy_id + timeframe
```

Order/Fill과 PaperBroker cash pool은 DB 전체에 대한 하나의 account다. 다른 Instrument, Strategy 또는 timeframe을 운용하려면 별도 Paper DB를 사용한다. multi-strategy shared-account portfolio runtime은 지원하지 않는다.

`strategy_id`는 표시 이름이 아니라 durable strategy semantics identity다. Strategy 계산 의미가 바뀌면 새로운 `strategy_id` 또는 새로운 Paper DB를 사용해야 한다. 별도 version framework는 없다.

### Paper startup과 safety

```text
SQLite DB
  → singleton config validation
  → Order / Fill account recovery
  → cursor recovery
  → reconciliation
  → kill switch + stale-data guard
  → scheduler
```

- 기본값은 trading disabled이며 `--enable-trading`이 있어야 simulated execution을 허용한다.
- unresolved `PENDING`, foreign session state, account mismatch는 자동 수정하지 않고 fail-closed한다.
- daily Bar timestamp는 candle open이며 freshness는 다음 closed candle의 expected completion과 허용 delay로 판단한다.
- ManualKillSwitch는 in-memory 객체다. CLI에는 실행 중 외부에서 토글하는 remote control이 없고 장시간 실행의 즉시 정지는 Ctrl+C다.
- durable decision idempotency와 pending-order protection은 같은 decision의 중복 submit을 막는다.

## B. Target architecture / future direction

M5에서는 Upbit authenticated Broker, 실제 잔고·주문·체결 상태, partial fill, 거래 단위·최소 주문 규칙, 외부 Broker reconciliation과 submit 불확실성 처리를 추가한다. 실제 비용 정책이나 Paper/Live 정책 교체 필요성이 확인될 때만 fee/slippage model port를 추출한다.

향후 multi-account, shared multi-strategy portfolio, 다른 거래소와 주식 지원은 별도 milestone에서 다룬다. 현재 `Instrument`는 `venue`와 `symbol`만 가지며 미래 필드를 미리 추가하지 않는다.

## 의존성 원칙

- Strategy는 market adapter, Broker, SQLite를 직접 호출하지 않는다.
- Position sizing과 Risk는 Backtest와 Paper에서 재사용한다.
- 상태 변화는 Signal이 아니라 Fill을 기준으로 계산한다.
- 실제 외부 주문은 항상 Risk를 통과해야 한다.
- storage와 provider 세부 구현은 application/domain 경계 밖에 둔다.
- 범용 framework나 분산 구조는 실제 필요 전에 만들지 않는다.
- AI는 선택적 분석/리포트 계층이며 Risk와 주문 권한을 우회하지 않는다.
