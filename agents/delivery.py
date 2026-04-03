"""Delivery Agent - KakaoTalk으로 OPIC 문제 전송 (AppleScript UI 자동화)

전송 방식:
  1. question_data를 2개 메시지로 포맷팅 (문제 + 답안)
  2. 각 수신자(recipient)에 대해 AppleScript 호출
  3. AppleScript가 카카오톡 UI를 자동화하여 메시지 전송

수신자 설정: data/kakao_recipients.json
  - 각 수신자에 row 번호 필수 (카카오톡 chatrooms 탭의 Pin 순서)
  - Dashboard Settings에서 웹으로 관리 가능

주의: 카카오톡 앱이 실행 중이어야 하며, 대상 채팅방이 Pin 고정되어 있어야 합니다.
"""

import subprocess
import time
from config import KAKAO_SEND_SCRIPT, load_kakao_recipients
from db import save_delivery, log_agent


class DeliveryAgent:
    name = "Delivery"

    def _format_messages(self, question_data: dict) -> list:
        """문제 데이터를 카카오톡 메시지 2개로 포맷팅.

        메시지 1: 문제 + Key Expressions + Tip
        메시지 2: Sample Answer (스포일러 방지를 위해 분리)
        """
        q = question_data

        # 메시지 1: 문제 본문
        msg1 = "\n".join([
            "━━━━━━━━━━━━━━━━━━━━",
            "OPIC Daily Practice",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Topic: {q.get('topic', 'N/A')}",
            f"Type: {q.get('question_type', 'N/A')}",
            f"Level: AL",
            "",
            "──────────────────",
            "Question:",
            q.get('question', 'N/A'),
            "──────────────────",
            "",
            "Key Expressions:",
            q.get('key_expressions', 'N/A'),
            "",
            "Tip:",
            q.get('tip', ''),
        ])

        # 메시지 2: 모범 답안 (별도 전송)
        msg2 = "\n".join([
            "──────────────────",
            "Sample Answer:",
            "(먼저 직접 답해보세요!)",
            "",
            q.get('sample_answer', 'N/A'),
            "━━━━━━━━━━━━━━━━━━━━",
        ])

        return [msg1, msg2]

    def _send_kakaotalk(self, row: int, message: str) -> None:
        """AppleScript를 호출하여 카카오톡 메시지 전송.

        Args:
            row: 채팅방 Pin 순서 번호 (1부터 시작)
            message: 전송할 메시지 텍스트
        """
        result = subprocess.run(
            ["osascript", KAKAO_SEND_SCRIPT, str(row), message],
            capture_output=True,
            text=True,
            timeout=30,  # AppleScript는 빠르므로 30초면 충분
        )
        if result.returncode != 0:
            raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")

    async def send(self, question_data: dict) -> dict:
        """모든 수신자에게 문제를 전송하고 결과를 반환.

        Returns:
            dict: {
                "delivered": True/False (전체 성공 여부),
                "recipients": [{"recipient": "이름", "status": "success/failed", "error": "..."}]
            }
        """
        await log_agent(self.name, "send", "started", f"question_id={question_data.get('id')}")

        # 문제 데이터가 없으면 전송 스킵
        if not question_data.get('question') or question_data.get('question') == 'N/A':
            await log_agent(self.name, "send", "skipped", "no question data")
            return {"delivered": False, "recipients": [{"recipient": "all", "status": "skipped", "error": "no question data"}]}

        results = []
        all_ok = True

        # 각 수신자에게 순차적으로 전송
        for recipient in load_kakao_recipients():
            channel = f"kakaotalk:{recipient['name']}"
            row = recipient.get("row")

            # row 번호가 없으면 스킵
            if not row:
                results.append({"recipient": recipient["name"], "status": "skipped", "error": "no row number"})
                continue

            try:
                # 메시지 2개를 순차 전송 (문제 → 2초 대기 → 답안)
                messages = self._format_messages(question_data)
                for msg in messages:
                    self._send_kakaotalk(row, msg)
                    time.sleep(2)  # UI 자동화 안정성을 위한 대기

                # 성공 기록
                await save_delivery(
                    question_id=question_data.get("id"),
                    channel=channel,
                    status="success",
                )
                await log_agent(self.name, "send", "success", f"sent to {recipient['name']}")
                results.append({"recipient": recipient["name"], "status": "success"})

            except Exception as e:
                # 실패 기록 (다른 수신자는 계속 시도)
                all_ok = False
                await save_delivery(
                    question_id=question_data.get("id"),
                    channel=channel,
                    status="failed",
                    error_message=str(e),
                )
                await log_agent(self.name, "send", "failed", f"{recipient['name']}: {e}")
                results.append({"recipient": recipient["name"], "status": "failed", "error": str(e)})

        return {"delivered": all_ok, "recipients": results}
