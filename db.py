"""데이터베이스 모듈 - SQLite 비동기 접근

3개의 테이블을 관리합니다:
  1. questions     - 생성된 OPIC 문제 저장
  2. delivery_log  - 카카오톡 전송 이력 (성공/실패)
  3. agent_log     - 모든 Agent의 활동 로그

주의사항:
  - WAL 모드 사용 (여러 Agent가 동시에 읽기/쓰기 가능)
  - busy_timeout 30초 (DB lock 시 즉시 에러 대신 대기)
  - 모든 시각은 KST (UTC+9)
"""

import aiosqlite
import json
import os
from datetime import datetime, timezone, timedelta
from config import DB_PATH

# 문제 아카이브 파일 경로 (git으로 추적되는 누적 기록)
ARCHIVE_PATH = os.path.join(os.path.dirname(__file__), "data", "questions_archive.json")

# 한국 표준시 (UTC+9)
KST = timezone(timedelta(hours=9))

# DB 연결 타임아웃 (초) - 여러 Agent가 동시 접근할 때 "database is locked" 방지
DB_TIMEOUT = 30


def _kst_now() -> str:
    """현재 KST 시각을 'YYYY-MM-DD HH:MM:SS' 형식으로 반환"""
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _connect():
    """타임아웃이 설정된 DB 연결 생성"""
    return aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT)


async def init_db():
    """DB 초기화 - 테이블 생성 및 WAL 모드 설정.
    앱 시작 시 1회 호출됩니다.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with _connect() as db:
        # WAL 모드: 읽기와 쓰기를 동시에 할 수 있게 해줌
        await db.execute("PRAGMA journal_mode=WAL")
        # busy_timeout: DB가 잠겨있을 때 30초까지 대기
        await db.execute("PRAGMA busy_timeout=30000")

        # 문제 테이블 - 생성된 OPIC 문제를 저장
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                question_type TEXT NOT NULL,
                question_text TEXT NOT NULL,
                sample_answer TEXT,
                key_expressions TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+9 hours'))
            )
        """)

        # 전송 이력 테이블 - 카카오톡 전송 결과를 기록
        await db.execute("""
            CREATE TABLE IF NOT EXISTS delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                channel TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                delivered_at TIMESTAMP DEFAULT (datetime('now', '+9 hours')),
                FOREIGN KEY (question_id) REFERENCES questions(id)
            )
        """)

        # Agent 활동 로그 테이블 - 모든 Agent의 동작을 기록
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+9 hours'))
            )
        """)
        await db.commit()


async def log_agent(agent_name: str, action: str, status: str, detail: str = ""):
    """Agent 활동을 로그 테이블에 기록.
    예: log_agent("Delivery", "send", "success", "sent to me")
    """
    async with _connect() as db:
        await db.execute(
            "INSERT INTO agent_log (agent_name, action, status, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (agent_name, action, status, detail, _kst_now()),
        )
        await db.commit()


async def save_question(topic, question_type, question_text, sample_answer="", key_expressions="", tip="", issue_number=None):
    """생성된 문제를 DB에 저장하고, JSON 아카이브에도 누적 기록.
    반환값: 새로 생성된 question_id
    """
    created_at = _kst_now()
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO questions (topic, question_type, question_text, sample_answer, key_expressions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (topic, question_type, question_text, sample_answer, key_expressions, created_at),
        )
        await db.commit()
        question_id = cursor.lastrowid

    # Git으로 추적되는 JSON 아카이브에도 저장 (누적)
    _append_to_archive({
        "id": question_id,
        "issue_number": issue_number,
        "topic": topic,
        "question_type": question_type,
        "question": question_text,
        "key_expressions": key_expressions,
        "tip": tip,
        "sample_answer": sample_answer,
        "created_at": created_at,
    })
    return question_id


def _append_to_archive(entry: dict):
    """질문을 git-tracked JSON 파일에 누적 저장.
    이 파일은 DB와 별도로, git 히스토리로 문제 이력을 추적할 수 있게 합니다.
    """
    archive = []
    if os.path.exists(ARCHIVE_PATH):
        try:
            with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
                archive = json.load(f)
        except (json.JSONDecodeError, IOError):
            archive = []
    archive.append(entry)
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


async def save_delivery(question_id, channel, status, error_message=""):
    """카카오톡 전송 결과를 delivery_log에 기록.
    channel 예: "kakaotalk:me", "kakaotalk:16추호성"
    """
    async with _connect() as db:
        await db.execute(
            "INSERT INTO delivery_log (question_id, channel, status, error_message, delivered_at) VALUES (?, ?, ?, ?, ?)",
            (question_id, channel, status, error_message, _kst_now()),
        )
        await db.commit()


async def get_recent_topics(days=7):
    """최근 N일간 출제된 주제/유형 조회 (중복 방지용)"""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT topic, question_type FROM questions WHERE created_at >= datetime('now', '+9 hours', ?)",
            (f"-{days} days",),
        )
        return await cursor.fetchall()


async def get_all_questions(limit=50):
    """최근 생성된 문제 목록 조회 (Dashboard용)"""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM questions ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return await cursor.fetchall()


async def get_delivery_logs(limit=50):
    """전송 이력 조회 (Dashboard용)"""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM delivery_log ORDER BY delivered_at DESC LIMIT ?", (limit,)
        )
        return await cursor.fetchall()


async def get_agent_logs(limit=100):
    """Agent 활동 로그 조회 (Dashboard용)"""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM agent_log ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return await cursor.fetchall()


async def get_stats():
    """Dashboard 통계용 데이터 조회.
    반환: 총 문제 수, 전송 성공/실패 수, 주제별/유형별 분포
    """
    async with _connect() as db:
        total_q = await db.execute_fetchall("SELECT COUNT(*) FROM questions")
        total_d = await db.execute_fetchall(
            "SELECT COUNT(*) FROM delivery_log WHERE status='success'"
        )
        total_f = await db.execute_fetchall(
            "SELECT COUNT(*) FROM delivery_log WHERE status='failed'"
        )
        topic_dist = await db.execute_fetchall(
            "SELECT topic, COUNT(*) as cnt FROM questions GROUP BY topic ORDER BY cnt DESC LIMIT 10"
        )
        type_dist = await db.execute_fetchall(
            "SELECT question_type, COUNT(*) as cnt FROM questions GROUP BY question_type ORDER BY cnt DESC"
        )
        return {
            "total_questions": total_q[0][0],
            "successful_deliveries": total_d[0][0],
            "failed_deliveries": total_f[0][0],
            "topic_distribution": [(r[0], r[1]) for r in topic_dist],
            "type_distribution": [(r[0], r[1]) for r in type_dist],
        }
