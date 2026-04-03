"""Question Generator Agent - Claude Code CLI로 OPIC AL급 문제 생성"""

import json
import subprocess
import traceback
from config import OPIC_TARGET_LEVEL
from db import save_question, log_agent

PROMPT_TEMPLATE = """당신은 OPIC {level} 등급 전문 출제위원입니다.

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

    async def generate(self, topic: str, question_type: str) -> dict:
        await log_agent(self.name, "generate", "started", f"{topic} / {question_type}")

        try:
            prompt = PROMPT_TEMPLATE.format(
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
