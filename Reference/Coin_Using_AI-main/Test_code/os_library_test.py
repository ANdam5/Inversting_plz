import os
from dotenv import load_dotenv
load_dotenv()

#os library test
print(os.getenv("UPBIT_ACCESS_KEY"))
print(os.getenv("UPBIT_SECRET_KEY"))
print(os.getenv("OPENAI_API_KEY"))