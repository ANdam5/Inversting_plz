# Architecture

## 목표와 접근법

초기 시스템은 **단일 Python 애플리케이션 안의 모듈형 모놀리스**로 만든다. 도메인 모델과 포트를 중심에 두고 Upbit, 파일/DB, 시계 같은 외부 요소를 어댑터로 연결한다. 프로세스 분리나 이벤트 브로커는 실제 운영상 필요가 생길 때만 도입한다.

핵심 흐름은 다음과 같다.

```text
MarketData adapter -> normalized MarketEvent -> Strategy -> Signal/OrderIntent
                                                        -> RiskManager
                                                        -> ExecutionService
                                                        -> Broker port -> Broker adapter
Broker events ------------------------------------------> Portfolio
모든 주요 입력/결정/결과 -------------------------------> Storage

Backtest / Paper / Live = 같은 코어 + 서로 다른 data, clock, broker/execution adapter
```

## 모듈과 책임

| 모듈 | 책임 | 주요 입력/출력 |
|---|---|---|
| `domain` | 공급자 중립 타입과 규칙: Instrument, Bar, Quote, Money, Signal, OrderIntent, Order, Fill, Position, PortfolioSnapshot | 불변에 가까운 도메인 객체 |
| `market_data` | 원천 데이터를 조회/수집하고 중복·시간대·결측을 검증한 뒤 표준 Bar/Quote로 변환 | provider payload -> MarketEvent |
| `strategy` | 시장 데이터와 읽기 전용 포트폴리오 상태로 매매 의도 생성. 주문 제출은 하지 않음 | context -> Signal/OrderIntent |
| `risk` | 포지션 크기, 현금, 노출, 손실 한도, 중복 주문, 거래 가능 여부를 검사·축소·거부 | OrderIntent -> ApprovedOrder/Reject |
| `execution` | 승인 주문을 실행 계획으로 바꾸고 제출, 상태 동기화, 취소, 재시도와 idempotency를 담당 | ApprovedOrder -> Order/Fill events |
| `broker` | 잔고·주문·체결을 위한 포트와 Upbit/paper/향후 주식 브로커 어댑터 | 표준 요청/응답 <-> 외부 API |
| `portfolio` | 현금, 포지션, 평균단가, 실현·미실현 손익과 거래 원장을 체결 기반으로 계산 | Fill/CorporateAction -> snapshot |
| `market_rules` | 세션/캘린더, 통화, tick/lot, 최소 주문, 수수료·세금, 결제, corporate action 정책 | 시장별 convention |
| `storage` | Bar, 주문, 체결, 포트폴리오 스냅샷, 전략 실행 및 의사결정 감사 기록의 repository 포트/구현 | 도메인 객체의 영속화 |
| `backtest` | 과거 이벤트 재생, 결정론적 clock, fill/slippage/fee 모델, 성과 지표 | 동일 Strategy/Risk + simulated broker |
| `application` | 유스케이스와 실행 루프를 조정하고 모드별 의존성을 조립 | collect/backtest/paper/live commands |
| `config` | 환경, instrument profile, 전략 파라미터, 위험 한도 검증. 비밀은 환경/secret provider에서 주입 | config -> typed settings |
| `observability` | 구조화 로그, 지표, 알림, run/order correlation ID | 운영 상태와 감사 추적 |
| `analysis_ai` (향후) | 뉴스/시장 국면/매매 결과를 분석해 버전된 feature 또는 리포트를 생성 | 선택적 feature/report |

## 의존성 규칙

```text
domain <- strategy, risk, portfolio
domain ports <- market_data, broker, storage, clock
위 항목 <- application <- mode-specific composition root
ports <- infrastructure adapters (Upbit, DB, paper, future stock broker)
backtest -> domain ports + strategy + risk + portfolio
```

- `domain`, `strategy`, `risk`, `portfolio`는 외부 SDK와 infrastructure를 import하지 않는다.
- `application`은 포트만 사용하며 실제 어댑터 선택은 composition root에서 한다.
- 어댑터가 공급자 응답과 오류를 표준 도메인 타입/오류로 번역한다.
- Portfolio의 진실은 Signal이 아니라 체결 이벤트다. 재시작 시 저장된 주문·체결과 브로커 상태를 reconciliation한다.
- Strategy 결과는 `(strategy_id, version, parameter_set_id, instrument_id)`와 함께 기록해 재현 가능하게 한다.

## Strategy와 파라미터

Strategy 계약은 대략 `on_event(context) -> list[OrderIntent]`이며 `context`에는 정규화된 데이터, clock, 읽기 전용 portfolio view, 해당 instrument의 파라미터만 포함한다. 파라미터 우선순위는 `기본 전략값 < 자산군 profile < instrument override < 실행별 override`로 정하고, 병합 결과를 실행 시작 시 검증·고정·기록한다. 따라서 같은 전략 구현에 BTC, ETF, 개별주식별 기간, 임계값, 목표 비중과 위험 한도를 다르게 적용할 수 있다.

## 실행 모드의 일관성

| 모드 | Market Data/Clock | Broker/Fill | 공유 부분 |
|---|---|---|---|
| Backtest | 저장된 데이터 + simulated clock | simulated broker, fee/slippage model | Strategy, Risk, Portfolio, domain |
| Paper | 실시간/지연 데이터 + real clock | paper broker | Strategy, Risk, Portfolio, domain |
| Live | 실시간 데이터 + real clock | 실제 broker adapter | Strategy, Risk, Portfolio, domain |

결정론을 위해 코어에서 현재 시간, 난수, 네트워크를 직접 사용하지 않고 각각 주입한다. 백테스트는 미래 데이터 참조를 막고, Live와 동일한 가격·수량 정규화 및 위험 검사 경로를 사용한다.

## Crypto와 Stock 확장

Upbit 초기 구현은 `UpbitMarketDataAdapter`, `UpbitBrokerAdapter`, crypto 24/7 calendar, KRW 수수료/tick/최소주문 규칙으로 제한한다. Bithumb은 같은 포트를 구현하는 별도 어댑터와 규칙 profile을 추가한다.

미국 주식 지원 시 Strategy, Risk 엔진, Execution 오케스트레이션, Portfolio 원장, Storage 포트, Backtest 러너는 재사용한다. 별도로 구현할 부분은 주식 market-data/broker adapter, 거래소 캘린더와 시간대, 주문 유형/세션 규칙, 수수료·세금·결제, 배당·분할 등 corporate action 처리다. `Instrument`는 처음부터 asset class, venue, symbol, quote currency, timezone과 안정적인 내부 ID를 가진다. 공급자 심볼은 adapter mapping으로 관리한다.

AI는 표준화되고 시점이 명확한 feature를 생성하거나 사후 리포트를 만든다. Strategy가 AI feature를 사용할 수는 있지만 결측/지연 시 안전하게 동작해야 하며, Risk와 주문 제출 권한은 AI 계층 밖에 둔다.

