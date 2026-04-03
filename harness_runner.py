"""Harness Runner - Agent들을 독립 워커로 상시 실행

각 Agent는 GitHub Issues를 감시하며 자기 차례가 오면 동작합니다.
Orchestrator가 주기적으로 파이프라인을 트리거하고,
나머지 Agent들은 Issue 댓글을 통해 상태를 주고받습���다.
"""

import asyncio
import json
import time
import signal
import sys
from datetime import datetime

from db import init_db, log_agent
from harness import GitHubHarness, ensure_labels, _gh, REPO
from agents.content_manager import ContentManagerAgent
from agents.question_generator import QuestionGeneratorAgent
from agents.delivery import DeliveryAgent

# 상태 공유 (Dashboard에서 조회용)
AGENT_STATUS = {
    "orchestrator": {"state": "idle", "last_run": None, "detail": ""},
    "content_manager": {"state": "idle", "last_run": None, "detail": ""},
    "question_generator": {"state": "idle", "last_run": None, "detail": ""},
    "delivery": {"state": "idle", "last_run": None, "detail": ""},
    "harness": {"state": "stopped", "started_at": None, "total_runs": 0, "loop_interval": 0},
}

harness = GitHubHarness()
shutdown_event = None  # run_harness()에서 초기화


def update_status(agent: str, state: str, detail: str = ""):
    AGENT_STATUS[agent]["state"] = state
    AGENT_STATUS[agent]["last_run"] = datetime.now().isoformat()
    AGENT_STATUS[agent]["detail"] = detail


def find_pending_issues():
    """Orchestrator가 생성했지만 아직 ContentManager가 처리하지 않은 Issue 찾기"""
    try:
        output = _gh([
            "issue", "list",
            "--repo", REPO,
            "--label", "pipeline,status:in-progress",
            "--state", "open",
            "--json", "number,title,comments,createdAt",
            "--limit", "5",
        ])
        issues = json.loads(output) if output else []
        return issues
    except Exception:
        return []


def issue_has_agent_comment(issue_number: int, agent_name: str) -> bool:
    """특정 Issue에 해당 Agent의 댓글이 있는지 확인"""
    try:
        detail = harness.get_issue_detail(issue_number)
        comments = detail.get("comments", [])
        for c in comments:
            body = c.get("body", "")
            if f"Agent: `{agent_name}`" in body and ("success" in body or "failed" in body):
                return True
        return False
    except Exception:
        return False


def get_agent_data_from_comments(issue_number: int, agent_name: str) -> dict:
    """Issue 댓글에서 특정 Agent의 성공 데이터 추출"""
    try:
        detail = harness.get_issue_detail(issue_number)
        for c in detail.get("comments", []):
            body = c.get("body", "")
            if f"Agent: `{agent_name}`" in body and "success" in body:
                # JSON payload 추출
                if "```json" in body:
                    json_str = body.split("```json")[1].split("```")[0].strip()
                    # HTML 엔티티 복원
                    json_str = json_str.replace("\\n", "\n")
                    return json.loads(json_str)
        return {}
    except Exception:
        return {}


# === Agent Workers ===

async def orchestrator_worker(interval_seconds: int):
    """Orchestrator: 주기적으로 새 파이프라인 Issue 생성"""
    while not shutdown_event.is_set():
        try:
            update_status("orchestrator", "running", "Creating new pipeline issue...")
            await log_agent("Orchestrator", "create_pipeline", "started")

            ensure_labels()
            issue_number = harness.create_pipeline_issue()
            harness.post_agent_status(
                issue_number, "Orchestrator", "pipeline_start", "started",
                {"message": "Pipeline initiated. Waiting for agents..."},
            )

            AGENT_STATUS["harness"]["total_runs"] += 1
            update_status("orchestrator", "waiting", f"Issue #{issue_number} created, waiting for agents")
            await log_agent("Orchestrator", "create_pipeline", "success", f"issue #{issue_number}")

        except Exception as e:
            update_status("orchestrator", "error", str(e))
            await log_agent("Orchestrator", "create_pipeline", "failed", str(e))

        # 다음 실행까지 대기
        update_status("orchestrator", "sleeping", f"Next run in {interval_seconds}s")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
            break  # shutdown
        except asyncio.TimeoutError:
            pass  # 정상 - 다음 루프


async def content_manager_worker(poll_seconds: int = 10):
    """ContentManager: 새 Issue를 감시하다가 주제/유형 선정"""
    agent = ContentManagerAgent()

    while not shutdown_event.is_set():
        try:
            update_status("content_manager", "polling", "Scanning for new pipeline issues...")
            issues = find_pending_issues()

            for issue in issues:
                issue_num = issue["number"]

                # 이미 처리했으면 스킵
                if issue_has_agent_comment(issue_num, "ContentManager"):
                    continue

                update_status("content_manager", "running", f"Processing Issue #{issue_num}")
                await log_agent("ContentManager", "pick_topic", "started", f"issue #{issue_num}")

                harness.post_agent_status(
                    issue_num, "ContentManager", "pick_topic_and_type", "started",
                )

                selection = await agent.pick_topic_and_type()

                harness.post_agent_status(
                    issue_num, "ContentManager", "pick_topic_and_type", "success",
                    selection,
                )
                update_status("content_manager", "done", f"Issue #{issue_num}: {selection['topic']}")
                await log_agent("ContentManager", "pick_topic", "success", str(selection))

        except Exception as e:
            update_status("content_manager", "error", str(e))
            await log_agent("ContentManager", "poll", "failed", str(e))

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_seconds)
            break
        except asyncio.TimeoutError:
            pass


async def question_generator_worker(poll_seconds: int = 15):
    """QuestionGenerator: ContentManager 완료를 감지하면 문제 생성"""
    agent = QuestionGeneratorAgent()

    while not shutdown_event.is_set():
        try:
            update_status("question_generator", "polling", "Waiting for ContentManager...")
            issues = find_pending_issues()

            for issue in issues:
                issue_num = issue["number"]

                # ContentManager가 완료했는지 확인
                if not issue_has_agent_comment(issue_num, "ContentManager"):
                    continue
                # 이미 처리했으면 스킵
                if issue_has_agent_comment(issue_num, "QuestionGenerator"):
                    continue

                update_status("question_generator", "running", f"Generating for Issue #{issue_num}")
                await log_agent("QuestionGenerator", "generate", "started", f"issue #{issue_num}")

                # ContentManager의 결과 가져오기
                selection = get_agent_data_from_comments(issue_num, "ContentManager")
                topic = selection.get("topic", "자기소개")
                q_type = selection.get("question_type", "묘사 (Description)")

                harness.post_agent_status(
                    issue_num, "QuestionGenerator", "generate", "started",
                    {"topic": topic, "type": q_type},
                )

                question_data = await agent.generate(topic=topic, question_type=q_type)

                harness_data = {
                    "question_id": question_data.get("id"),
                    "question": question_data.get("question", ""),
                    "key_expressions": question_data.get("key_expressions", ""),
                    "tip": question_data.get("tip", ""),
                }
                harness.post_agent_status(
                    issue_num, "QuestionGenerator", "generate", "success",
                    harness_data,
                )
                update_status("question_generator", "done", f"Issue #{issue_num}: question generated")
                await log_agent("QuestionGenerator", "generate", "success", f"issue #{issue_num}")

        except Exception as e:
            update_status("question_generator", "error", str(e))
            await log_agent("QuestionGenerator", "poll", "failed", str(e))

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_seconds)
            break
        except asyncio.TimeoutError:
            pass


async def delivery_worker(poll_seconds: int = 10):
    """Delivery: QuestionGenerator 완료를 감지하면 Slack 전송 + Issue close"""
    agent = DeliveryAgent()

    while not shutdown_event.is_set():
        try:
            update_status("delivery", "polling", "Waiting for QuestionGenerator...")
            issues = find_pending_issues()

            for issue in issues:
                issue_num = issue["number"]

                # QuestionGenerator가 완료했는지 확인
                if not issue_has_agent_comment(issue_num, "QuestionGenerator"):
                    continue
                # 이미 처리했으면 스킵
                if issue_has_agent_comment(issue_num, "Delivery"):
                    continue

                update_status("delivery", "running", f"Delivering Issue #{issue_num}")
                await log_agent("Delivery", "send", "started", f"issue #{issue_num}")

                # QuestionGenerator 결과 가져오기
                q_data = get_agent_data_from_comments(issue_num, "QuestionGenerator")
                # ContentManager 결과도 필요 (topic, question_type)
                cm_data = get_agent_data_from_comments(issue_num, "ContentManager")
                q_data["topic"] = cm_data.get("topic", "Unknown")
                q_data["question_type"] = cm_data.get("question_type", "Unknown")
                q_data["id"] = q_data.get("question_id")

                harness.post_agent_status(issue_num, "Delivery", "send", "started")

                delivered = await agent.send(q_data)

                harness.post_agent_status(
                    issue_num, "Delivery", "send",
                    "success" if delivered else "failed",
                    {"delivered": delivered},
                )

                # Pipeline 완료 → Issue close
                final_status = "success" if delivered else "failed"
                harness.post_agent_status(
                    issue_num, "Orchestrator", "pipeline_complete", final_status,
                    {"summary": f"Topic: {q_data['topic']}, Delivered: {delivered}"},
                )
                harness.close_pipeline_issue(issue_num, final_status)

                update_status("delivery", "done", f"Issue #{issue_num}: delivered={delivered}")
                await log_agent("Delivery", "send", "success" if delivered else "failed", f"issue #{issue_num}")

        except Exception as e:
            update_status("delivery", "error", str(e))
            await log_agent("Delivery", "poll", "failed", str(e))

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=poll_seconds)
            break
        except asyncio.TimeoutError:
            pass


async def run_harness(interval_seconds: int = 300):
    """모든 Agent 워커를 동시에 시작"""
    global shutdown_event
    shutdown_event = asyncio.Event()
    await init_db()

    AGENT_STATUS["harness"]["state"] = "running"
    AGENT_STATUS["harness"]["started_at"] = datetime.now().isoformat()
    AGENT_STATUS["harness"]["loop_interval"] = interval_seconds

    print(f"{'='*60}")
    print(f"  OPIC Daily Harness - RUNNING")
    print(f"  Pipeline interval: {interval_seconds}s")
    print(f"  Agents: Orchestrator, ContentManager, QuestionGenerator, Delivery")
    print(f"  GitHub: https://github.com/{REPO}/issues")
    print(f"{'='*60}")

    # 모든 Agent 워커를 동시 실행
    tasks = [
        asyncio.create_task(orchestrator_worker(interval_seconds)),
        asyncio.create_task(content_manager_worker(poll_seconds=10)),
        asyncio.create_task(question_generator_worker(poll_seconds=15)),
        asyncio.create_task(delivery_worker(poll_seconds=10)),
    ]

    # graceful shutdown
    def handle_signal(*_):
        print("\nShutting down harness...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    await asyncio.gather(*tasks)
    AGENT_STATUS["harness"]["state"] = "stopped"
    print("Harness stopped.")


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    asyncio.run(run_harness(interval))
