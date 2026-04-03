"""OPIC Daily Agent Harness - 메인 실행 파일

Usage:
    python run.py                    # Harness + Dashboard 동시 실행 (5분 간격)
    python run.py --interval 60      # 60초 간격으로 파이프라인 반복
    python run.py --dashboard        # Dashboard만 실행
"""

import asyncio
import sys
import threading
import uvicorn

from config import DASHBOARD_PORT


def start_dashboard():
    """별도 스레드에서 Dashboard 실행"""
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=DASHBOARD_PORT,
        log_level="warning",
    )


def main():
    interval = 300  # 기본 5분

    if "--dashboard" in sys.argv:
        print(f"Dashboard only: http://localhost:{DASHBOARD_PORT}")
        uvicorn.run("dashboard.app:app", host="0.0.0.0", port=DASHBOARD_PORT, reload=True)
        return

    # --interval 파싱
    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            interval = int(sys.argv[idx + 1])

    # Dashboard를 별도 스레드에서 실행
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    print(f"Dashboard: http://localhost:{DASHBOARD_PORT}")

    # Harness 메인 루프 실행
    from harness_runner import run_harness
    asyncio.run(run_harness(interval))


if __name__ == "__main__":
    main()
