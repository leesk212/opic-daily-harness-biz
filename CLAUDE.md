# OPIC Daily Harness - Claude Code Context

OPIc AL급 영어 연습 문제를 자동 생성하고 KakaoTalk으로 전송하는 AI Agent Harness 시스템.

## 실행 방법

```bash
# 일반 실행 (sudo 필요 - macOS Accessibility 권한)
sudo .venv/bin/python run.py --run-now    # 즉시 1회 + 스케줄 모드
sudo .venv/bin/python run.py              # 스케줄만 (06/12/18/00시 KST)
sudo .venv/bin/python run.py --dashboard  # Dashboard만

# 외부 접속 (별도 터미널)
cloudflared tunnel --url http://localhost:8080
```

Dashboard: `http://localhost:8080` (Admin: `?admin` 파라미터)

## 아키텍처 핵심

**GitHub Issues가 메시지 큐 역할.** Agent 간 직접 호출 없음.

```
Orchestrator (스케줄 트리거 → Issue 생성)
    ↓ GitHub Issue #N
ContentManager (10초 polling → topic/type 선택 → Comment)
    ↓ Issue Comment
QuestionGenerator (15초 polling → Claude CLI로 문제 생성 → Comment)
    ↓ Issue Comment
Delivery (10초 polling → AppleScript로 KakaoTalk 전송 → Issue close)
```

1 Pipeline = 1 GitHub Issue. 각 Agent 결과 = Issue Comment (JSON payload).

## 파일 구조 & 역할

| 파일 | 역할 |
|------|------|
| `run.py` | 진입점. Dashboard(스레드) + Harness(스레드) + APScheduler 동시 실행 |
| `harness_runner.py` | 4개 Agent Worker를 asyncio로 실행. `AGENT_STATUS` 공유, `_trigger_q` 큐 |
| `harness.py` | GitHub Issues 통신 레이어. `gh` CLI 래퍼 (`GitHubHarness` 클래스) |
| `config.py` | 환경변수, OPIC 주제/유형, 수신자/주제 JSON 로드/저장 |
| `db.py` | SQLite (aiosqlite). questions/delivery_log/agent_log 3개 테이블. WAL 모드 |
| `tracing.py` | Langfuse 트레이싱. 파이프라인별 trace → span/generation/event/score |
| `agents/content_manager.py` | 주제/유형 선택 (최근 7일 중복 방지) |
| `agents/question_generator.py` | `claude -p <prompt>` subprocess 호출. timeout 120초 |
| `agents/delivery.py` | AppleScript(`scripts/kakao_send.scpt`)로 KakaoTalk 전송 |
| `dashboard/app.py` | FastAPI REST API. 15개 엔드포인트 |
| `dashboard/templates/index.html` | SPA 대시보드. 3초 polling, SVG 파이프라인 그래프 |
| `scripts/kakao_send.scpt` | AppleScript UI 자동화. row 번호로 고정된 채팅방 선택 |
| `data/kakao_recipients.json` | 수신자 목록 (name, self, row). 런타임 수정 가능 |
| `data/selected_topics.json` | 선택된 OPIC 주제 12개. 런타임 수정 가능 |
| `data/questions_archive.json` | 누적 문제 아카이브 (git 추적용) |

## KakaoTalk 전송 구조

kakaocli는 740개 채팅방 AX 순회로 hang 발생하여 **폐기**. AppleScript 직접 전송으로 교체.

```
delivery.py → subprocess: osascript kakao_send.scpt <row> <message>
```

- **row 번호** = 카카오톡 chatrooms 탭(checkbox 2)에서 **고정(Pin)된 채팅방 순서**
- 수신자 추가: 카카오톡에서 Pin → `data/kakao_recipients.json`에 row 추가 (재시작 불필요)
- 메시지는 2개로 분할 전송 (문제 + 답안), 사이 2초 대기
- 클립보드(Cmd+V)로 메시지 입력

## 자주 발생하는 이슈 & 해결

### DB "database is locked"
- 원인: 여러 Agent가 동시 SQLite 접근
- 해결: WAL 모드 + busy_timeout 30초 (db.py에 적용됨)

### root 경로 문제
- sudo로 실행 시 `~`가 `/var/root`로 풀림
- config.py에서 `expanduser` + fallback 경로 처리

### QG 데이터 파싱 실패
- 원인: `get_agent_data_from_comments()`에서 `replace("\\n", "\n")` 했었음
- 해결: replace 제거 (JSON 내부 이스케이프를 깨뜨림)

### KakaoTalk 전송 hang
- 원인: kakaocli가 AX API로 740개 행 순회
- 해결: AppleScript 직접 전송 + 채팅방 Pin 고정

### cloudflared
- `cloudflared tunnel --url http://localhost:8080`로 외부 접속
- trycloudflare 임시 URL (프로세스 재시작 시 변경)
- Harness만 재시작할 때 cloudflared PID는 유지

## API 엔드포인트

| Method | Path | 용도 |
|--------|------|------|
| GET | `/api/harness-status` | 실시간 Agent 상태 |
| GET | `/api/pipelines` | 파이프라인 목록 (GitHub Issues) |
| GET | `/api/pipelines/{n}` | 파이프라인 상세 (Comments) |
| GET | `/api/stats` | 통계 (문제 수, 전송 성공/실패, 분포) |
| GET | `/api/questions` | 생성된 문제 목록 |
| GET | `/api/delivery-logs` | 전송 이력 |
| GET | `/api/agent-logs` | Agent 활동 로그 |
| GET | `/api/schedule` | 다음 스케줄 |
| GET/PUT | `/api/recipients` | KakaoTalk 수신자 관리 |
| GET/PUT | `/api/topics` | OPIC 주제 선택 관리 |
| POST | `/api/trigger` | 수동 파이프라인 트리거 |
| POST | `/api/shutdown` | Agent 중지 (Dashboard 유지) |
| POST | `/api/restart` | Agent 재시작 |

## 의존성 흐름

```
run.py
├── harness_runner.py
│   ├── db.py ← config.py
│   ├── harness.py (gh CLI → GitHub API)
│   ├── tracing.py (→ Langfuse)
│   └── agents/
│       ├── content_manager.py ← db.py, config.py
│       ├── question_generator.py ← db.py, config.py (→ claude CLI)
│       └── delivery.py ← config.py, db.py (→ osascript)
└── dashboard/app.py ← db.py, harness.py, config.py
```

## 코드 수정 시 주의사항

- Agent 추가/수정 후 `harness_runner.py`의 worker 함수도 업데이트 필요
- GitHub Issue Comment의 JSON은 `get_agent_data_from_comments()`로 파싱됨. `Agent: \`{name}\`` 패턴 + "success" 문자열로 매칭
- `data/*.json` 파일은 런타임에 읽으므로 Harness 재시작 없이 반영됨
- `AGENT_STATUS` dict는 메모리 공유 (Dashboard에서 직접 import)
- QG의 `claude -p` 호출은 blocking subprocess. `kill_current()`로 강제 종료 가능
