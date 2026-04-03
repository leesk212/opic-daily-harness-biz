"""Question Generator Agent - Claude API로 OPIC AL급 문제 생성"""

import json
import anthropic
from config import ANTHROPIC_API_KEY, OPIC_TARGET_LEVEL
from db import save_question, log_agent

SYSTEM_PROMPT = f"""당신은 OPIC {OPIC_TARGET_LEVEL} 등급 전문 출제위원입니다.

규칙:
1. 모든 문제는 영어로 출제합니다 (실제 OPIC 시험과 동일).
2. {OPIC_TARGET_LEVEL} 등급에 맞는 난이도로 출제합니다.
3. 자연스럽고 실제 시험에 나올 법한 문제를 만듭니다.
4. 콤보 세트의 경우 3개의 연관 질문을 만듭니다.
5. 롤플레이의 경우 구체적인 상황을 설정합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{{
    "question": "영어 질문 전문",
    "sample_answer": "AL등급 수준의 모범 답변 (영어, 200단어 이상)",
    "key_expressions": "답변에 활용하면 좋은 핵심 표현 5개 (쉼표 구분)",
    "tip": "이 문제를 잘 답하기 위한 전략 팁 (한국어)"
}}
"""


class QuestionGeneratorAgent:
    name = "QuestionGenerator"

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    async def generate(self, topic: str, question_type: str) -> dict:
        await log_agent(self.name, "generate", "started", f"{topic} / {question_type}")

        try:
            user_prompt = f"주제: {topic}\n문제 유형: {question_type}\n\n위 조건에 맞는 OPIC 문제를 1개 생성해주세요."

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            response_text = message.content[0].text

            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())

            question_id = await save_question(
                topic=topic,
                question_type=question_type,
                question_text=data["question"],
                sample_answer=data.get("sample_answer", ""),
                key_expressions=data.get("key_expressions", ""),
            )

            data["id"] = question_id
            data["topic"] = topic
            data["question_type"] = question_type

            await log_agent(self.name, "generate", "success", f"question_id={question_id}")
            return data

        except Exception as e:
            await log_agent(self.name, "generate", "failed", str(e))
            raise
