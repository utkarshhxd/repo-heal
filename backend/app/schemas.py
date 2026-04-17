from typing import Any

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    github_user_id: int
    login: str
    name: str | None = None
    avatar_url: str | None = None


class RepoResponse(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool
    default_branch: str
    owner_login: str


class BranchResponse(BaseModel):
    name: str


class JobCreateRequest(BaseModel):
    repository_full_name: str = Field(..., min_length=3)
    branch: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=3)


class JobResponse(BaseModel):
    id: str
    status: str
    repo_full_name: str
    base_branch: str
    fix_branch: str | None = None
    pr_number: int | None = None
    prompt: str
    summary: dict[str, Any] | None = None
    pr_url: str | None = None
    merged_at: str | None = None
    merge_commit_sha: str | None = None
    error: str | None = None
    logs: list[str]
    created_at: str
    updated_at: str
