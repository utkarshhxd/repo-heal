# Client Demo With A Tunnel

This project can be shared directly from your own laptop for a live client demo.

The app has two local services:

- frontend on `http://localhost:3000`
- backend on `http://localhost:8000`

Because GitHub OAuth is part of the flow, you must expose both services and update the public URLs before sending the app to your client.

## Tool To Use

Use `ngrok`.

## 1. Start The App Locally

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

Check these URLs first on your own machine:

- `http://localhost:3000`
- `http://localhost:8000/api/health`

## 2. Create Public Tunnel URLs

Open two more terminals.

```powershell
ngrok http 8000
```

```powershell
ngrok http 3000
```

You should get two HTTPS URLs, for example:

- backend: `https://my-backend.ngrok-free.app`
- frontend: `https://my-frontend.ngrok-free.app`

## 3. Update The Root `.env`

Replace the local URLs with your tunnel URLs.

```env
BACKEND_URL=https://YOUR-BACKEND-TUNNEL
FRONTEND_URL=https://YOUR-FRONTEND-TUNNEL
SESSION_COOKIE_NAME=repo_agent_session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_client_secret
GITHUB_CALLBACK_URL=https://YOUR-FRONTEND-TUNNEL/auth/github/callback
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash,gemini-2.0-flash
WORKSPACE_ROOT=backend/data/workspaces
DATABASE_PATH=backend/data/app.db
GIT_AUTHOR_NAME=Repo Agent
GIT_AUTHOR_EMAIL=repo-agent@local.dev
NEXT_PUBLIC_API_BASE_URL=
```

Important:

- `SESSION_COOKIE_SECURE=true` is required for HTTPS demo URLs.
- Keep the OAuth callback on the frontend tunnel domain so the session cookie is stored for the same site your client is using.
- Leave `NEXT_PUBLIC_API_BASE_URL` empty for the frontend tunnel flow so browser requests stay same-origin and use Next.js rewrites.
- Restart both frontend and backend after changing `.env`.

## 4. Update Your GitHub OAuth App

In your GitHub OAuth App settings, set:

- Homepage URL: `https://YOUR-FRONTEND-TUNNEL`
- Authorization callback URL: `https://YOUR-FRONTEND-TUNNEL/auth/github/callback`

The callback URL must exactly match `GITHUB_CALLBACK_URL`.

## 5. Restart The App

After saving `.env`, restart both services:

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```powershell
cd frontend
npm run dev
```

## 6. Test Before Sending To Client

Open the frontend tunnel URL in an incognito window and verify:

1. The page loads.
2. GitHub login redirects correctly.
3. You return to the app after login.
4. Repository loading works.
5. A demo repair job can start.

## 7. Send Only The Frontend URL

Send your client the frontend tunnel URL only.

Example:

```text
https://YOUR-FRONTEND-TUNNEL
```

The frontend already proxies `/api` and `/auth` requests to the backend.

## Demo Notes

- Your laptop must stay on and connected during the demo.
- Free tunnel URLs may change every time you restart them.
- If the tunnel URL changes, update `.env`, update the GitHub OAuth app, and restart both services.
- If login fails after a tunnel restart, the callback URL is usually the first thing to check.
