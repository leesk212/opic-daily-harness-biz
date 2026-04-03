"""설정 관리 모듈

이 파일은 시스템의 모든 설정값을 관리합니다:
- 환경 변수 (.env 파일에서 로드)
- 파일 경로 (스크립트, 데이터, DB)
- OPIC 주제/유형 목록
- JSON 파일 기반 런타임 설정 (수신자, 주제 선택, QG 프롬프트)

JSON 설정 파일들은 Dashboard에서 웹으로 수정 가능하며,
수정 즉시 다음 파이프라인부터 반영됩니다 (재시작 불필요).
"""

import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일에서 환경 변수 로드

# ============================================================
# 경로 설정
# ============================================================

# 카카오톡 전송용 AppleScript 경로
KAKAO_SEND_SCRIPT = os.path.join(os.path.dirname(__file__), "scripts", "kakao_send.scpt")

# 런타임 설정 JSON 파일 경로들
KAKAO_RECIPIENTS_PATH = os.path.join(os.path.dirname(__file__), "data", "kakao_recipients.json")
SELECTED_TOPICS_PATH = os.path.join(os.path.dirname(__file__), "data", "selected_topics.json")
QG_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "data", "qg_prompt.txt")

# DB 및 로그 경로
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "opic.db")
LOG_DIR = os.path.join(os.path.dirname(__file__), "data", "logs")

# ============================================================
# 카카오톡 수신자 관리
# ============================================================
# 각 수신자는 {name, self, row} 형태
# - name: 채팅방 이름 (표시용)
# - self: 나와의 채팅 여부
# - row: 카카오톡 chatrooms 탭에서 고정(Pin)된 순서 번호

_DEFAULT_RECIPIENTS = [
    {"name": "me", "self": True, "row": 1},
    {"name": "16추호성", "self": False, "row": 2},
]

def load_kakao_recipients():
    """JSON 파일에서 수신자 목록을 로드. 파일 없으면 기본값 생성."""
    import json
    try:
        with open(KAKAO_RECIPIENTS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_kakao_recipients(_DEFAULT_RECIPIENTS)
        return _DEFAULT_RECIPIENTS

def save_kakao_recipients(recipients):
    """수신자 목록을 JSON 파일에 저장."""
    import json
    os.makedirs(os.path.dirname(KAKAO_RECIPIENTS_PATH), exist_ok=True)
    with open(KAKAO_RECIPIENTS_PATH, "w") as f:
        json.dump(recipients, f, ensure_ascii=False, indent=2)

# ============================================================
# OPIC 주제 선택 관리
# ============================================================
# 전체 22개 주제 중 사용자가 12개를 선택하여 사용

_DEFAULT_SELECTED_TOPICS = [
    "자기소개", "거주지/집", "여가/취미", "음악 감상", "영화 보기", "공원 가기",
    "해변/바다", "국내 여행", "해외 여행", "쇼핑", "요리/음식", "건강/운동",
]

def load_selected_topics():
    """선택된 주제 목록 로드. 파일 없으면 기본 12개 생성."""
    import json
    try:
        with open(SELECTED_TOPICS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_selected_topics(_DEFAULT_SELECTED_TOPICS)
        return _DEFAULT_SELECTED_TOPICS

def save_selected_topics(topics):
    """선택된 주제 목록을 JSON 파일에 저장."""
    import json
    os.makedirs(os.path.dirname(SELECTED_TOPICS_PATH), exist_ok=True)
    with open(SELECTED_TOPICS_PATH, "w") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

# ============================================================
# QuestionGenerator 프롬프트 관리
# ============================================================
# {level}, {topic}, {question_type} 플레이스홀더가 런타임에 치환됨

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
    """QG 프롬프트 텍스트 파일 로드. 없으면 기본 프롬프트 생성."""
    try:
        with open(QG_PROMPT_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        save_qg_prompt(_DEFAULT_QG_PROMPT)
        return _DEFAULT_QG_PROMPT

def save_qg_prompt(prompt):
    """QG 프롬프트를 텍스트 파일에 저장."""
    os.makedirs(os.path.dirname(QG_PROMPT_PATH), exist_ok=True)
    with open(QG_PROMPT_PATH, "w") as f:
        f.write(prompt)

# ============================================================
# 환경 변수 기반 설정
# ============================================================

# 파이프라인 스케줄 시간 (KST 기준, 기본: 6시, 12시, 18시, 0시)
SCHEDULE_HOURS = [int(h.strip()) for h in os.getenv("SCHEDULE_HOURS", "6,12,18,0").split(",")]

# Dashboard 웹서버 포트 (기본: 8080)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# ============================================================
# OPIC 시험 설정
# ============================================================

# 목표 등급 (AL = Advanced Low)
OPIC_TARGET_LEVEL = "AL"

# 전체 OPIC 주제 22개 (이 중 12개를 사용자가 선택)
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

# OPIC 문제 유형 8가지
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
