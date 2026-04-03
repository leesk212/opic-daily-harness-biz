"""Content Manager Agent - 주제/유형 선택 및 중복 방지

이 Agent는 LLM을 사용하지 않고 규칙 기반으로 동작합니다:
1. 사용자가 선택한 12개 주제에서 선택
2. 최근 7일간 출제된 주제는 피함 (중복 방지)
3. 문제 유형은 가장 적게 나온 유형을 우선 선택 (균형 유지)
4. 선택 결과를 GitHub Issue Comment에 JSON으로 기록
"""

import random
from db import get_recent_topics, log_agent
from config import OPIC_TOPICS, OPIC_QUESTION_TYPES, load_selected_topics


class ContentManagerAgent:
    name = "ContentManager"

    async def pick_topic_and_type(self) -> dict:
        """주제와 문제 유형을 선택하여 반환.
        반환값 예: {"topic": "해외 여행", "question_type": "롤플레이 (Role Play)"}
        """
        await log_agent(self.name, "pick_topic_and_type", "started")

        try:
            # 최근 7일간 출제된 주제/유형 조회
            recent = await get_recent_topics(days=7)
            recent_topics = [r["topic"] for r in recent]
            recent_types = [r["question_type"] for r in recent]

            # 사용자가 Dashboard에서 선택한 12개 주제만 사용
            selected = load_selected_topics()

            # 최근 7일간 안 나온 주제를 우선 선택 (중복 방지)
            available_topics = [t for t in selected if t not in recent_topics]
            if not available_topics:
                # 전부 최근에 나왔으면 전체에서 선택
                available_topics = selected

            # 가장 적게 출제된 문제 유형을 우선 선택 (균형 유지)
            type_counts = {}
            for qt in OPIC_QUESTION_TYPES:
                type_counts[qt] = recent_types.count(qt)
            min_count = min(type_counts.values()) if type_counts else 0
            available_types = [t for t, c in type_counts.items() if c == min_count]

            # 랜덤 선택
            topic = random.choice(available_topics)
            question_type = random.choice(available_types)

            result = {"topic": topic, "question_type": question_type}
            await log_agent(self.name, "pick_topic_and_type", "success", str(result))
            return result

        except Exception as e:
            # 에러 발생 시 완전 랜덤으로 폴백
            await log_agent(self.name, "pick_topic_and_type", "failed", str(e))
            return {
                "topic": random.choice(load_selected_topics()),
                "question_type": random.choice(OPIC_QUESTION_TYPES),
            }
