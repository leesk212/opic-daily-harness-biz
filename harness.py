"""GitHub Issues Harness - Agent 간 통신 레이어

이 모듈이 "Harness"의 핵심입니다.
Agent들은 서로 직접 호출하지 않고, GitHub Issues를 통해 소통합니다:

  - 1개의 파이프라인 실행 = 1개의 GitHub Issue
  - 각 Agent의 실행 결과 = 해당 Issue의 Comment (JSON 데이터 포함)
  - Issue 라벨로 상태 관리 (in-progress → success/failed)

이 구조 덕분에:
  1. Agent를 독립적으로 교체/수정 가능
  2. 실행 이력이 GitHub에 자동 기록
  3. 하나의 Agent가 실패해도 다른 Agent에 영향 없음

모든 GitHub API 호출은 `gh` CLI를 통해 이루어집니다.
"""

import json
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

KST = timezone(timedelta(hours=9))

# GitHub 레포지토리 (Issue가 생성되는 곳)
REPO = "leesk212/opic-daily-harness"

# GitHub Issue에 사용하는 라벨들
LABELS = {
    "orchestrator": "agent:orchestrator",
    "content_manager": "agent:content-manager",
    "question_generator": "agent:question-generator",
    "delivery": "agent:delivery",
    "pipeline": "pipeline",
    "success": "status:success",
    "failed": "status:failed",
    "in_progress": "status:in-progress",
}


def _gh(args: List[str], input_text: Optional[str] = None) -> str:
    """GitHub CLI(gh) 명령어 실행 래퍼.
    `gh issue create`, `gh issue comment` 등의 명령어를 subprocess로 실행합니다.
    """
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed: {result.stderr}")
    return result.stdout.strip()


def ensure_labels():
    """GitHub 레포에 필요한 라벨이 없으면 자동 생성.
    최초 실행 시 또는 새 레포에서 라벨을 초기화할 때 사용.
    """
    existing = _gh(["label", "list", "--repo", REPO, "--json", "name", "-q", ".[].name"])
    existing_labels = set(existing.split("\n")) if existing else set()

    # 라벨별 색상 코드 (GitHub 라벨 색상)
    label_colors = {
        "agent:orchestrator": "5319E7",       # 보라색
        "agent:content-manager": "0E8A16",    # 초록색
        "agent:question-generator": "1D76DB", # 파란색
        "agent:delivery": "D93F0B",           # 빨간색
        "pipeline": "FBCA04",                 # 노란색
        "status:success": "0E8A16",           # 초록색
        "status:failed": "B60205",            # 빨간색
        "status:in-progress": "FEF2C0",       # 연노란색
    }

    for label, color in label_colors.items():
        if label not in existing_labels:
            try:
                _gh(["label", "create", label, "--repo", REPO, "--color", color, "--force"])
            except RuntimeError:
                pass  # 이미 존재하는 경우 무시


class GitHubHarness:
    """GitHub Issues를 메시지 큐처럼 사용하는 Harness 클래스.

    주요 기능:
    - Issue 생성 (파이프라인 시작)
    - Comment 작성 (Agent 결과 기록)
    - Issue 닫기 (파이프라인 완료)
    - Issue/Comment 조회 (Agent가 이전 Agent의 결과를 확인)
    """

    def __init__(self):
        self.repo = REPO

    def create_pipeline_issue(self) -> int:
        """새 파이프라인 실행용 Issue를 생성하고 Issue 번호를 반환.

        생성되는 Issue 예시:
          제목: [Pipeline] OPIC Daily - 2026-04-03 15:07 KST
          라벨: pipeline, agent:orchestrator, status:in-progress
        """
        today = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        title = f"[Pipeline] OPIC Daily - {today} KST"
        body = json.dumps({
            "type": "pipeline_start",
            "agent": "orchestrator",
            "timestamp": today,
            "status": "in_progress",
        }, ensure_ascii=False, indent=2)

        output = _gh([
            "issue", "create",
            "--repo", self.repo,
            "--title", title,
            "--body", body,
            "--label", f"{LABELS['pipeline']},{LABELS['orchestrator']},{LABELS['in_progress']}",
        ])
        # 응답 예: "https://github.com/leesk212/opic-daily-harness/issues/42"
        issue_number = int(output.rstrip("/").split("/")[-1])
        return issue_number

    def post_agent_status(self, issue_number: int, agent_name: str, action: str, status: str, data: Optional[Dict] = None):
        """Agent 실행 결과를 Issue Comment(댓글)로 기록.

        댓글 형식:
          ## 🎯 ✅ Agent: `Orchestrator` — pipeline_start
          **Label:** `agent:orchestrator` | **Status:** `success` | **Time:** `2026-04-03 15:07:44 KST`
          ### Payload
          ```json
          { ... }
          ```

        다른 Agent는 이 댓글의 JSON을 파싱하여 이전 Agent의 결과를 가져옵니다.
        """
        timestamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

        # Agent별 이모지 (Dashboard와 GitHub에서 시각적으로 구분)
        agent_emoji = {
            "Orchestrator": "\U0001f3af",       # 🎯
            "ContentManager": "\U0001f4cb",     # 📋
            "QuestionGenerator": "\U0001f916",  # 🤖
            "Delivery": "\U0001f4e8",           # 📨
        }.get(agent_name, "\u2139\ufe0f")

        # Agent별 GitHub 라벨
        agent_label = {
            "Orchestrator": "agent:orchestrator",
            "ContentManager": "agent:content-manager",
            "QuestionGenerator": "agent:question-generator",
            "Delivery": "agent:delivery",
        }.get(agent_name, "")

        # 상태별 이모지 (✅ 성공, ❌ 실패, 🔄 시작)
        status_emoji = {
            "success": "\u2705",
            "failed": "\u274c",
            "started": "\U0001f504",
            "in_progress": "\u23f3",
        }.get(status, "\u2139\ufe0f")

        # 마크다운 댓글 본문 생성
        body_lines = [
            f"## {agent_emoji} {status_emoji} Agent: `{agent_name}` — {action}",
            f"**Label:** `{agent_label}` | **Status:** `{status}` | **Time:** `{timestamp}`",
            "",
        ]

        # JSON 데이터가 있으면 코드 블록으로 추가
        if data:
            body_lines.append("### Payload")
            body_lines.append("```json")
            body_lines.append(json.dumps(data, ensure_ascii=False, indent=2))
            body_lines.append("```")

        body = "\n".join(body_lines)

        _gh([
            "issue", "comment",
            "--repo", self.repo,
            str(issue_number),
            "--body", body,
        ])

    def close_pipeline_issue(self, issue_number: int, status: str):
        """파이프라인 완료 시 Issue를 닫고 최종 라벨을 업데이트.

        - in-progress 라벨 제거
        - success 또는 failed 라벨 추가
        - Issue 닫기 (성공이면 completed, 실패면 not planned)
        """
        label = LABELS.get(status, LABELS["success"])

        # in-progress 라벨 제거
        try:
            _gh(["issue", "edit", "--repo", self.repo, str(issue_number),
                 "--remove-label", LABELS["in_progress"]])
        except RuntimeError:
            pass

        # 최종 상태 라벨 추가
        _gh(["issue", "edit", "--repo", self.repo, str(issue_number),
             "--add-label", label])

        # Issue 닫기
        state_reason = "completed" if status == "success" else "not planned"
        _gh(["issue", "close", "--repo", self.repo, str(issue_number),
             "--reason", state_reason])

    def get_pipeline_issues(self, state: str = "all", limit: int = 20) -> List[Dict]:
        """파이프라인 Issue 목록 조회 (Dashboard용)"""
        output = _gh([
            "issue", "list",
            "--repo", self.repo,
            "--label", LABELS["pipeline"],
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,labels,createdAt,closedAt,comments",
        ])
        return json.loads(output) if output else []

    def get_issue_comments(self, issue_number: int) -> List[Dict]:
        """특정 Issue의 모든 댓글 조회"""
        output = _gh([
            "issue", "view",
            "--repo", self.repo,
            str(issue_number),
            "--json", "comments",
        ])
        data = json.loads(output) if output else {}
        return data.get("comments", [])

    def get_issue_detail(self, issue_number: int) -> dict:
        """Issue 상세 정보 조회 (제목, 본문, 라벨, 댓글 전부)"""
        output = _gh([
            "issue", "view",
            "--repo", self.repo,
            str(issue_number),
            "--json", "number,title,state,body,labels,createdAt,closedAt,comments",
        ])
        return json.loads(output) if output else {}
