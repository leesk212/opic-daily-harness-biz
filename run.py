"""OPIC Daily Agent Harness - 메인 실행 파일

이 파일은 전체 시스템의 진입점(entry point)입니다.
3개의 컴포넌트를 동시에 실행합니다:
  1. Dashboard (FastAPI 웹서버) - 별도 스레드
  2. Harness (4개 Agent Worker) - 별도 스레드
  3. Scheduler (APScheduler) - 백그라운드

Usage:
    python run.py                    # 전체 실행 (Harness + Dashboard + Scheduler)
    python run.py --dashboard        # Dashboard만 실행 (개발/디버깅용)
    python run.py --run-now          # 즉시 1회 파이프라인 실행 + 스케줄 모드

Schedule: 06:00, 12:00, 18:00, 00:00 KST
Manual trigger: Dashboard에서 "Run Now" 버튼 또는 POST /api/trigger
"""

import asyncio
import sys
import threading
import time
import uvicorn

from config import DASHBOARD_PORT, SCHEDULE_HOURS


def start_dashboard():
    """Dashboard 웹서버를 별도 스레드에서 실행.
    FastAPI 앱을 uvicorn으로 구동합니다.
    """
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        log_level="warning",
    )


def start_scheduler():
    """APScheduler로 KST 기준 정해진 시각에 파이프라인을 자동 트리거.

    SCHEDULE_HOURS에 설정된 시각(기본 6,12,18,0)마다
    harness_runner의 trigger_pipeline()을 호출하여
    새 파이프라인(GitHub Issue)을 생성합니다.
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from datetime import timezone, timedelta

    KST = timezone(timedelta(hours=9))

    def _trigger():
        from harness_runner import trigger_pipeline
        trigger_pipeline()

    scheduler = BackgroundScheduler()
    # SCHEDULE_HOURS를 쉼표로 연결하여 cron 표현식으로 변환
    # 예: [6,12,18,0] → "6,12,18,0" → 매일 6시, 12시, 18시, 0시에 실행
    hours_csv = ",".join(str(h) for h in SCHEDULE_HOURS)
    scheduler.add_job(
        _trigger,
        CronTrigger(hour=hours_csv, minute=0, timezone=KST),
        id="opic_daily_pipeline",
        name=f"OPIC Pipeline @ {hours_csv}:00 KST",
        replace_existing=True,
    )
    scheduler.start()
    print(f"  Scheduler: Pipeline at {hours_csv}:00 KST")
    return scheduler


def run_harness_in_thread():
    """Harness(4개 Agent Worker)를 별도 스레드에서 실행.
    asyncio.run()으로 harness_runner의 메인 루프를 구동합니다.
    스레드가 종료되어도 메인 프로세스(Dashboard+Scheduler)는 유지됩니다.
    """
    from harness_runner import run_harness
    try:
        asyncio.run(run_harness())
    except Exception as e:
        print(f"  Harness stopped: {e}")
    print("  Harness thread exited.")


# 글로벌 harness 스레드 참조 (Dashboard에서 재시작할 때 사용)
_harness_thread = None


def start_harness():
    """Harness 스레드 시작. 이미 실행 중이면 False 반환."""
    global _harness_thread
    if _harness_thread and _harness_thread.is_alive():
        return False  # 이미 실행 중
    _harness_thread = threading.Thread(target=run_harness_in_thread, daemon=True)
    _harness_thread.start()
    return True


def is_harness_alive():
    """Harness 스레드가 살아있는지 확인"""
    return _harness_thread is not None and _harness_thread.is_alive()


def main():
    # --dashboard 모드: Dashboard만 실행 (Agent 없이)
    if "--dashboard" in sys.argv:
        print(f"Dashboard only: http://localhost:{DASHBOARD_PORT}")
        uvicorn.run("dashboard.app:app", host="0.0.0.0", port=DASHBOARD_PORT, reload=True)
        return

    run_now = "--run-now" in sys.argv

    # 1. Dashboard 시작 (별도 스레드 - daemon이라 메인 종료 시 같이 종료)
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    print(f"  Dashboard: http://localhost:{DASHBOARD_PORT}")

    # 2. Harness 시작 (별도 스레드 - 4개 Agent Worker가 asyncio로 동시 실행)
    start_harness()
    time.sleep(1)  # Harness 초기화 대기

    # 3. Scheduler 시작 (백그라운드 - 설정된 시각에 자동 트리거)
    scheduler = start_scheduler()

    # --run-now: 즉시 1회 파이프라인 트리거
    if run_now:
        time.sleep(1)
        from harness_runner import trigger_pipeline
        trigger_pipeline()
        print("  Immediate trigger queued.")

    # 메인 스레드: Ctrl+C 대기 (Dashboard + Scheduler는 계속 동작)
    print(f"\n  Running. Press Ctrl+C to exit completely.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down everything...")
        from harness_runner import shutdown_harness
        shutdown_harness()
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
