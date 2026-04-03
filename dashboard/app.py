"""Dashboard - FastAPI 웹 서버 (GitHub Issues Harness 연동)"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import init_db, get_all_questions, get_delivery_logs, get_agent_logs, get_stats
from harness import GitHubHarness
from agents.orchestrator import OrchestratorAgent

app = FastAPI(title="OPIC Agent Dashboard")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
harness = GitHubHarness()


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stats")
async def api_stats():
    return await get_stats()


@app.get("/api/questions")
async def api_questions():
    rows = await get_all_questions(limit=50)
    return [dict(r) for r in rows]


@app.get("/api/delivery-logs")
async def api_delivery_logs():
    rows = await get_delivery_logs(limit=50)
    return [dict(r) for r in rows]


@app.get("/api/agent-logs")
async def api_agent_logs():
    rows = await get_agent_logs(limit=100)
    return [dict(r) for r in rows]


@app.get("/api/pipelines")
async def api_pipelines():
    """GitHub Issues 기반 파이프라인 목록"""
    return harness.get_pipeline_issues(state="all", limit=20)


@app.get("/api/pipelines/{issue_number}")
async def api_pipeline_detail(issue_number: int):
    """특정 파이프라인 Issue 상세 + 댓글(Agent 상태)"""
    return harness.get_issue_detail(issue_number)


@app.post("/api/trigger")
async def api_trigger():
    orchestrator = OrchestratorAgent()
    result = await orchestrator.run_pipeline()
    return result
