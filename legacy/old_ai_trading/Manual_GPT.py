# 새로운 환경에선 마우스 위치 수정 필수!
import pyautogui, time, re, json, pyperclip

def Input_GPT():
    time.sleep(3)  
    # 실행 후 3초 대기 (마우스 옮길 시간)

    # alt+tab (Chatgpt Web)
    pyautogui.hotkey('alt', 'tab')
    time.sleep(1)

    # ctrl+shift+o
    pyautogui.hotkey('ctrlleft', 'shift', 'o')
    time.sleep(1)

    # ctrl+v
    pyautogui.hotkey('ctrlleft', 'v')
    time.sleep(1)

    # enter
    pyautogui.hotkey('enter')

    # 30초 기다리기
    time.sleep(20)

    pyautogui.click()          # 현재 마우스 위치 클릭 -> 텍스트박스 포커스 유도
    time.sleep(0.3)

    # ctrl+a
    pyautogui.hotkey('ctrlleft', 'a')
    time.sleep(1)

    # ctrl+c
    pyautogui.hotkey('ctrlleft', 'c')
    time.sleep(1)

    #Chat gpt Session 닫기
    pyautogui.moveTo(1875, 147)
    pyautogui.click()          # 현재 마우스 위치 클릭 / 메뉴열기
    time.sleep(0.3)

    pyautogui.moveTo(1775, 368)
    pyautogui.click()          # 현재 마우스 위치 클릭 / 닫기 1
    time.sleep(0.3)

    pyautogui.moveTo(1131, 600)
    pyautogui.click()          # 현재 마우스 위치 클릭 / 닫기 2
    time.sleep(0.3)

    # alt+tab (Vscode)
    pyautogui.hotkey('alt', 'tab')
    time.sleep(1)

    pyautogui.click()          # 현재 마우스 위치 클릭 -> 텍스트박스 포커스 유도
    time.sleep(0.3)

    text = pyperclip.paste()

    # 가장 마지막 JSON 객체 후보를 뒤에서부터 찾기
    # (단순 정규식은 중괄호 중첩에 약하니, 아래는 "마지막 {부터 끝까지"를 먼저 잡고 json 시도)
    last_brace = text.rfind('{')
    if last_brace == -1:
        return None

    candidate = text[last_brace:].strip()

    # 혹시 뒤에 다른 글자가 붙었으면 JSON 끝을 대충 정리
    # 가장 마지막 '}' 위치로 자르기
    last_close = candidate.rfind('}')
    candidate = candidate[:last_close+1]

    # JSON 파싱 시도 (실패하면 None)
    try:
        obj = json.loads(candidate)
    except Exception:
        return None

    only = json.dumps(obj, ensure_ascii=False)
    #클립보드에 넣지 말고, only로 return해서 사용
    #pyperclip.copy(only)
    return only