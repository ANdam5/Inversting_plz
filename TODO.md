# TODO

위에서 아래 순서가 기본이며, 각 항목은 하나의 독립 테스트 대상을 갖는다. `[ ]` 한 항목은 가능한 한 하나의 작은 PR/commit 단위로 유지한다.

## M0 — 최소 기반

- [x] Python package 기본 디렉터리를 만들고 package import smoke test를 추가한다.
- [x] pytest 설정과 항상 통과하는 smoke test를 추가한다.
- [x] 최소 `Instrument` 모델을 정의하고 KRW-BTC 식별값 생성을 테스트한다.
- [x] timestamp는 timezone-aware UTC만 허용하는 규칙을 정의하고 naive datetime 거부를 테스트한다.
- [x] 최소 `Bar` 모델을 정의하고 OHLCV 불변조건을 테스트한다.
- [x] `MarketDataProvider` 최소 protocol을 정의하고 fake provider로 Bar 조회를 테스트한다.

## M1 — Upbit OHLCV

- [x] 저장된 Upbit candle fixture 하나를 표준 `Bar`로 변환하고 UTC 값을 테스트한다.
- [x] Upbit 공개 API client로 KRW-BTC candle 한 페이지를 요청하고 HTTP 요청 구성을 테스트한다.
- [x] `UpbitMarketDataProvider`가 공개 API 응답을 시간순 `Bar` 목록으로 반환하는지 fixture로 테스트한다.
- [x] 로컬 Bar 저장 형식을 정하고 저장 후 조회 round-trip을 테스트한다.
- [x] KRW-BTC Bar 목록을 로컬에 저장하는 수집 use case를 구현하고 fake provider로 테스트한다.
- [x] `(instrument, timeframe, timestamp)` 기준 중복 방지를 구현하고 같은 Bar 재저장을 테스트한다.
- [x] OHLCV 수집 CLI를 추가하고 fake provider로 API→변환→저장 흐름을 end-to-end 테스트한다.
- [x] CLI에서 실제 Upbit KRW-BTC 공개 데이터를 한 번 수집하는 opt-in integration test를 추가한다.
- [x] candle pagination을 구현하고 페이지 경계 누락·중복을 테스트한다.
- [x] 저장된 최신 timestamp 이후만 수집하고 중단 후 재실행을 테스트한다.
- [x] Upbit API 오류를 표준 provider 오류로 변환하고 timeout·429 응답을 테스트한다.
- [x] 중복·역순·비정상 OHLCV 데이터 검사를 구현하고 각각을 테스트한다.
- [x] 예상 구간의 결측 탐지를 구현하고 24/7 규칙 fixture로 테스트한다.

## M1.5 — Backtest용 데이터셋 준비

- [x] 고정된 현재 시각으로 24/7 일봉의 closed 상태를 판정하고 UTC 경계를 테스트한다.
- [x] SQLite에서 완료된 Bar만 조회하고 진행 중 Bar 제외를 테스트한다.
- [x] 기존 pagination CLI로 KRW-BTC 일봉 약 5년치를 수집한다.
- [x] 데이터셋 row/closed/range/duplicate/gap summary를 구현하고 테스트한다.
- [x] 데이터셋 summary CLI를 추가하고 출력 결과를 테스트한다.

## M2-A — Strategy / Signal

- [x] Strategy protocol을 정의하고 Broker·Upbit·SQLite에 의존하지 않는 구현을 테스트한다.
- [x] `Signal` 최소 모델과 bullish/bearish/neutral 유형을 정의하고 테스트한다.
- [x] Decimal 종가 기반 Simple Moving Average를 구현하고 경계 길이·결측 입력을 테스트한다.
- [x] 이동평균 교차 Strategy가 실제 bullish/bearish 교차와 neutral을 구분하는지 테스트한다.
- [x] closed Bar만 조회해 20/60 Strategy Signal을 출력하는 read-only CLI를 구현하고 테스트한다.
- [x] 동일 Strategy의 다중 Instrument 및 parameter 재사용성을 테스트한다.

## M2-B1 — Instrument Strategy Profile

- [x] Instrument, strategy ID, 검증된 MA parameter를 묶는 immutable Profile을 정의한다.
- [x] Profile 생성 시 fast/slow window 규칙을 검증한다.
- [x] Profile에서 현재 MA Crossover Strategy를 생성하는 최소 경로를 구현한다.
- [x] KRW-BTC와 KRW-ETH Profile이 같은 Strategy에 다른 parameter를 전달하는지 테스트한다.

## M2-B2-A — OrderIntent / Decimal foundation

- [x] `OrderIntent` 최소 모델을 정의하고 serialization round-trip을 테스트한다.
- [x] 금융 가격·수량·금액은 Decimal을 사용하고 float 입력을 거부하는 기초 정책을 정의한다.

## M2-B2-B — Position sizing

- [x] 목표 비중을 OrderIntent 수량으로 변환하고 Decimal 내림을 테스트한다.
- [x] BTC와 ETF profile에 같은 Strategy와 sizing 로직을 적용하고 서로 다른 수량을 테스트한다.

## M2-C1 — Basic Risk Manager

- [x] Risk Manager protocol과 APPROVED/ADJUSTED/REJECTED 결과를 정의한다.
- [x] 최대 단일 종목 비중 규칙을 구현하고 축소/거부를 테스트한다.
- [x] 최소 현금 보유 규칙을 구현하고 주문 축소를 테스트한다.
- [x] 최대 단일 주문 금액 규칙을 구현하고 경계값을 테스트한다.

> Note: 동일 Intent 재처리와 중복 미체결 주문 차단은 Order/Broker 상태가 필요한 운영 위험이므로 M4 Paper Trading으로 이동했다.

## M3-A — Minimal deterministic backtest

- [x] 최소 `Fill` 모델을 정의하고 Decimal·UTC 불변조건을 테스트한다.
- [x] 단일 종목 가상 현금과 보유 수량을 Fill로 갱신하고 초과 매도를 차단한다.
- [x] 과거 closed Bar를 시간순으로 replay하고 같은 입력의 결과가 재현되는지 테스트한다.
- [x] Signal을 다음 Bar open에서 sizing·Risk·Fill하여 look-ahead를 방지한다.
- [x] 기존 Position sizing과 `BasicRiskManager`를 Backtest에서 재사용한다.
- [x] backtest CLI를 추가하고 작은 SQLite fixture로 end-to-end 테스트한다.
- [x] optional CLI fill detail output을 추가하고 출력 순서·금액을 테스트한다.
- [x] Strategy Signal이 desired target state를 변경하도록 처리한다.
- [x] Risk ADJUSTED 시 다음 Bar에서 남은 target adjustment를 이어서 수행한다.
- [x] target 완료 후 neutral Bar에서 continuous rebalance하지 않음을 테스트한다.
- [x] target adjustment 중 반대 방향 미세조정 주문을 방지한다.
- [x] 최소 주문 금액으로 초소액 BUY target adjustment를 종료한다.

## M3-B1 — Execution Cost Realism

- [x] deterministic adverse slippage를 구현하고 BUY/SELL 방향을 테스트한다.
- [x] fee-aware Fill과 Portfolio 현금 회계를 구현한다.
- [x] slippage-adjusted 가격으로 Risk를 평가하고 fee-aware affordability를 적용한다.
- [x] 모든 Fill fee의 합계인 total fee reporting을 추가한다.
- [x] CLI에서 fee/slippage를 Decimal 설정으로 전달한다.
- [x] fee=0, slippage=0에서 기존 M3-A 결과를 회귀 검증한다.
- [x] 비용 가정이 적용된 historical dataset 실행을 검증한다.

## M3-B2 — Performance Analysis

- [x] closed Bar마다 close 기준 Equity Curve를 기록한다.
- [x] Total Return을 Decimal 비율로 계산한다.
- [x] Maximum Drawdown을 이전 최고점 대비 음수 비율로 계산한다.
- [x] 실제 timestamp 기간과 365.25일 기준으로 CAGR을 계산한다.
- [x] 초기 10% BTC와 90% 현금을 유지하는 Passive benchmark를 계산한다.
- [x] 첫 open에서 전액 매수하는 BTC 100% Buy & Hold benchmark를 계산한다.

## M3-B3 — Configuration Resolution

- [x] instrument/profile/runtime parameter 병합 우선순위를 구현하고 검증 실패를 테스트한다.

> 우선순위: default < instrument/profile < runtime override

## M3-B4 — Portfolio Accounting / Trade Metrics

- [x] 평균단가와 실현 손익 계산을 구현하고 부분 매도를 테스트한다.
- [x] 미실현 손익 평가를 구현하고 quote currency 일관성을 테스트한다.
- [x] 거래별 성과 지표를 고정 원장으로 테스트한다.

## M3-C — Backtest Metadata / Reproducibility

- [x] backtest run metadata에 코드/전략/파라미터/데이터 버전을 기록하고 round-trip을 테스트한다.
- [x] 동일 dataset과 동일 configuration에서 동일 fingerprint와 backtest 결과가 생성되는지 테스트한다.

## M4 — Paper Trading

- [x] Clock protocol과 fixed/system clock을 정의하고 UTC 시간 결정론을 테스트한다.
- [x] polling scheduler를 구현하고 fake clock으로 주기와 in-memory 중복 Bar 차단을 테스트한다.
- [x] Paper Order·Fill·cursor repository protocol과 SQLite 구현의 재개방 round-trip을 테스트한다.
- [x] `Order`, `OrderStatus` 모델을 정의하고 유효한 상태 전이를 테스트한다.
- [x] Broker protocol을 정의하고 메모리 fake로 주문 contract를 테스트한다.
- [x] paper broker의 명시적 Order/Fill 생명주기를 구현하고 Broker 주문 contract를 통과시킨다.
- [x] paper broker의 cash/position 및 비용 반영 실행을 구현하고 테스트한다.
- [x] closed Bar부터 PaperBroker 실행까지 단일 paper cycle을 연결하고 테스트한다.
- [x] closed Bar decision identity를 영속화하고 재처리 시 동일 identity를 테스트한다.
- [x] 동일 decision 재처리 및 scope별 중복 미체결 주문 제출 차단을 테스트한다.
- [x] Paper Order·Fill·cursor SQLite persistence foundation을 구현한다.
- [x] 영속 Order·Fill·cursor로 Paper account와 scheduler를 재시작 복구한다.
- [x] 저장 상태와 broker 상태 reconciliation을 구현하고 불일치 시나리오를 테스트한다.
- [x] stale market data 차단 규칙을 구현하고 신규 주문 거부를 테스트한다.
- [x] restart-safe Paper runtime ID와 구조화 로그에 cycle/order correlation ID를 추가하고 로그 capture로 테스트한다.
- [x] kill switch를 구현하고 활성화 중 주문 미제출을 테스트한다.
- [x] durable Paper session configuration을 저장하고 restart 설정 불일치를 차단한다.
- [x] paper trading CLI를 추가하고 fake market feed로 end-to-end 테스트한다.
- [x] Upbit 금융 JSON의 Decimal 정밀도와 실패 poll cadence를 최종 회귀 테스트한다.
- [x] Paper DB를 단일 account/session으로 제한하고 foreign scope 상태를 fail-closed한다.

## M5 — Upbit Live

- [ ] Upbit Live 비용 정책을 확인하고 실제 필요 시 fee model port와 Upbit fee fixture를 추가한다.
- [ ] Paper/Live 비용 정책의 교체 필요성이 확인되면 slippage model port를 추출한다.
- [x] Upbit 인증 서명 생성을 공식 fixture로 테스트한다.
- [x] Upbit 잔고 응답을 표준 balance로 변환하고 fixture로 테스트한다.
- [x] Upbit 주문 응답을 snapshot으로 파싱하고 정확한 원 수량이 있는 주문만 표준 `Order`로 변환하며 시장가 매수는 명시적으로 거부한다.
- [x] Upbit order snapshot의 trade/progress 추적과 부분체결 polling core를 fake source로 테스트한다.
- [x] authenticated Upbit individual-order HTTP 조회 source를 existing tracker에 연결하고 fake HTTP로 검증한다.
- [x] REST trades와 cumulative `paid_fee`를 분리 보존하는 Live accounting update 정책을 구현하고 테스트한다.
- [x] Live execution ledger SQLite persistence와 restart idempotency를 구현한다.
- [ ] Upbit tick size 반올림을 구현하고 가격 구간 경계를 테스트한다.
- [ ] Upbit 최소 주문 금액 검사를 구현하고 경계값을 테스트한다.
- [ ] 재시도 정책을 멱등 요청에만 적용하고 timeout/429를 테스트한다.
- [ ] 시작 시 reconciliation을 구현하고 미확인 주문이 있으면 fail-closed 되는지 테스트한다.
- [ ] dry-run adapter를 구현하고 외부 주문 호출이 없음을 테스트한다.
- [ ] Live 실행 전 명시적 enable 설정을 검사하고 기본 비활성을 테스트한다.

## M6 이후 — 확장

- [ ] Bithumb market-data adapter를 구현하고 공통 contract suite를 통과시킨다.
- [ ] Bithumb broker adapter를 구현하고 공통 contract suite를 통과시킨다.
- [ ] 미국 주식 거래 calendar adapter를 구현하고 휴장/조기폐장을 테스트한다.
- [ ] 미국 주식 market-data adapter를 구현하고 공통 contract suite를 통과시킨다.
- [ ] 미국 주식 broker adapter를 구현하고 공통 contract suite를 통과시킨다.
- [ ] 주식 분할 이벤트를 Portfolio에 적용하고 수량/평균단가 보존을 테스트한다.
- [ ] 현금 배당 이벤트를 Portfolio에 적용하고 ex-date/pay-date 시나리오를 테스트한다.
- [ ] 주식 수수료·세금·결제 규칙을 구현하고 시장별 fixture로 테스트한다.
- [ ] AI feature schema에 event time/model version/source를 포함하고 validation을 테스트한다.
- [ ] AI feature timeout/결측 시 Strategy fallback을 테스트한다.
- [ ] AI 분석 비활성 상태에서 core trading 회귀 테스트를 실행한다.
