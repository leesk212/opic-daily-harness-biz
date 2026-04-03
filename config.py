import os
from dotenv import load_dotenv

load_dotenv()

# KakaoTalk delivery via AppleScript (UI automation)
KAKAO_SEND_SCRIPT = os.path.join(os.path.dirname(__file__), "scripts", "kakao_send.scpt")
KAKAO_RECIPIENTS_PATH = os.path.join(os.path.dirname(__file__), "data", "kakao_recipients.json")
SELECTED_TOPICS_PATH = os.path.join(os.path.dirname(__file__), "data", "selected_topics.json")

_DEFAULT_RECIPIENTS = [
    {"name": "me", "self": True, "row": 1},
    {"name": "16추호성", "self": False, "row": 2},
]

def load_kakao_recipients():
    import json
    try:
        with open(KAKAO_RECIPIENTS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_kakao_recipients(_DEFAULT_RECIPIENTS)
        return _DEFAULT_RECIPIENTS

def save_kakao_recipients(recipients):
    import json
    os.makedirs(os.path.dirname(KAKAO_RECIPIENTS_PATH), exist_ok=True)
    with open(KAKAO_RECIPIENTS_PATH, "w") as f:
        json.dump(recipients, f, ensure_ascii=False, indent=2)


# 기본 선택 주제 12개
_DEFAULT_SELECTED_TOPICS = [
    "자기소개", "거주지/집", "여가/취미", "음악 감상", "영화 보기", "공원 가기",
    "해변/바다", "국내 여행", "해외 여행", "쇼핑", "요리/음식", "건강/운동",
]

def load_selected_topics():
    import json
    try:
        with open(SELECTED_TOPICS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_selected_topics(_DEFAULT_SELECTED_TOPICS)
        return _DEFAULT_SELECTED_TOPICS

def save_selected_topics(topics):
    import json
    os.makedirs(os.path.dirname(SELECTED_TOPICS_PATH), exist_ok=True)
    with open(SELECTED_TOPICS_PATH, "w") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

# QG Prompt Template
QG_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "data", "qg_prompt.txt")

_DEFAULT_QG_PROMPT = """당신은 OPIC {level} 등급 전문 출제위원입니다.

주제: {topic}
문제 유형: {question_type}

규칙:
1. 모든 문제는 영어로 출제합니다 (실제 OPIC 시험과 동일).
2. {level} 등급에 맞는 난이도로 출제합니다.
3. 자연스럽고 실제 시험에 나올 법한 문제를 만듭니다.
4. 콤보 세트의 경우 3개의 연관 질문을 만듭니다.
5. 롤플레이의 경우 구체적인 상황을 설정합니다.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력:
{{"question": "영어 질문 전문", "sample_answer": "AL등급 수준의 모범 답변 (영어, 200단어 이상)", "key_expressions": "답변에 활용하면 좋은 핵심 표현 5개 (쉼표 구분, 반드시 하나의 문자열)", "tip": "이 문제를 잘 답하기 위한 전략 팁 (한국어)"}}"""

def load_qg_prompt():
    try:
        with open(QG_PROMPT_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        save_qg_prompt(_DEFAULT_QG_PROMPT)
        return _DEFAULT_QG_PROMPT

def save_qg_prompt(prompt):
    os.makedirs(os.path.dirname(QG_PROMPT_PATH), exist_ok=True)
    with open(QG_PROMPT_PATH, "w") as f:
        f.write(prompt)

# Claude Code CLI is used for question generation (no API key needed)

# Schedule: comma-separated hours in KST (e.g. "6,12,18,0")
SCHEDULE_HOURS = [int(h.strip()) for h in os.getenv("SCHEDULE_HOURS", "6,12,18,0").split(",")]
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# OPIC Settings
OPIC_TARGET_LEVEL = "AL"  # Advanced Low

OPIC_TOPICS = [
    "자기소개",
    "거주지/집",
    "여가/취미",
    "음악 감상",
    "영화 보기",
    "공원 가기",
    "해변/바다",
    "국내 여행",
    "해외 여행",
    "쇼핑",
    "요리/음식",
    "건강/운동",
    "기술/인터넷",
    "직장/업무",
    "학교/교육",
    "날씨/계절",
    "교통수단",
    "뉴스/이슈",
    "재활용/환경",
    "호텔 예약",
    "식당 예약",
    "은행 업무",
]

OPIC_QUESTION_TYPES = [
    "자기소개 (Self-Introduction)",
    "묘사 (Description)",
    "습관/루틴 (Habit/Routine)",
    "과거 경험 (Past Experience)",
    "비교 (Comparison)",
    "돌발 질문 (Unexpected Question)",
    "롤플레이 (Role Play)",
    "콤보 세트 (Combo Set - 3연속 질문)",
]

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "opic.db")
LOG_DIR = os.path.join(os.path.dirname(__file__), "data", "logs")
