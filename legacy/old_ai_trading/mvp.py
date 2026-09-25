import os
from dotenv import load_dotenv
load_dotenv()

def ai_trading():
    # 1. 업비트 차트 데이터 가져오기 (30일 일봉)
    import pyupbit
    #o 시가, h 고가, l 저가, c 종가, v 거래량, count 개수, interval 조회단위
    df = pyupbit.get_ohlcv("KRW-BTC", count=30, interval="day")
    df_json = df.to_json()
    #print(df_json)

    # 2. AI에게 데이터 제공하고 판단 받기

    from openai import OpenAI
    client = OpenAI()

    response = client.responses.create(
    prompt={
        "id": "pmpt_69a42fbb75048197b0a594ebc67ebeec0d6e59316a625c1b",
        "version": "4"
    },
    input=[
        {
            "role" : "user",
            "content" : [
                {
                    "type" : "input_text",
                    "text" : "Json Data :\n" + df_json
                }
            ]
        }
    ],
    text={
        "format": {
        "type": "json_object"
        }
    },
    reasoning={},
    store=True,
    include=["web_search_call.action.sources"]
    )

    # 3. AI의 판단에 따라 실제로 자동매매 진행하기

    # result 형태를 string -> json으로 변환
    #'dict' type으로 사용 가능함
    import json
    result = json.loads(response.output_text)

    # print(type(result))
    # print(result["decision"])
    # print(result["reason"])

    print("#### AI Decision : ", result["decision"].upper(), "###")
    print(f"### Reason : ", result["reason"], "###")

    # 업비트 로그인
    import pyupbit
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    upbit = pyupbit.Upbit(access, secret)

    if result["decision"] == "buy":
        # 시장가 매수
        Cash = upbit.get_balance("KRW")                     # 보유 현금 조회
        Available_Cash = upbit.get_balance("KRW")*0.9995    # 수수료 고려한 금액
        if Available_Cash > 5000:
            #print(upbit.buy_market_order("KRW-BTC", Available_Cash))
            print("buy : ", result["reason"])
        else :
            print("Err - KRW 잔고 5000원 미만")

    elif result["decision"] == "sell":
        # 시장가 매도
        Hold_BTC = upbit.get_balance("KRW-BTC")             # KRW-BTC 조회
        Cur_BTC = pyupbit.get_orderbook(ticker="KRW-BTC")['orderbook_units'][0]["ask_price"]
        if Hold_BTC*Cur_BTC > 5000:
            #print(upbit.sell_market_order("KRW-BTC", Hold_BTC))
            print("sell : ", result["reason"])
        else :
            print("Err - 구매금액 KRW 5000원 미만")
            
    elif result["decision"] == "hold":
        # 홀딩
        pass

while True:
    import time
    time.sleep(10)
    ai_trading()






