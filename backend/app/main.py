from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from . import db, github
from .agent import run_job
from .config import get_settings
from .schemas import BranchResponse, JobCreateRequest, JobResponse, RepoResponse, UserResponse


settings = get_settings()
app = FastAPI(title="Repo Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db.init_db()


def get_current_session(request: Request) -> dict:
    session_id = request.cookies.get(settings.session_cookie_name)
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return session


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "Repo Agent API"}


@app.get("/auth/github/login")
async def github_login() -> RedirectResponse:
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")
    state = db.create_oauth_state()
    return RedirectResponse(github.build_authorize_url(state), status_code=status.HTTP_302_FOUND)


@app.get("/auth/github/callback")
async def github_callback(code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error:
        return RedirectResponse(f"{settings.frontend_url}?auth_error={error}", status_code=status.HTTP_302_FOUND)
    if not code or not state or not db.pop_oauth_state(state):
        return RedirectResponse(f"{settings.frontend_url}?auth_error=invalid_state", status_code=status.HTTP_302_FOUND)

    token = await github.exchange_code_for_token(code)
    user = await github.get_authenticated_user(token)
    user_id = db.upsert_user(
        github_user_id=int(user["id"]),
        login=user["login"],
        name=user.get("name"),
        avatar_url=user.get("avatar_url"),
        access_token=token,
    )
    session_id = db.create_session(user_id)

    response = RedirectResponse(f"{settings.frontend_url}?connected=1", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=60 * 60 * 24 * 7,
    )
    return response


@app.post("/auth/logout")
async def logout(request: Request) -> Response:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        db.delete_session(session_id)
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        settings.session_cookie_name,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    return response


@app.get("/api/me", response_model=UserResponse)
async def me(session: dict = Depends(get_current_session)) -> UserResponse:
    return UserResponse(
        id=session["user_id"],
        github_user_id=session["github_user_id"],
        login=session["login"],
        name=session.get("name"),
        avatar_url=session.get("avatar_url"),
    )


@app.get("/api/repos", response_model=list[RepoResponse])
async def repos(session: dict = Depends(get_current_session)) -> list[RepoResponse]:
    repositories = await github.list_repositories(session["access_token"])
    return [
        RepoResponse(
            id=item["id"],
            name=item["name"],
            full_name=item["full_name"],
            private=item["private"],
            default_branch=item["default_branch"],
            owner_login=item["owner"]["login"],
        )
        for item in repositories
    ]


@app.get("/api/repos/{owner}/{repo}/branches", response_model=list[BranchResponse])
async def branches(owner: str, repo: str, session: dict = Depends(get_current_session)) -> list[BranchResponse]:
    payload = await github.list_branches(session["access_token"], f"{owner}/{repo}")
    return [BranchResponse(name=item["name"]) for item in payload]


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(payload: JobCreateRequest, session: dict = Depends(get_current_session)) -> JobResponse:
    job = db.create_job(
        user_id=session["user_id"],
        repo_full_name=payload.repository_full_name,
        base_branch=payload.branch,
        prompt=payload.prompt,
    )
    asyncio.create_task(run_job(job["id"]))
    return JobResponse(**job)


@app.post("/api/run", response_model=JobResponse)
async def start_run(payload: JobCreateRequest, session: dict = Depends(get_current_session)) -> JobResponse:
    job = db.create_job(
        user_id=session["user_id"],
        repo_full_name=payload.repository_full_name,
        base_branch=payload.branch,
        prompt=payload.prompt,
    )
    asyncio.create_task(run_job(job["id"]))
    return JobResponse(**job)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, session: dict = Depends(get_current_session)) -> JobResponse:
    job = db.get_job(job_id, user_id=session["user_id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@app.post("/api/jobs/{job_id}/merge", response_model=JobResponse)
async def merge_job_pull_request(job_id: str, session: dict = Depends(get_current_session)) -> JobResponse:
    job = db.get_job(job_id, user_id=session["user_id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "completed":
        raise HTTPException(status_code=409, detail="The repair job has not completed yet")
    if not job.get("pr_url") or not job.get("pr_number"):
        raise HTTPException(status_code=409, detail="This job does not have a pull request to merge")
    if job.get("merged_at"):
        raise HTTPException(status_code=409, detail="This pull request has already been merged")

    token = db.get_access_token_for_user(session["user_id"])
    try:
        result = await github.merge_pull_request(token, job["repo_full_name"], int(job["pr_number"]))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub merge failed: {exc}") from exc

    db.append_job_log(job_id, f"Merged pull request #{job['pr_number']}.")
    updated_job = db.update_job(
        job_id,
        merged_at=db.utc_now(),
        merge_commit_sha=result.get("sha"),
    )
    return JobResponse(**updated_job)


@app.get("/api/events/{job_id}")
async def job_events(job_id: str, request: Request, session: dict = Depends(get_current_session)):
    async def event_generator():
        last_log_index = 0
        last_status = "queued"
        
        while True:
            if await request.is_disconnected():
                break
                
            job = db.get_job(job_id, user_id=session["user_id"])
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
                break
                
            current_logs = job.get("logs", [])
            while last_log_index < len(current_logs):
                msg = current_logs[last_log_index]
                if msg.startswith("$ "):
                    msg = msg[2:]
                yield f"data: {json.dumps({'type': 'step', 'message': msg})}\n\n"
                last_log_index += 1
                
            status = job.get("status")
            if status == "completed" and last_status != "completed":
                # Ensure all logs are streamed before sending success
                yield f"data: {json.dumps({'type': 'success', 'message': 'Pull request created successfully!', 'pr_url': job.get('pr_url')})}\n\n"
                break
            elif status == "failed" and last_status != "failed":
                yield f"data: {json.dumps({'type': 'error', 'message': job.get('error', 'Job failed unexpectedly')})}\n\n"
                break
                
            last_status = status
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
