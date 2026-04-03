"""Langfuse 트레이싱 모듈 - 파이프라인 관측성(Observability)

Langfuse는 LLM 애플리케이션 모니터링 서비스입니다.
각 파이프라인 실행을 trace로 기록하여:
  - Agent별 실행 시간 측정 (span)
  - LLM 호출 추적 (generation)
  - 성공/실패 점수 기록 (score)
  - 이벤트 로깅 (event)

Langfuse 대시보드: https://cloud.langfuse.com
환경 변수: LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_BASE_URL
"""

import os
from langfuse import Langfuse
from langfuse.types import TraceContext
from dotenv import load_dotenv

load_dotenv()

# Langfuse 클라이언트 초기화 (.env에서 키 로드)
langfuse = Langfuse(
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
)


def create_pipeline_trace(issue_number):
    """새 파이프라인의 trace 생성.
    하나의 GitHub Issue = 하나의 trace.
    반환: trace_id (이후 span/event에서 사용)
    """
    trace_id = langfuse.create_trace_id()
    ctx = TraceContext(trace_id=trace_id)
    langfuse.create_event(
        trace_context=ctx,
        name="pipeline_start",
        metadata={"issue_number": issue_number},
    )
    return trace_id


def _ctx(trace_id):
    """trace_id를 TraceContext 객체로 변환 (내부 헬퍼)"""
    return TraceContext(trace_id=trace_id)


def start_span(trace_id, name, input_data=None, metadata=None):
    """Agent 작업 구간(span) 시작.
    예: start_span(trace_id, "content_manager.pick_topic", {...})
    반환된 span 객체의 .end()를 호출하면 구간이 종료됩니다.
    """
    return langfuse.start_span(
        trace_context=_ctx(trace_id),
        name=name,
        input=input_data,
        metadata=metadata or {},
    )


def start_generation(trace_id, name, model, input_data, metadata=None):
    """LLM 호출 구간 시작 (QuestionGenerator의 Claude CLI 호출용).
    generation은 span과 비슷하지만 모델명, 토큰 수 등 LLM 메타데이터를 추가로 기록합니다.
    """
    return langfuse.start_generation(
        trace_context=_ctx(trace_id),
        name=name,
        model=model,
        input=input_data,
        metadata=metadata or {},
    )


def log_event(trace_id, name, input_data=None, output_data=None, metadata=None):
    """단일 이벤트 기록 (구간 없이 한 시점의 데이터를 로깅).
    예: 파이프라인 완료 시 최종 결과 기록
    """
    langfuse.create_event(
        trace_context=_ctx(trace_id),
        name=name,
        input=input_data,
        output=output_data,
        metadata=metadata or {},
    )


def score_trace(trace_id, name, value, comment=""):
    """파이프라인에 점수 부여.
    예: score_trace(trace_id, "pipeline_success", 1.0, "Topic: 해외 여행")
    Langfuse 대시보드에서 성공률 등을 시각화할 수 있습니다.
    """
    langfuse.create_score(
        trace_id=trace_id,
        name=name,
        value=value,
        comment=comment,
    )


def flush():
    """버퍼에 쌓인 트레이싱 데이터를 Langfuse 서버로 즉시 전송"""
    langfuse.flush()
