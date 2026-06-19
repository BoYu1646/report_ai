from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from src.config import DEFAULT_CONFIG_PATH, AppConfig, load_config, save_config
from src.models import GenerateRequest, ReportResponse
from src.scheduler import create_scheduler
from src.services.report_service import ReportService


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"


class AppState:
    config: AppConfig = load_config()


state = AppState()
app = FastAPI(title="Weekly Report Agent", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    scheduler = create_scheduler(state.config)
    scheduler.start()
    app.state.scheduler = scheduler


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def get_config() -> dict:
    return state.config.model_dump(mode="json")


@app.post("/api/config")
async def update_config(payload: dict) -> dict[str, str]:
    state.config = AppConfig.model_validate(payload)
    save_config(state.config, DEFAULT_CONFIG_PATH)
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)
    scheduler = create_scheduler(state.config)
    scheduler.start()
    app.state.scheduler = scheduler
    return {"status": "saved"}


@app.post("/api/reports/generate", response_model=ReportResponse)
async def generate_report(request: GenerateRequest | None = None) -> ReportResponse:
    try:
        return await ReportService(state.config).generate(request or GenerateRequest())
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            detail = "Git API 认证失败：Token 无效、过期，或页面中填写了错误的 Git Token。公共仓库可清空 Token 后重试。"
        elif status_code == 403:
            detail = "Git API 权限不足或触发限流：请检查 Token 权限、组织授权或稍后重试。"
        elif status_code == 404:
            detail = "Git 仓库不存在或 Token 无权访问该仓库，请检查 owner/repo 与 Token 权限。"
        else:
            detail = f"Git API 请求失败：HTTP {status_code}。"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Git API 网络请求失败：{exc.__class__.__name__}。") from exc


@app.get("/api/reports/latest")
async def latest_report() -> dict[str, str]:
    return {"markdown": ReportService(state.config).latest_markdown()}


@app.get("/api/reports/export")
async def export_report() -> Response:
    if not state.config.web.enable_export:
        raise HTTPException(status_code=403, detail="Export is disabled by configuration.")
    latest = ReportService(state.config).latest_report_path()
    if not latest:
        raise HTTPException(status_code=404, detail="No report generated yet.")
    return FileResponse(latest, media_type="text/markdown", filename=latest.name)


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
