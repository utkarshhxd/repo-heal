# Repo Agent

Repo Agent is a two-part app for repairing static website repositories through a chat UI. The frontend is a Next.js client, and the backend is a FastAPI service that authenticates with GitHub, clones a target repository, analyzes static files, applies fixes, validates the results, and opens a pull request.

## What It Does

- Connects to GitHub with OAuth
- Lets a user pick a repository and branch
- Scans only static-site files: `.html`, `.css`, and `.js`
- Runs rule-based checks plus local LLM-assisted fixes through Ollama
- Pushes validated fixes to a new branch
- Opens a GitHub pull request

## Project Structure

- `frontend/` - Next.js app router frontend
- `backend/` - FastAPI API, GitHub integration, repair orchestration, SQLite storage
- `.env.example` - the only environment template you need

## Environment Setup

This repo is configured to use one shared environment file at the repository root.

1. Copy `.env.example` to `.env`.
2. Fill in the GitHub OAuth values.
3. Adjust the Ollama model only if you want something different from the default.

### Environment Variables

```env
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_COOKIE_NAME=repo_agent_session
SESSION_COOKIE_SECURE=false
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_client_secret
GITHUB_CALLBACK_URL=http://localhost:8000/auth/github/callback
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
WORKSPACE_ROOT=backend/data/workspaces
DATABASE_PATH=backend/data/app.db
GIT_AUTHOR_NAME=Repo Agent
GIT_AUTHOR_EMAIL=repo-agent@local.dev
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Prerequisites

- Node.js 18+ with `npm`
- Python 3.11+ recommended
- Git
- Ollama installed and running locally
- A GitHub OAuth App

## GitHub OAuth App Setup

Create a GitHub OAuth App with:

- Homepage URL: `http://localhost:3000`
- Authorization callback URL: `http://localhost:8000/auth/github/callback`

Then copy the client ID and client secret into your root `.env`.

## Install On Your System

### 1. Frontend dependencies

```powershell
cd frontend
npm install
```

### 2. Backend Python environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Backend Node tooling

The backend uses Node-based validators like `htmlhint` and `eslint`.

```powershell
cd backend
npm install
```

### 4. Start Ollama

Make sure the model from `.env` is available locally:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

If you prefer another local model, update `OLLAMA_MODEL` in `.env`.

## Run Locally

Open two terminals.

### Terminal 1: backend

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2: frontend

```powershell
cd frontend
npm run dev
```

Then open `http://localhost:3000`.

## How The App Works

1. Sign in with GitHub from the frontend.
2. Select a repository and branch.
3. Enter a fix request in the chat box.
4. The backend clones the repository into `backend/data/workspaces/`.
5. The repair pipeline analyzes `.html`, `.css`, and `.js` files.
6. Validated changes are committed to a new branch and a PR is created.

## Notes

- SQLite data is stored under `backend/data/`.
- Workspace clones are temporary and cleaned up after each job.
- Access tokens are stored server-side for the active session flow.
- The app is currently scoped to static website repositories, not full-stack or framework-specific build systems.
