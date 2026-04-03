"""Question Generator Agent - Claude Code CLI로 OPIC AL급 문제 생성

이 Agent는 시스템에서 유일하게 LLM(Claude)을 호출하는 Agent입니다:
1. config의 QG 프롬프트 템플릿을 로드
2. {level}, {topic}, {question_type}을 치환하여 프롬프트 완성
3. `claude -p <프롬프트>` 명령어로 Claude Code CLI 호출 (subprocess)
4. 응답에서 JSON 추출 (question, sample_answer, key_expressions, tip)
5. DB에 저장하고 결과를 반환

프롬프트는 Dashboard Settings에서 수정 가능 (data/qg_prompt.txt)
"""

import json
import subprocess
import traceback
from config import OPIC_TARGET_LEVEL, load_qg_prompt
from db import save_question, log_agent


class QuestionGeneratorAgent:
    name = "QuestionGenerator"

    def __init__(self):
        # 현재 실행 중인 claude 프로세스 참조 (shutdown 시 kill 용)
        self._current_proc = None

    def kill_current(self):
        """실행 중인 claude 프로세스를 강제 종료.
        harness shutdown 시 호출되어 즉시 중단합니다.
        """
        if self._current_proc:
            try:
                self._current_proc.kill()
            except Exception:
                pass

    async def generate(self, topic: str, question_type: str, issue_number: int = None) -> dict:
        """OPIC 문제를 생성하여 DB에 저장하고 결과를 반환.

        Args:
            topic: OPIC 주제 (예: "해외 여행")
            question_type: 문제 유형 (예: "롤플레이 (Role Play)")
            issue_number: GitHub Issue 번호 (아카이브 기록용)

        Returns:
            dict: {id, topic, question_type, question, sample_answer, key_expressions, tip}
        """
        await log_agent(self.name, "generate", "started", f"{topic} / {question_type}")

        try:
            # 1. 프롬프트 생성 - 파일에서 템플릿 로드 후 변수 치환
            prompt = load_qg_prompt().format(
                level=OPIC_TARGET_LEVEL,  # "AL"
                topic=topic,
                question_type=question_type,
            )

            # 2. Claude Code CLI 호출 (subprocess)
            # claude -p "프롬프트" --output-format text
            proc = subprocess.Popen(
                ["claude", "-p", prompt, "--output-format", "text"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._current_proc = proc
            try:
                # 최대 120초 대기
                stdout, stderr = proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError("claude CLI timed out")
            finally:
                self._current_proc = None

            if proc.returncode != 0:
                raise RuntimeError(f"claude CLI error: {(stderr or '')[:500]}")

            response_text = stdout.strip()

            # 3. JSON 파싱 - Claude가 ```json 블록으로 감싸는 경우 처리
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())

            # key_expressions가 배열로 오면 쉼표 구분 문자열로 변환
            ke = data.get("key_expressions", "")
            if isinstance(ke, list):
                ke = ", ".join(str(item) for item in ke)
            data["key_expressions"] = ke

            # 4. DB에 저장
            question_id = await save_question(
                topic=topic,
                question_type=question_type,
                question_text=data["question"],
                sample_answer=data.get("sample_answer", ""),
                key_expressions=ke,
                tip=data.get("tip", ""),
                issue_number=issue_number,
            )

            # 5. 결과에 메타데이터 추가하여 반환
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
