import os
from dotenv import load_dotenv
load_dotenv()

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
  max_output_tokens=258,
  store=True,
  include=["web_search_call.action.sources"]
)


import json
result = json.loads(response.output_text)
print(result["decision"])
print(result["reason"])

