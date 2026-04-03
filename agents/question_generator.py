"""Question Generator Agent - Claude Code CLI로 OPIC AL급 문제 생성"""

import json
import subprocess
import traceback
from config import OPIC_TARGET_LEVEL, load_qg_prompt
from db import save_question, log_agent


class QuestionGeneratorAgent:
    name = "QuestionGenerator"

    def __init__(self):
        self._current_proc = None

    def kill_current(self):
        """실행 중인 claude 프로세스 강제 종료"""
        if self._current_proc:
            try:
                self._current_proc.kill()
            except Exception:
                pass

    async def generate(self, topic: str, question_type: str, issue_number: int = None) -> dict:
        await log_agent(self.name, "generate", "started", f"{topic} / {question_type}")

        try:
            prompt = load_qg_prompt().format(
                level=OPIC_TARGET_LEVEL,
                topic=topic,
                question_type=question_type,
            )

            proc = subprocess.Popen(
                ["claude", "-p", prompt, "--output-format", "text"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._current_proc = proc
            try:
                stdout, stderr = proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError("claude CLI timed out")
            finally:
                self._current_proc = None

            if proc.returncode != 0:
                raise RuntimeError(f"claude CLI error: {(stderr or '')[:500]}")

            response_text = stdout.strip()

            # JSON 파싱
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())

            # key_expressions가 배열이면 문자열로 변환
            ke = data.get("key_expressions", "")
            if isinstance(ke, list):
                ke = ", ".join(str(item) for item in ke)
            data["key_expressions"] = ke

            question_id = await save_question(
                topic=topic,
                question_type=question_type,
                question_text=data["question"],
                sample_answer=data.get("sample_answer", ""),
                key_expressions=ke,
                tip=data.get("tip", ""),
                issue_number=issue_number,
            )

            data["id"] = question_id
            data["topic"] = topic
            data["question_type"] = question_type

            await log_agent(self.name, "generate", "success", f"question_id={question_id}")
            return data

        except Exception as e:
            tb = traceback.format_exc()
            error_detail = f"{str(e)}\n{tb}"
            try:
                await log_agent(self.name, "generate", "failed", error_detail[:1000])
            except Exception:
                pass  # DB lock 등 2차 에러 무시
            raise
