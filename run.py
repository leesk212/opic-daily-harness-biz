"""OPIC Daily Agent - 메인 실행 파일

Usage:
    python run.py              # Dashboard + 스케줄러 함께 실행
    python run.py --once       # 즉시 1회 실행 (테스트용)
    python run.py --dashboard  # Dashboard만 실행
"""

import asyncio
import sys
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import DAILY_SEND_HOUR, DAILY_SEND_MINUTE, DASHBOARD_PORT
from db import init_db
from agents.orchestrator import OrchestratorAgent


async def run_once():
    """파이프라인 1회 실행 (테스트용)"""
    await init_db()
    orchestrator = OrchestratorAgent()
    result = await orchestrator.run_pipeline()
    print(f"\n{'='*50}")
    print(f"Status: {result['status']}")
    if "steps" in result:
        steps = result["steps"]
        if "content_selection" in steps:
            sel = steps["content_selection"]
            print(f"Topic: {sel['topic']}")
            print(f"Type: {sel['question_type']}")
        if "question" in steps:
            q = steps["question"]
            print(f"\nQuestion: {q.get('question', 'N/A')}")
            print(f"Key Expressions: {q.get('key_expressions', 'N/A')}")
        if "delivery" in steps:
            print(f"Delivered: {steps['delivery']['success']}")
    if "error" in result:
        print(f"Error: {result['error']}")
    print(f"{'='*50}")


def run_dashboard_with_scheduler():
    """Dashboard + 스케줄러 함께 실행"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_once,
        CronTrigger(hour=DAILY_SEND_HOUR, minute=DAILY_SEND_MINUTE),
        id="daily_opic",
        name="Daily OPIC Question",
    )
    scheduler.start()
    print(f"Scheduler started: daily at {DAILY_SEND_HOUR:02d}:{DAILY_SEND_MINUTE:02d}")
    print(f"Dashboard: http://localhost:{DASHBOARD_PORT}")

    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        reload=False,
    )


def run_dashboard_only():
    """Dashboard만 실행"""
    print(f"Dashboard: http://localhost:{DASHBOARD_PORT}")
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        reload=True,
    )


if __name__ == "__main__":
    if "--once" in sys.argv:
        asyncio.run(run_once())
    elif "--dashboard" in sys.argv:
        run_dashboard_only()
    else:
        run_dashboard_with_scheduler()
