# Showcase Deployment

This repo can be showcased with:

- Frontend: Vercel, using `frontend/` as the project root.
- Backend: Render, using the Docker service in `backend/Dockerfile`.

## 1. Deploy Backend On Render

Create a new Render Web Service from this repository.

- Runtime: Docker
- Root directory: `backend`
- Health check path: `/api/health`

Set these environment variables:

```env
BACKEND_URL=https://YOUR-RENDER-SERVICE.onrender.com
FRONTEND_URL=https://YOUR-VERCEL-PROJECT.vercel.app
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_client_secret
GITHUB_CALLBACK_URL=https://YOUR-VERCEL-PROJECT.vercel.app/auth/github/callback
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
DATABASE_PATH=/app/data/app.db
WORKSPACE_ROOT=/app/data/workspaces
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash,gemini-2.0-flash
GIT_AUTHOR_NAME=Repo Agent
GIT_AUTHOR_EMAIL=repo-agent@local.dev
```

Add a persistent disk mounted at `/app/data` so SQLite and temporary workspace paths survive restarts.

## 2. Deploy Frontend On Vercel

Create a Vercel project from this repository.

- Framework preset: Next.js
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `.next`

Set this environment variable:

```env
BACKEND_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Do not set `NEXT_PUBLIC_API_BASE_URL` on Vercel for the proxied production setup. The frontend should call same-origin `/api` and `/auth` routes so browser cookies are stored for the Vercel app domain.

Redeploy the frontend after setting the final Render backend URL.

## 3. Configure GitHub OAuth

In your GitHub OAuth App, use:

- Homepage URL: `https://YOUR-VERCEL-PROJECT.vercel.app`
- Authorization callback URL: `https://YOUR-VERCEL-PROJECT.vercel.app/auth/github/callback`

The callback URL must exactly match `GITHUB_CALLBACK_URL` on Render.

## Gemini API Key

Create a Gemini API key in Google AI Studio and add it to Render as `GEMINI_API_KEY`.
The free tier is suitable for a showcase, but requests are rate-limited.
