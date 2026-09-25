# 초보자를 위한 프로젝트 안내서

이 문서는 Python을 처음 접하는 사용자가 현재 프로젝트를 실행하고, 저장된 데이터를 확인하고, 테스트의 의미를 이해할 수 있도록 설명한다. 현재 저장소에 실제로 구현된 기능만 다룬다.

## 1. 이 프로젝트가 지금 무엇을 하는 프로그램인지

현재 프로그램은 Upbit에서 원화로 거래되는 비트코인(`KRW-BTC`)의 일봉 데이터를 가져와 검사하고 SQLite 파일에 저장한다.

```text
Upbit
  → 비트코인 일봉 수집
  → 공통 Bar 형태로 변환
  → 순서·중복·누락·가격 값 검증
  → SQLite 저장
  → 완료된 일봉 조회와 데이터셋 요약
```

여기서 **일봉**은 하루 동안의 시가, 고가, 저가, 종가, 거래량을 한 묶음으로 표현한 데이터다.

현재는 수집한 데이터로 20일·60일 이동평균 교차 Signal을 계산하고, 과거 closed Bar 위에서 최소 Backtest를 실행할 수 있다. 하지만 자동매매 프로그램 전체는 아니며 실제 거래소 주문은 하지 않는다.

## 2. 현재 할 수 있는 것 / 아직 할 수 없는 것

### 현재 가능한 것

- Upbit 공개 API에서 `KRW-BTC` 일봉 가져오기
- pagination으로 여러 페이지의 과거 일봉 가져오기
- 공통 `Bar` 형태로 변환하기
- SQLite DB 파일에 저장하기
- 같은 Bar의 중복 저장 방지하기
- DB의 최신 timestamp 이후 데이터만 증분 수집하기
- timeout, HTTP 429, provider 오류를 구분하기
- 잘못된 OHLCV, 중복, 순서 오류, 일봉 누락 검사하기
- 현재 진행 중인 일봉과 완료된 일봉 구분하기
- 완료된 일봉만 SQLite에서 조회하기
- summary 명령으로 데이터셋 상태 확인하기
- 종가의 Simple Moving Average(SMA) 계산하기
- 20일·60일 이동평균의 실제 교차 시점에 Strategy Signal 만들기
- signal 명령으로 최신 closed Bar 기준 판단 확인하기
- closed Bar를 시간순으로 재생하는 결정론적 Backtest 실행하기
- 다음 Bar open에서 가상 체결하고 단일 종목 가상 현금·수량 확인하기

### 현재 불가능한 것

- 수수료·slippage를 반영한 현실적인 성과 분석
- 평균단가, 실현손익, MDD 같은 상세 지표 계산
- 실제 거래소 Order 생성 또는 제출
- Paper Trading
- 실제 투자
- 실제 계좌 Portfolio 관리
- AI 또는 뉴스 분석

## 3. 프로젝트 폴더 구조

아래는 현재 실행과 이해에 중요한 실제 파일들이다.

```text
Inversting_plz/
├─ pyproject.toml                  # 패키지 정보, Python 버전, pytest 설정
├─ AGENTS.md                       # 이 저장소에서 지켜야 할 개발 원칙
├─ TODO.md                         # 완료한 단계와 앞으로 구현할 작업
├─ data/
│  ├─ market.db                    # 초기 수집·중복 검증에 사용한 SQLite 데이터
│  └─ krw_btc_5y.db                # 약 5년치 KRW-BTC 일봉 데이터셋
├─ docs/
│  ├─ ARCHITECTURE.md              # 장기 시스템 구조 설명
│  ├─ ROADMAP.md                   # 개발 단계 계획
│  └─ BEGINNER_GUIDE.md            # 지금 읽고 있는 초보자용 안내서
├─ src/investing_plz/
│  ├─ __init__.py                  # investing_plz를 Python 패키지로 표시
│  ├─ __main__.py                  # python -m investing_plz 실행 시작점
│  ├─ cli.py                       # collect/summary/signal/backtest 명령 처리
│  ├─ indicators/
│  │  ├─ __init__.py              # indicator 함수 공개
│  │  └─ moving_average.py        # Decimal 종가의 Simple Moving Average
│  ├─ adapters/
│  │  ├─ __init__.py              # adapters 패키지 표시
│  │  └─ upbit.py                 # Upbit HTTP 요청과 응답→Bar 변환
│  ├─ application/
│  │  ├─ __init__.py              # application 패키지 표시
│  │  ├─ collect.py               # 데이터 수집 전체 순서를 조정
│  │  └─ position_sizing.py       # 목표 비중을 OrderIntent 수량으로 변환
│  ├─ backtest/
│  │  ├─ __init__.py              # Backtest 공개 이름 모음
│  │  ├─ models.py                # 설정, Fill, 가상 Portfolio, 결과 모델
│  │  └─ runner.py                # closed Bar를 순서대로 재생하는 실행기
│  ├─ domain/
│  │  ├─ __init__.py              # 주요 domain 모델 공개
│  │  ├─ instrument.py            # 거래소와 종목을 나타내는 Instrument
│  │  ├─ bar.py                   # 공통 OHLCV Bar와 기본 불변조건
│  │  ├─ decimal.py               # 금융 값의 Decimal 타입 검사
│  │  ├─ order_intent.py          # 실제 주문 전의 BUY/SELL 주문 후보
│  │  └─ time.py                  # timezone-aware UTC 검사
│  ├─ market_data/
│  │  ├─ __init__.py              # market_data의 공개 이름 모음
│  │  ├─ provider.py              # MarketDataProvider 공통 약속
│  │  ├─ errors.py                # timeout/429/validation 표준 오류
│  │  ├─ validation.py            # 중복·정렬·일봉 gap 검사
│  │  ├─ candles.py               # closed candle 판정
│  │  └─ dataset.py               # DatasetSummary 결과 구조
│  ├─ strategy/
│     ├─ __init__.py              # Strategy 관련 공개 이름 모음
│     ├─ protocol.py              # Strategy가 따라야 하는 최소 약속
│     ├─ signal.py                # Signal과 bullish/bearish/neutral 유형
│     └─ moving_average_crossover.py # MA 교차 규칙과 계산 결과
│  ├─ risk/
│  │  ├─ __init__.py              # Risk 관련 공개 이름 모음
│  │  ├─ models.py                # Context, Limits, Decision 모델
│  │  ├─ protocol.py              # Risk Manager 최소 계약
│  │  └─ manager.py               # 세 가지 기본 BUY 위험 제한
│  └─ storage/
│     ├─ __init__.py              # storage 패키지와 SQLiteBarStore 공개
│     └─ sqlite.py                # SQLite 생성·저장·조회·summary
└─ tests/
   ├─ fixtures/
   │  └─ upbit_day_candles.json   # 인터넷 없이 쓰는 Upbit 응답 예제
   ├─ integration/
   │  └─ test_upbit_public_api.py # 실제 Upbit 공개 API 연결 검사
   ├─ test_bar.py
   ├─ test_backtest.py             # next-bar 체결, Risk, Portfolio, 결정론 검사
   ├─ test_backtest_cli.py         # SQLite→Backtest→출력 전체 흐름 검사
   ├─ test_cli.py
   ├─ test_closed_candles.py
   ├─ test_collect.py
   ├─ test_dataset.py
   ├─ test_instrument.py
   ├─ test_market_data_provider.py
   ├─ test_market_data_validation.py
   ├─ test_moving_average.py
   ├─ test_moving_average_strategy.py
   ├─ test_signal_cli.py
   ├─ test_smoke.py
   ├─ test_sqlite_bar_store.py
   ├─ test_upbit_provider.py
   └─ test_upbit_robustness.py
```

`__init__.py`는 해당 폴더가 Python 패키지임을 나타내고, 다른 파일에서 사용할 이름을 모아 공개하는 역할도 한다.

## 4. `collect` 명령 실행 흐름

예를 들어 다음 명령을 실행한다고 하자.

```powershell
python -m investing_plz collect `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --pages 10 `
  --database data\krw_btc_5y.db
```

실제 코드 흐름은 다음과 같다.

1. **`src/investing_plz/__main__.py`**
   - `python -m investing_plz`가 가장 먼저 실행하는 파일이다.
   - `cli.py`의 `main()`을 호출한다.

2. **`src/investing_plz/cli.py`의 `main()`**
   - `collect`, `--venue`, `--symbol`, `--pages`, `--database` 같은 입력을 읽는다.
   - `Instrument("upbit", "KRW-BTC")`를 만든다.
   - `UpbitMarketDataProvider`와 `SQLiteBarStore`를 만든 뒤 `collect_bars()`에 넘긴다.

3. **`src/investing_plz/application/collect.py`의 `collect_bars()`**
   - SQLite 테이블을 준비한다.
   - DB에서 해당 종목과 timeframe의 최신 timestamp를 읽는다.
   - provider에 최신 timestamp 이후 데이터가 필요하다고 요청한다.

4. **`src/investing_plz/adapters/upbit.py`의 `UpbitMarketDataProvider.get_bars()`**
   - Upbit 공개 candle API에 HTTP GET 요청을 보낸다.
   - 한 페이지에 최대 200개를 받고, `--pages` 수만큼 이전 페이지를 이어서 요청한다.
   - 각 Upbit JSON을 `upbit_candle_to_bar()`로 공통 `Bar`로 바꾼다.
   - Upbit가 보내는 최신순 데이터를 검사한 뒤 최종 결과는 과거→현재 오름차순으로 반환한다.

5. **`validate_bar_series()`**
   - `collect_bars()`가 받은 Bar 목록의 timestamp 중복, 오름차순, 하루 간격을 검사한다.
   - 문제가 있으면 저장하지 않고 명확한 오류를 발생시킨다.

6. **`src/investing_plz/storage/sqlite.py`의 `SQLiteBarStore.save()`**
   - 새 Bar를 `bars` 테이블에 저장한다.
   - 동일한 거래소·종목·timeframe·timestamp가 이미 있으면 다시 넣지 않는다.

7. **터미널 결과**
   - `fetched`, `inserted`, `total`, DB 경로를 출력한다.

```text
사용자 명령
  ↓
__main__.py
  ↓
cli.main()
  ↓
collect_bars()
  ↓
UpbitMarketDataProvider.get_bars()
  ↓
Upbit 공개 API → Upbit JSON → Bar
  ↓
validate_bar_series()
  ↓
SQLiteBarStore.save()
  ↓
SQLite DB 파일
```

## 5. 실제 데이터 한 건이 저장되는 과정

2026-09-24 비트코인 일봉 한 건을 예로 들면 다음과 같다.

### 1단계: Upbit JSON

Upbit는 대략 다음 의미의 데이터를 보낸다.

```json
{
  "candle_date_time_utc": "2026-09-24T00:00:00",
  "opening_price": 160000000,
  "high_price": 162000000,
  "low_price": 158000000,
  "trade_price": 161000000,
  "candle_acc_trade_volume": 7.125
}
```

### 2단계: 공통 `Bar`

`upbit_candle_to_bar()`가 공급자 전용 이름을 공통 이름으로 바꾼다.

```text
candle_date_time_utc      → timestamp
opening_price             → open
high_price                → high
low_price                 → low
trade_price               → close
candle_acc_trade_volume   → volume
```

가격과 거래량은 금융 숫자의 정밀도를 지키기 위해 `Decimal`로 바뀐다. timestamp에는 UTC 정보가 붙는다.

### 3단계: 검증

- 가격이나 거래량이 음수인지 확인한다.
- `high`가 open/close보다 낮지 않은지 확인한다.
- `low`가 open/close보다 높지 않은지 확인한다.
- 다른 Bar와 timestamp가 중복되지 않는지 확인한다.
- 일봉이 하루 간격으로 정렬되어 있는지 확인한다.

### 4단계: SQLite row

검증을 통과하면 `bars` 테이블에 다음 열로 저장된다.

```text
venue | symbol  | interval | timestamp                 | open ... volume
upbit | KRW-BTC | day      | 2026-09-24T00:00:00+00:00 | ...
```

## 6. `Bar`가 무엇인지

`Bar`는 일정 시간 동안의 시장 움직임을 한 줄로 요약한 공통 데이터 구조다. 현재는 일봉을 사용한다.

| 필드 | 쉬운 설명 |
|---|---|
| `timestamp` | 이 일봉이 시작된 UTC 시각 |
| `open` | 하루가 시작될 때의 가격, 시가 |
| `high` | 하루 동안 가장 높았던 가격, 고가 |
| `low` | 하루 동안 가장 낮았던 가격, 저가 |
| `close` | 현재 또는 하루가 끝났을 때의 가격, 종가 |
| `volume` | 하루 동안 거래된 비트코인의 양, 거래량 |

`Bar`에는 이 값 외에도 어떤 종목인지 나타내는 `instrument`와 시간 단위인 `interval`이 있다.

Upbit JSON을 그대로 DB에 넣지 않는 이유는 거래소마다 JSON 필드 이름과 형식이 다를 수 있기 때문이다. 먼저 공통 `Bar`로 바꾸면 나중에 다른 거래소나 주식 MarketDataProvider를 추가하더라도 이후 검증과 데이터 사용 코드는 같은 구조를 사용할 수 있다. 다만 현재 실제 provider 구현은 Upbit 일봉뿐이다.

## 7. SQLite DB 설명

SQLite는 별도의 DB 서버를 설치하지 않고 파일 하나에 표 형태의 데이터를 저장하는 작은 데이터베이스다.

현재 두 DB 파일이 있다.

### `data/market.db`

- 초기 수집과 중복 방지를 실제로 확인할 때 사용한 데이터다.
- 현재 확인된 상태에서는 400개의 KRW-BTC 일봉이 들어 있다.
- 기본 CLI에서 `--database`를 생략하면 이 경로를 사용한다.

### `data/krw_btc_5y.db`

- 백테스트 준비를 위해 수집한 약 5년치 KRW-BTC historical dataset이다.
- 현재 2021-04-05부터 2026-09-25까지 2,000개의 일봉이 있다.
- 그중 완료된 일봉은 1,999개이며, 2026-09-25 일봉은 당시 진행 중이었다.

DB 파일은 Python source code가 아니라 **프로그램이 만든 데이터 산출물**이다. `.py` 파일은 “어떻게 동작할지”를 적은 코드이고, `.db` 파일은 그 코드가 실제로 수집해 저장한 결과다.

## 8. Closed candle 설명

오늘 일봉은 하루가 끝나기 전까지 가격과 거래량이 계속 바뀐다. 예를 들어 2026-09-25 UTC 오전에 조회한 9월 25일 일봉은 아직 최종 종가가 정해지지 않았다. 이런 진행 중 데이터를 완성된 과거 데이터처럼 백테스트에 사용하면 미래 결과가 왜곡될 수 있다.

현재 `market_data/candles.py`는 일봉에 대해 다음 조건을 사용한다.

```text
now >= bar.timestamp + 1 day
```

예를 들어 2026-09-24 00:00 UTC 일봉은 2026-09-25 00:00 UTC부터 closed다.

현재 진행 중인 Bar가 DB에 저장되는 것은 허용된다. 대신 `SQLiteBarStore.load_closed_bars()`에 명시적인 `now`를 넘기면 closed Bar만 돌려준다. 따라서 앞으로 전략이나 백테스트는 전체 DB가 아니라 이 완료 데이터 조회 결과를 사용하면 된다. 현재 백테스트 엔진 자체는 아직 없다.

## 9. `summary` 명령

약 5년치 데이터셋을 확인하는 명령은 다음과 같다.

```powershell
python -m investing_plz summary `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db
```

출력 항목의 의미는 다음과 같다.

| 항목 | 의미 |
|---|---|
| `venue` | 데이터를 제공한 시장. 현재는 `upbit` |
| `symbol` | 종목 코드. 현재는 `KRW-BTC` |
| `timeframe` | candle 시간 단위. 현재는 `day` |
| `row_count` | DB에 저장된 전체 Bar 수 |
| `closed_bar_count` | 현재 시각 기준으로 완료된 Bar 수 |
| `earliest_timestamp` | 가장 오래된 Bar의 시작 시각 |
| `latest_timestamp` | 가장 최신 Bar의 시작 시각. 진행 중 Bar일 수 있음 |
| `latest_closed_timestamp` | 완료된 Bar 중 가장 최신 Bar의 시작 시각 |
| `duplicate_count` | 같은 timestamp가 추가로 존재하는 횟수. 정상은 0 |
| `gap_count` | 연속된 일봉 사이에서 빠진 날짜 수. 정상은 0 |

현재 `krw_btc_5y.db`의 확인 결과는 전체 2,000개, closed 1,999개, duplicate 0개, gap 0개다.

## 9A. Moving Average, Strategy, Signal

### Moving Average란 무엇인가

Moving Average(MA, 이동평균)는 최근 N개 종가의 평균이다. 매일 크게 흔들리는 가격을 조금 부드럽게 보게 해준다. 현재 코드는 `simple_moving_average(values, window)`로 계산하며 외부 라이브러리 없이 `Decimal` 값을 그대로 사용한다.

- **fast MA**: 짧은 기간 평균이다. 기본값은 최근 20개 일봉이며 최근 가격 변화에 더 빨리 반응한다.
- **slow MA**: 긴 기간 평균이다. 기본값은 최근 60개 일봉이며 더 천천히 움직인다.

### Strategy와 Signal

Strategy는 시장 데이터를 받아 정해진 규칙으로 판단하는 코드다. 현재 `MovingAverageCrossoverStrategy`는 직전 fast/slow MA와 현재 fast/slow MA를 비교해 실제 교차가 일어난 날만 crossover Signal을 만든다.

Signal은 Strategy의 판단 결과이며 실제 주문이 아니다. 현재 Signal은 `bullish_crossover`, `bearish_crossover`, `neutral` 중 하나다. `bullish_crossover`도 “매수 주문을 보냈다”는 뜻이 아니라 이동평균 규칙이 상승 교차를 발견했다는 뜻일 뿐이다.

### Instrument, Strategy, Parameter는 서로 별개다

- **Instrument**는 무엇을 분석하거나 투자할지 나타낸다. 예: `upbit:KRW-BTC`, `upbit:KRW-ETH`, 향후 `stock:SPY`.
- **Strategy**는 어떤 규칙으로 판단할지 나타낸다. 현재 구현된 것은 `MovingAverageCrossoverStrategy` 하나뿐이다.
- **Parameter**는 같은 Strategy를 어떤 설정으로 사용할지 나타낸다. 여기서는 `fast_window`와 `slow_window`다.
- **Risk**는 만들어진 OrderIntent가 운영 안전 한도 안에 있는지 검사하는 영역이다. 현재 기본 세 규칙만 구현되어 있다.
- **Profile**은 특정 Instrument에 어떤 Strategy와 Parameter를 사용할지 한데 묶은 설정이다.

따라서 Strategy 내부에서 종목 이름을 보고 규칙을 바꾸지 않는다. 사용자가 같은 Strategy class에 서로 다른 Instrument의 Bar와 서로 다른 parameter를 전달한다.

```text
KRW-BTC → MovingAverageCrossoverStrategy → fast=20, slow=60
KRW-ETH → MovingAverageCrossoverStrategy → fast=15, slow=50

향후 가능한 선택:
KRW-XRP → BreakoutStrategy
```

마지막 예시의 `BreakoutStrategy`는 구조를 설명하기 위한 미래 예시일 뿐 현재 코드에는 구현되어 있지 않다. YAML, Strategy registry, 종목별 profile loader도 아직 없다.

### Strategy Profile

지금은 `StrategyProfile`이라는 작은 immutable(만든 뒤 값을 바꾸지 않는) 설정 모델이 있다. Profile은 종목별 조건문을 Strategy 안에 넣는 대신, 종목과 Strategy 설정을 바깥에서 연결한다.

```text
KRW-BTC
└─ Profile
   ├─ Strategy = moving_average_crossover
   ├─ Fast = 20
   └─ Slow = 60

KRW-ETH
└─ Profile
   ├─ Strategy = moving_average_crossover
   ├─ Fast = 15
   └─ Slow = 50
```

`MovingAverageCrossoverParameters`는 fast와 slow가 양수인지, fast가 slow보다 작은지 Profile 생성 시 검사한다. `create_strategy_from_profile()`은 이 값을 `MovingAverageCrossoverStrategy`에 전달한다.

```text
Instrument + strategy_id + parameters
                ↓
         StrategyProfile
                ↓
 create_strategy_from_profile()
                ↓
 MovingAverageCrossoverStrategy
```

현재 Profile 값은 구조를 보여 주는 예제이며 “투자에 가장 좋은 설정”이라는 뜻이 아니다. 좋은 Strategy와 parameter인지는 향후 Backtest로 평가해야 한다. 현재는 MA Crossover Strategy 하나만 지원하며 YAML, JSON, DB 설정, registry, 상속 체계는 없다.

| 개념 | 의미 | 현재 상태 |
|---|---|---|
| Bar | 시장의 시가·고가·저가·종가·거래량 | 구현됨 |
| Indicator / MA | Bar의 종가로 계산한 값 | 구현됨 |
| Strategy | Indicator를 보고 판단하는 규칙 | MA crossover만 구현됨 |
| Signal | Strategy가 만든 판단 결과 | 구현됨, 주문 아님 |
| Order | 거래소에 보내는 실제 거래 요청 | 아직 구현되지 않음 |

### Signal과 OrderIntent

```text
Signal
  → 시장에 대한 Strategy의 판단

OrderIntent
  → 계산 결과 만들어진 내부 주문 후보

Risk Manager
  → 주문 후보가 안전한지 검사하고 승인·축소·거부

Order
  → Broker로 제출되는 실제 주문 (아직 구현되지 않음)
```

`OrderIntent`에는 Instrument, UTC timestamp, strategy ID, BUY/SELL 방향, quantity가 있다. Broker 주문 ID, 체결 상태, 수수료, 가격 같은 실행 정보는 아직 없다. 따라서 OrderIntent가 생겨도 거래소에는 아무 요청도 전달되지 않는다.

### Position sizing

Position sizing은 Signal과 목표 비중 설정을 실제 주문 후보 수량으로 바꾸는 계산이다. Strategy 안에서 계산하지 않으며, 현재는 Portfolio class 대신 필요한 값을 함수에 직접 전달한다.

```text
포트폴리오 가치 10,000,000원
  ↓
BTC 목표 비중 10%
  ↓
목표 가치 1,000,000원
  ↓
BTC 가격 100,000,000원
  ↓
목표 수량 0.01 BTC
  ↓
현재 0.004 BTC 보유
  ↓
BUY 0.006 BTC OrderIntent
```

계산식은 다음과 같다.

```text
target_value = portfolio_value × target_weight
target_quantity = target_value ÷ current_price
difference = target_quantity - current_quantity
```

차이가 양수면 BUY, 음수면 절대값 수량의 SELL Intent가 된다. 차이가 0이거나 주문 가능 단위로 내림한 결과가 0이면 Intent를 만들지 않는다. 현재는 long-only이므로 목표 비중은 0부터 1까지만 허용한다.

`quantity_step`은 주문 수량 단위다. 예를 들어 `Decimal("0.00000001")`이면 계산된 차이를 이 단위 이하로 보수적으로 내림한다. 아직 거래소별 lot-size framework는 없으며 호출하는 쪽에서 step을 명시한다.

```text
Bar
  ↓
Indicator
  ↓
Strategy
  ↓
Signal
  ↓
Position sizing
  ↓
OrderIntent
  ↓
Risk Manager
  ↓
APPROVED / ADJUSTED / REJECTED
  ↓
Order         (아직 미구현)
```

### Basic Risk Manager

Risk Manager는 OrderIntent를 실제 주문으로 보내기 전에 운영자가 정한 안전 한도를 검사한다. 현재는 실제 Order가 없으므로 검사 결과까지만 만들며 Upbit 주문은 발생하지 않는다.

```text
OrderIntent: "BUY 0.01 BTC를 원함"
  ↓
BasicRiskManager
  ├─ 최대 주문 금액 검사
  ├─ 최대 종목 비중 검사
  └─ 최소 현금 보유 검사
  ↓
APPROVED / ADJUSTED / REJECTED
  ↓
Order  (아직 미구현)
```

- **APPROVED**: 원래 Intent를 그대로 허용한다.
- **ADJUSTED**: 안전 한도 안으로 수량을 줄여 허용한다.
- **REJECTED**: 허용할 수 있는 수량이 없어 거부한다.

예를 들어 `BUY 0.01 BTC`가 100만원이지만 최대 주문 금액이 50만원이면 `BUY 0.005 BTC`로 ADJUSTED된다. 여러 한도가 동시에 적용되면 허용 금액이 가장 작은 제한을 사용하므로 규칙 검사 순서에 따라 결과가 바뀌지 않는다.

Risk 계산에는 portfolio value, available cash, 현재 종목 가치, 현재 가격, 수량 단위를 직접 전달한다. 아직 Portfolio class나 실제 잔고 조회는 없다. SELL은 long 포지션을 줄이는 방향이므로 BUY용 현금·노출 한도로 막지 않는다.

### 금융 값에 Decimal을 사용하는 이유

Python의 `float`는 0.1 같은 십진수를 내부에서 정확히 표현하지 못해 작은 오차가 생길 수 있다. 가격, 수량, 금액 계산에서는 이런 오차가 쌓일 수 있으므로 이 프로젝트는 문자열로 만든 `Decimal`, 예를 들어 `Decimal("0.01")`을 사용한다. `OrderIntent.quantity`에 `0.01` 같은 float를 넣으면 명확하게 거부한다.

OrderIntent를 저장하거나 전달할 때는 `to_dict()`로 timestamp, side, quantity를 문자열 중심의 단순한 dict로 바꾼다. `from_dict()`로 다시 만들면 원래 값과 타입이 보존된다.

### Crossover 규칙

```text
bullish crossover:
직전 fast <= 직전 slow, 현재 fast > 현재 slow

bearish crossover:
직전 fast >= 직전 slow, 현재 fast < 현재 slow

그 외:
neutral
```

단순히 fast MA가 slow MA보다 높은 상태가 계속된다고 매일 bullish Signal을 만들지 않는다. 직전과 현재 사이에 실제로 선이 교차한 순간만 crossover다. 직전 60일 평균과 현재 60일 평균이 모두 필요하므로 20/60 설정에는 최소 61개의 closed Bar가 필요하다.

### `signal` CLI

```powershell
python -m investing_plz signal `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db `
  --fast 20 `
  --slow 60
```

실제 실행 순서는 다음과 같다.

```text
cli.py의 main()
  ↓
SQLiteBarStore.load_closed_bars()
  ↓
완료된 Bar만 반환
  ↓
MovingAverageCrossoverStrategy.evaluate()
  ↓
simple_moving_average()
  ↓
Signal + 직전/현재 MA
  ↓
터미널 출력
```

데이터 흐름으로 보면 더 간단하다.

```text
data/krw_btc_5y.db
  ↓
closed Bars
  ↓
Moving Average
  ↓
MA Crossover Strategy
  ↓
Signal
  ↓
터미널 출력
```

이 명령은 DB를 읽기만 한다. 현재 진행 중인 오늘 일봉은 `load_closed_bars()`에서 제외된다.

`signal`을 실제 실행하면 저장된 시장 데이터로 현재 판단을 계산한다. 반면 Strategy 테스트는 사람이 만든 고정 Bar를 사용해 bullish, bearish, neutral 규칙이 언제나 같은 결과를 내는지 검사한다. 테스트는 실제 투자 판단이나 주문을 수행하지 않는다.

## 9B. 최소 Backtest

Backtest는 과거 시장 데이터를 오래된 순서부터 다시 재생하면서 현재 Rule을 적용했을 때 가상 돈이 어떻게 변했는지 보는 실험이다. M3-A의 목적은 수익성을 증명하는 것이 아니라 지금까지 만든 구성요소가 올바른 순서로 연결되는지 확인하는 것이다.

```text
Historical closed Bars
  ↓
Strategy
  ↓
Signal (Bar T의 close까지 사용)
  ↓
다음 Bar T+1 open
  ↓
Position sizing
  ↓
OrderIntent
  ↓
BasicRiskManager
  ↓
Simulated Fill
  ↓
가상 Portfolio
  ↓
다음 Bar...
```

- **Fill**은 승인된 주문 후보가 특정 가격에서 실제로 체결됐다고 가정한 결과다. 여기서는 다음 Bar의 open 가격에 전체 수량이 즉시 체결됐다고 가정한다.
- **Portfolio**는 Backtest 안의 가상 현금과 단일 종목 보유 수량이다. 실제 Upbit 계좌나 잔고가 아니다.
- **Mark-to-market**은 마지막에 팔지 않은 보유 자산을 최신 closed Bar의 close 가격으로 평가하는 것이다.
- **Look-ahead bias**는 그 시점에는 알 수 없던 미래 정보를 과거 판단에 사용하는 오류다.

Bar T의 종가는 하루가 끝나야 알 수 있으므로, 그 종가로 만든 Signal을 같은 Bar의 open이나 close에 체결하지 않는다. Signal은 다음 Bar까지 기다리고, T+1 open 가격으로 sizing과 Risk 검사를 한 뒤 같은 가격으로 Fill한다. 마지막 Bar에서 생긴 Signal은 다음 Bar가 없으므로 체결되지 않는다.

Backtest에서 Signal은 한 번의 주문 지시가 아니라 **목표 상태를 바꾸는 사건**으로 사용된다.

```text
bullish crossover → 설정된 목표 비중(예: BTC 10%)으로 변경
neutral           → 기존 목표를 그대로 유지
bearish crossover → 목표 비중 0%로 변경
```

`max_order_amount`는 총 목표 포지션이 아니라 **한 번에 허용할 주문 크기**다. 목표 BTC 가치가 100만원이고 한 번 주문 한도가 50만원이면 첫 open에서 약 50만원을 사고, Risk 결과가 ADJUSTED이므로 다음 Bar open에서 남은 목표분을 다시 계산한다. APPROVED되어 목표 조정이 끝나면 pending 상태를 종료하므로 이후 가격만 움직였다는 이유로 매일 10%에 다시 맞추지는 않는다. REJECTED되거나 반올림 후 Intent가 없을 때도 자동 재시도를 끝낸다.

Bullish target adjustment는 사고 싶은 방향으로 목표에 접근하는 과정이다. 진행 중 가격이 올라 목표를 조금 초과해 계산상 SELL이 필요해져도 반대 방향으로 미세 조정하지 않고 진입을 완료한 것으로 처리한다. Bearish는 반대로 보유 수량을 0으로 만드는 청산 과정이므로 SELL만 허용한다.

`min_trade_amount`는 목표와의 차이가 너무 작을 때 의미 없는 소액 BUY를 만들지 않기 위한 Backtest 운영 기준이다. 예를 들어 남은 BUY 필요 금액이 3원이고 최소 주문 기준이 10,000원이면 추가 주문 없이 진입을 끝낸다. 이는 Upbit의 공식 최소 주문 금액이나 추천 설정이 아니다. Bearish 청산 SELL은 작은 잔여 포지션을 영구히 남기지 않도록 이 기준보다 작아도 전량 청산한다.

**Fee**는 거래가 체결될 때 거래대금과 별도로 빠지는 수수료다. **Slippage**는 Bar의 open 같은 기준 시장가격보다 불리한 가격에 체결된다고 가정하는 비용이다. 예를 들어 open이 100,000,000원이고 slippage가 5 bps라면 BUY는 100,050,000원, SELL은 99,950,000원에 체결된다. `fee_rate=0.0005`이면 체결 거래대금의 0.05%를 fee로 반영한다.

이 비용 값은 실제 시장 비용을 자동으로 조회하거나 추정한 결과가 아니다. 사용자가 Backtest 가정으로 직접 지정하는 값이다.

### Backtest 성과를 읽는 기본 지표

- **Equity Curve**는 각 closed Bar의 close 시점에 가상 계좌 전체 가치가 어떻게 변했는지 기록한 흐름이다.
- **Total Return**은 초기 자금 대비 마지막 계좌 가치의 전체 변화율이다. `0.16`은 전체 기간 약 16%를 뜻한다.
- **CAGR**은 첫 Bar부터 마지막 Bar까지의 실제 기간을 연 단위로 환산한 연평균 복리 변화율이다.
- **MDD(Maximum Drawdown)**는 이전 최고 계좌 가치에서 가장 크게 하락했던 비율이다. 이 프로젝트에서는 `-0.10`처럼 음수로 표시하며 이는 최대 약 10% 하락을 뜻한다.
- **Passive 10%**는 첫 Bar open에서 자금의 10%만 BTC로 사고 나머지 90%는 현금으로 둔 비교 기준이다. 이후 BTC 비중이 변해도 다시 10%로 맞추지 않으므로, 현재 Strategy와 초기 노출만 비슷할 뿐 지속적인 10% 비중 유지 benchmark는 아니다.
- **BTC 100% Buy & Hold**는 첫 Bar open에서 가능한 만큼 BTC를 한 번 사고 마지막 close까지 그대로 보유하는 비교 기준이다. 현재 Strategy보다 BTC 가격 위험에 훨씬 많이 노출된다.

현재 약 5년 dataset과 `fee_rate=0.0005`, `slippage_bps=5` 가정에서 확인한 참고값은 다음과 같다.

| 비교 대상 | 최종 가치 | Total Return | CAGR | MDD |
|---|---:|---:|---:|---:|
| MA Strategy 10% | 약 11,603,960원 | 약 16.04% | 약 2.76%/년 | 약 -4.76% |
| Passive 10% | 약 10,556,083원 | 약 5.56% | 약 0.99%/년 | 약 -10.53% |
| BTC 100% Buy & Hold | 약 15,560,827원 | 약 55.61% | 약 8.42%/년 | 약 -74.13% |

이 값들은 특정 dataset과 비용 가정으로 계산한 과거 시뮬레이션 참고값이다. 데이터 기간, 비용, 규칙이 바뀌면 결과도 달라지며 실제 과거 결과가 미래 수익을 보장하지 않는다. 특히 100% BTC benchmark는 위험 노출이 달라 MA Strategy 10%와 같은 위험 수준의 직접 비교가 아니다.

현재 가상 Portfolio는 `cash`와 `position_quantity`만 가진다. BUY Fill은 현금을 줄이고 수량을 늘리며, SELL Fill은 반대로 처리한다. 보유량보다 많이 팔 수 없다. 종료 시에는 `cash + position_quantity × latest_close`로 최종 가치를 계산한다.

```powershell
python -m investing_plz backtest `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db `
  --fast 20 `
  --slow 60 `
  --initial-cash 10000000 `
  --target-weight 0.10 `
  --quantity-step 0.00000001 `
  --min-trade-amount 10000 `
  --fee-rate 0.0005 `
  --slippage-bps 5 `
  --max-order-amount 500000 `
  --max-instrument-weight 0.20 `
  --min-cash-reserve 1000000
```

이 명령은 DB의 closed Bar만 읽고 DB를 수정하지 않는다. 금융 옵션은 `Decimal`로 해석된다. `fee_rate`와 `slippage_bps`의 기본값은 0이다. 평균단가와 실현손익 같은 상세 회계는 아직 없으며, 과거 지표만 보고 Strategy가 좋다고 단정하면 안 된다.

가상 체결 내역도 확인하려면 같은 명령 끝에 `--show-fills`를 붙인다.

```powershell
python -m investing_plz backtest `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db `
  --show-fills
```

`--show-fills`는 Backtest 계산을 바꾸지 않고, 이미 계산된 Fill의 시간, BUY/SELL 방향, 수량, 체결 가격, 거래대금과 fee를 요약 아래에 추가로 보여 주는 선택 옵션이다.

## 10. pytest란 무엇인가

다음 명령은 시장 데이터를 수집하는 명령이 아니다.

```powershell
python -m pytest -q
```

`pytest`는 **작성된 코드가 예상대로 동작하는지 자동으로 검사하는 도구**다. `-q`는 결과를 간단히 보여 달라는 옵션이다.

테스트는 예를 들어 다음을 확인한다.

- 이상한 OHLCV가 들어오면 거부하는가?
- 같은 Bar를 두 번 저장해도 중복 행이 생기지 않는가?
- 최신 timestamp 이후 데이터만 가져오는가?
- pagination 경계에서 데이터가 빠지거나 겹치지 않는가?
- timeout과 HTTP 429를 올바른 오류로 바꾸는가?
- 오늘 진행 중인 일봉을 closed로 잘못 판단하지 않는가?
- SQLite에서 closed Bar만 정상 조회되는가?
- summary의 row, 날짜 범위, gap 수가 맞는가?

즉, `collect`는 실제 데이터를 만드는 실행이고, `pytest`는 그 실행에 쓰이는 부품들이 올바른지 검사하는 실행이다.

## 11. 현재 테스트 파일 설명

| 테스트 파일 | 검사하는 내용 |
|---|---|
| `test_smoke.py` | 설치된 패키지와 핵심 모델을 import할 수 있는지 |
| `test_instrument.py` | Upbit KRW-BTC 식별과 빈 venue/symbol 거부 |
| `test_bar.py` | UTC timestamp와 OHLCV 기본 불변조건 |
| `test_market_data_provider.py` | fake provider가 공통 provider 계약처럼 동작하는지 |
| `test_upbit_provider.py` | 저장된 Upbit fixture가 올바른 Bar로 변환되고 시간순으로 반환되는지 |
| `test_upbit_robustness.py` | pagination, 페이지 경계, timeout, 429, 중복, 잘못된 순서와 OHLCV |
| `test_market_data_validation.py` | Bar 목록의 중복·역순·일봉 gap 검사 |
| `test_moving_average.py` | SMA 정상 계산, 정확한 길이, 부족한 데이터, 잘못된 window |
| `test_moving_average_strategy.py` | bullish/bearish 교차, neutral, 최소 Bar 수와 window 검증 |
| `test_strategy_reuse.py` | 같은 Strategy의 KRW-BTC/KRW-ETH 및 서로 다른 parameter 재사용 |
| `test_strategy_profile.py` | BTC/ETH Profile, Strategy 생성, fast/slow parameter 검증 |
| `test_order_intent.py` | BUY/SELL Intent, Decimal·UTC 검증과 JSON round-trip |
| `test_position_sizing.py` | 목표 비중 수량, BUY/SELL, 내림, 입력 검증, BTC/ETF 재사용 |
| `test_risk_manager.py` | 승인·축소·거부, 주문금액·종목비중·현금 한도와 SELL 처리 |
| `test_signal_cli.py` | 진행 중 Bar 제외와 signal CLI 전체 흐름 |
| `test_sqlite_bar_store.py` | SQLite 저장, 값 round-trip, 중복 방지, 최신 timestamp 조회 |
| `test_collect.py` | 수집 use case의 중복 없는 재실행과 중단 후 이어받기 |
| `test_closed_candles.py` | 과거/현재 일봉과 정확한 UTC 종료 경계 판정 |
| `test_dataset.py` | open candle 제외 조회, summary 수와 날짜 범위, gap 계산 |
| `test_cli.py` | 인터넷 없이 collect 및 summary 명령이 끝까지 동작하는지 |
| `integration/test_upbit_public_api.py` | 실제 Upbit 공개 API에서 데이터를 받아 임시 SQLite DB에 저장하는지 |

`tests/fixtures/upbit_day_candles.json`은 실제 인터넷을 사용하지 않고도 Upbit 응답 변환을 반복 검사하기 위한 고정 예제다.

## 12. Unit Test와 Integration Test 차이

### Unit Test

작은 코드 단위를 가짜 데이터나 fixture로 검사한다.

- 인터넷이 필요 없다.
- 빠르고 결과가 일정하다.
- Upbit가 잠시 장애여도 코드 자체를 검사할 수 있다.
- 기본 `python -m pytest -q`에서 실행된다.

### Integration Test

여러 부품과 외부 서비스를 실제로 연결해 검사한다.

- 실제 Upbit 공개 API와 인터넷을 사용한다.
- 외부 네트워크나 Upbit 상태에 따라 실패할 수 있다.
- 실제 API 응답이 provider, Bar, collect, SQLite까지 이어지는지 확인한다.

현재 integration test는 `RUN_UPBIT_INTEGRATION=1` 환경변수가 있을 때만 실행된다. 기본 테스트가 인터넷 상태 때문에 불안정해지거나 Upbit에 불필요한 요청을 보내는 것을 막기 위해서다. 실제 DB가 아닌 pytest의 임시 DB를 사용한다.

## 13. 내가 자주 사용할 명령어

모든 명령은 PowerShell에서 프로젝트 루트 `D:\Projects\Inversting_plz`로 이동한 뒤 실행한다.

### 프로젝트 폴더로 이동

```powershell
cd D:\Projects\Inversting_plz
```

이후 명령의 기준 위치를 프로젝트 루트로 바꾼다.

### 가상환경 활성화

```powershell
.\.venv\Scripts\Activate.ps1
```

이 프로젝트에 설치된 Python과 pytest를 사용하도록 한다. 활성화가 어려우면 아래 명령들의 `python` 대신 `.\.venv\Scripts\python.exe`를 사용해도 된다.

### 기본 테스트 실행

```powershell
python -m pytest -q
```

인터넷 없이 코드 동작을 자동 검사한다. 실제 Upbit integration test는 skip된다.

### 실제 Upbit integration test 실행

```powershell
$env:RUN_UPBIT_INTEGRATION = "1"
python -m pytest -q -m integration
Remove-Item Env:RUN_UPBIT_INTEGRATION
```

실제 Upbit 공개 API 연결을 검사하고, 끝난 뒤 opt-in 환경변수를 제거한다.

### KRW-BTC 최신 데이터 수집

```powershell
python -m investing_plz collect `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --pages 10 `
  --database data\krw_btc_5y.db
```

Upbit 일봉을 요청해 검증한 뒤 기존 DB의 최신 timestamp보다 새로운 Bar를 저장한다. 같은 데이터는 추가되지 않는다.

### 약 5년 데이터셋 요약

```powershell
python -m investing_plz summary `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db
```

저장 개수, closed 개수, 날짜 범위, 중복과 gap을 출력한다.

### 최신 MA crossover Signal 확인

```powershell
python -m investing_plz signal `
  --venue upbit `
  --symbol KRW-BTC `
  --timeframe day `
  --database data\krw_btc_5y.db `
  --fast 20 `
  --slow 60
```

완료된 일봉만 읽어 직전·현재 20일/60일 MA와 Strategy Signal을 출력한다. DB는 수정하지 않으며 주문도 만들지 않는다.

### SQLite row 수 직접 확인

```powershell
python -c "import sqlite3; db=sqlite3.connect(r'data\krw_btc_5y.db'); print(db.execute('SELECT COUNT(*) FROM bars').fetchone()[0]); db.close()"
```

`bars` 테이블의 전체 행 수를 직접 출력한다.

### 최신 5개 Bar 직접 확인

```powershell
python -c "import sqlite3; db=sqlite3.connect(r'data\krw_btc_5y.db'); print(*db.execute('SELECT * FROM bars ORDER BY timestamp DESC LIMIT 5').fetchall(), sep='\n'); db.close()"
```

DB에 저장된 가장 최신 5개 행을 보여준다.

### Git 작업 상태 확인

```powershell
git status --short
```

커밋 이후 수정·생성된 파일을 짧게 보여준다. `M`은 수정, `??`는 아직 Git이 추적하지 않는 새 파일이다.

## 14. 실행 / 테스트 / 산출물 구분

| 구분 | 예시 | 목적 | 실제 데이터 변경 |
|---|---|---|---|
| A. 프로그램 실행 | `python -m investing_plz collect ...` | Upbit에서 시장 데이터를 가져와 지정한 DB에 저장 | 예. SQLite DB가 생성되거나 새 행이 추가됨 |
| A-2. 분석 실행 | `python -m investing_plz signal ...` | 저장된 closed Bar로 MA와 Signal 계산 | 아니요. DB를 읽기만 함 |
| B. 테스트 실행 | `python -m pytest -q` | 코드가 예상대로 작동하는지 자동 검사 | 실제 dataset은 변경하지 않음. 테스트용 임시 파일 사용 |
| C. 산출물 확인 | `summary` 명령, `data/krw_btc_5y.db` | 실제 저장 결과의 수량·기간·품질 확인 | summary는 읽기만 하며 DB 내용을 바꾸지 않음 |

가장 중요한 차이는 다음과 같다.

- **프로그램 실행**은 실제 결과를 만든다.
- **테스트 실행**은 코드의 정확성을 검사한다.
- **산출물 확인**은 이미 만들어진 결과를 읽어 상태를 보여준다.

## 15. 현재 전체 흐름 그림

### 실제 데이터 수집 흐름

```text
                 [ Upbit 공개 API ]
                         │
                         │ OHLCV JSON
                         ▼
              [ UpbitMarketDataProvider ]
                         │
                         │ 공통 형식 변환
                         ▼
                       [ Bar ]
                         │
                  순서·중복·gap 검증
                         │
                         ▼
                 [ collect_bars() ]
                         │
                         ▼
                 [ SQLiteBarStore ]
                         │
                         ▼
               data/krw_btc_5y.db
                         │
                 ┌───────┴────────┐
                 ▼                ▼
          closed Bar 조회     summary CLI
                 │
                 ▼
             20/60 MA
                 │
                 ▼
        MA Crossover Strategy
                 │
                 ▼
               Signal
```

### 테스트 흐름

```text
tests/
├─ domain 검사        → Instrument, Bar, UTC
├─ provider 검사      → Upbit JSON 변환, pagination, 오류
├─ validation 검사    → 중복, 순서, gap, 비정상 OHLCV
├─ DB 검사            → 저장, 중복 방지, 최신 timestamp
├─ dataset 검사       → closed 조회와 summary
├─ CLI 검사           → 명령 전체 흐름
└─ integration 검사   → 실제 Upbit API 연결, 명시적으로 켤 때만 실행
```

## 16. 현재 개발 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| M0 | Python package, Instrument, Bar, MarketDataProvider 기본 구조 | 완료 |
| M1 | Upbit 일봉 수집, pagination, 검증, SQLite, CLI | 완료 |
| M1.5 | closed candle, historical dataset, summary | 완료 |
| M2-A | Strategy, Signal, 20/60 MA crossover | 완료 |
| M2-B1 | Instrument별 Strategy Profile | 완료 |
| M2-B2-A | OrderIntent와 Decimal 기초 | 완료 |
| M2-B2-B | Position sizing과 BTC/ETF 재사용 | 부분 완료 |
| M2-C1 | Basic Risk Manager | 완료 |
| M2-C2 | 중복 미체결 주문과 운영 위험 | **아직 구현되지 않음** |
| M3-A | 최소 결정론적 Backtest | 완료 |
| M3-B1 | 수수료·slippage 실행 비용 | 완료 |
| M3-B2 | Equity Curve·Total Return·MDD·CAGR·Passive benchmark | 완료 |
| M3-C | 실행 metadata·범용 architecture 강화 | **아직 구현되지 않음** |

현재 저장소에는 Signal, Position sizing, OrderIntent, 기본 Risk 판단과 단일 종목 가상 Portfolio를 사용하는 최소 Backtest가 있다. 실제 Order, 미체결 주문 상태, Broker와 실제 계좌 Portfolio는 아직 없다.

## 17. 초보자가 지금 이해하면 충분한 것

처음부터 모든 Python 문법과 파일 내부를 이해할 필요는 없다. 현재는 다음 다섯 가지를 이해하면 충분하다.

1. **어디서 실행하는가**  
   프로젝트 루트에서 가상환경을 활성화하고 `python -m investing_plz ...`를 실행한다.

2. **데이터가 어디서 들어오는가**  
   API key가 필요 없는 Upbit 공개 candle API에서 KRW-BTC 일봉이 들어온다.

3. **데이터가 어떤 형태로 변환되는가**  
   Upbit JSON은 거래소와 무관한 공통 `Bar`로 변환되고 검증된다.

4. **어디에 저장되는가**  
   실제 약 5년 데이터는 `data/krw_btc_5y.db`의 `bars` 테이블에 저장된다.

5. **테스트가 무엇을 검증하는가**  
   `pytest`는 데이터 변환, 검증, 저장, closed 판정, summary가 예상대로 동작하는지 자동 검사한다. 실제 시장 데이터를 수집하는 명령과는 다르다.
