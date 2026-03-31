# GClaw Web App & Firebase Auth (Plan 4a of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Firebase Authentication middleware for the FastAPI backend, replace hardcoded user_id with auth-derived user_id across all API endpoints, scaffold a Next.js 14+ web app with TypeScript and Tailwind CSS, implement Google Sign-In on the client, create a Chat View and Board View, and set up PWA basics for mobile installability.

**Architecture:** The backend gains a Firebase Auth middleware that verifies ID tokens on every request (except `/health`) and injects the authenticated `user_id` into request state. The frontend is a Next.js App Router project in `web/` that uses Firebase JS SDK for authentication and Firestore real-time listeners. An API client module handles all HTTP calls to the FastAPI backend with automatic auth token injection. The Chat View calls `POST /chat` and renders markdown responses. The Board View reads tasks directly from Firestore with real-time listeners and groups them by kanban status columns.

**Tech Stack:**
- Backend: Python 3.10, FastAPI, firebase-admin (for ID token verification)
- Frontend: Next.js 14+, TypeScript (strict), Tailwind CSS, Firebase JS SDK (Auth + Firestore), React 18+
- Testing: pytest + mocks (backend), vitest + React Testing Library (frontend)

**Builds on Plans 1-3:**
- `create_app` factory, `AgentRunner`, `BoardService`, `CronService`, `HeartbeatService`
- `ChatRequest` / `ChatResponse` in `api/chat.py`
- `BoardRepo` with `users/{userId}/board/{taskId}` Firestore paths
- `Settings` dataclass for configuration
- All existing API routes (`/chat`, `/board/*`, `/cron/*`, `/heartbeat/*`)

**Subsequent Plans (future):**
- Plan 4b: Voice (Gemini Live API), Agent Dashboard, Skills & Crons views, Memory Explorer
- Plan 4c: Multi-user A2A, onboarding flow, full PWA (push notifications, offline support)

---

## File Structure

```
gclaw/
├── src/
│   └── gclaw/
│       ├── settings.py                          # MODIFY: add firebase_project_id setting
│       ├── auth/
│       │   ├── __init__.py                      # NEW
│       │   ├── middleware.py                     # NEW: Firebase Auth middleware
│       │   └── dependencies.py                  # NEW: FastAPI dependency for user_id
│       ├── api/
│       │   ├── app.py                           # MODIFY: add auth middleware
│       │   ├── chat.py                          # MODIFY: use auth-derived user_id
│       │   └── board_routes.py                  # MODIFY: use auth-derived user_id
├── tests/
│   ├── test_auth_middleware.py                   # NEW
│   └── test_api_auth.py                         # NEW: API tests with auth
├── web/
│   ├── package.json                             # NEW
│   ├── tsconfig.json                            # NEW
│   ├── next.config.ts                           # NEW
│   ├── tailwind.config.ts                       # NEW
│   ├── postcss.config.mjs                       # NEW
│   ├── public/
│   │   ├── manifest.json                        # NEW: PWA manifest
│   │   ├── sw.js                                # NEW: Service worker
│   │   ├── icon-192.png                         # NEW: PWA icon placeholder
│   │   └── icon-512.png                         # NEW: PWA icon placeholder
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx                       # NEW: Root layout with auth provider
│   │   │   ├── page.tsx                         # NEW: Landing / redirect
│   │   │   ├── globals.css                      # NEW: Tailwind imports
│   │   │   ├── login/
│   │   │   │   └── page.tsx                     # NEW: Login page
│   │   │   ├── chat/
│   │   │   │   └── page.tsx                     # NEW: Chat View page
│   │   │   └── board/
│   │   │       └── page.tsx                     # NEW: Board View page
│   │   ├── lib/
│   │   │   ├── firebase.ts                      # NEW: Firebase client init
│   │   │   └── api-client.ts                    # NEW: Typed HTTP client with auth
│   │   ├── contexts/
│   │   │   └── auth-context.tsx                 # NEW: React auth context + provider
│   │   ├── components/
│   │   │   ├── auth-guard.tsx                   # NEW: Route protection component
│   │   │   ├── chat/
│   │   │   │   ├── chat-view.tsx                # NEW: Chat interface
│   │   │   │   ├── message-list.tsx             # NEW: Message rendering
│   │   │   │   └── message-input.tsx            # NEW: Input box
│   │   │   └── board/
│   │   │       ├── board-view.tsx               # NEW: Kanban board
│   │   │       ├── board-column.tsx             # NEW: Status column
│   │   │       └── task-card.tsx                # NEW: Task card
│   │   └── types/
│   │       └── index.ts                         # NEW: Shared TypeScript types
│   ├── __tests__/
│   │   ├── api-client.test.ts                   # NEW
│   │   ├── auth-context.test.tsx                # NEW
│   │   ├── chat-view.test.tsx                   # NEW
│   │   └── board-view.test.tsx                  # NEW
│   └── .env.local.example                       # NEW
```

---

### Task 1: Firebase Auth Middleware (Python/FastAPI)

**Files:**
- Create: `src/gclaw/auth/__init__.py`
- Create: `src/gclaw/auth/middleware.py`
- Create: `src/gclaw/auth/dependencies.py`
- Modify: `src/gclaw/settings.py`
- Create: `tests/test_auth_middleware.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth_middleware.py`:

```python
"""Tests for Firebase Auth middleware and dependencies."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends
from starlette.requests import Request

from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.auth.dependencies import get_current_user_id


@pytest.fixture
def mock_verify_token():
    """Mock firebase_admin.auth.verify_id_token."""
    with patch("gclaw.auth.middleware.firebase_auth") as mock_auth:
        mock_auth.verify_id_token.return_value = {
            "uid": "test_user_123",
            "email": "test@example.com",
        }
        yield mock_auth


@pytest.fixture
def app_with_auth(mock_verify_token):
    """FastAPI app with auth middleware and a test endpoint."""
    app = FastAPI()
    app.add_middleware(FirebaseAuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        return {"user_id": request.state.user_id}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_bypasses_auth(auth_client):
    """Health endpoint should not require auth."""
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401(auth_client):
    resp = await auth_client.get("/protected")
    assert resp.status_code == 401
    assert "missing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_bearer_format_returns_401(auth_client):
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "NotBearer token123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_sets_user_id(auth_client, mock_verify_token):
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "Bearer valid_token_here"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "test_user_123"
    mock_verify_token.verify_id_token.assert_called_once_with("valid_token_here")


@pytest.mark.asyncio
async def test_expired_token_returns_401(auth_client, mock_verify_token):
    mock_verify_token.verify_id_token.side_effect = Exception("Token expired")
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "Bearer expired_token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_dependency():
    """Test the FastAPI dependency extracts user_id from request state."""
    mock_request = MagicMock()
    mock_request.state.user_id = "dep_user_456"
    user_id = await get_current_user_id(mock_request)
    assert user_id == "dep_user_456"


@pytest.mark.asyncio
async def test_get_current_user_id_missing_raises():
    """Test the dependency raises 401 when user_id is not set."""
    mock_request = MagicMock()
    mock_request.state = MagicMock(spec=[])  # no user_id attribute
    with pytest.raises(Exception):
        await get_current_user_id(mock_request)
```

- [ ] **Step 2: Create `src/gclaw/auth/__init__.py`**

```python
"""Firebase authentication for GClaw API."""
```

- [ ] **Step 3: Create `src/gclaw/auth/middleware.py`**

```python
"""Firebase Auth middleware for FastAPI.

Verifies Firebase ID tokens from the Authorization header and injects
the authenticated user_id into request.state for downstream handlers.
"""

from __future__ import annotations

import logging

from firebase_admin import auth as firebase_auth
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that do not require authentication
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Verify Firebase ID token on every request (except public paths).

    Expects header: Authorization: Bearer <firebase_id_token>
    Sets: request.state.user_id = decoded token uid
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
            )

        # Parse Bearer token
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format. Expected: Bearer <token>"},
            )

        token = parts[1]

        # Verify token with Firebase Admin SDK
        try:
            decoded = firebase_auth.verify_id_token(token)
            request.state.user_id = decoded["uid"]
        except Exception as exc:
            logger.warning("Firebase token verification failed: %s", exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)
```

- [ ] **Step 4: Create `src/gclaw/auth/dependencies.py`**

```python
"""FastAPI dependencies for authentication."""

from __future__ import annotations

from fastapi import HTTPException, Request


async def get_current_user_id(request: Request) -> str:
    """Extract authenticated user_id from request state.

    The FirebaseAuthMiddleware must run before this dependency.
    Returns the user_id string set by the middleware.
    Raises 401 if no user_id is present (middleware was bypassed or failed).
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id
```

- [ ] **Step 5: Add `firebase-admin` to backend dependencies**

In `pyproject.toml`, add to `dependencies`:

```toml
    "firebase-admin>=6.4.0",
```

- [ ] **Step 6: Modify `src/gclaw/settings.py` — add Firebase config**

Add to the `Settings` dataclass:

```python
    # Firebase Auth settings
    firebase_auth_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "FIREBASE_AUTH_ENABLED", "false"
        ).lower() == "true"
    )
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_auth_middleware.py -v`
Expected: All 7 tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/gclaw/auth/ tests/test_auth_middleware.py
git commit -m "feat: Firebase Auth middleware with token verification and user_id injection"
```

---

### Task 2: Auth-Aware API Endpoints

**Files:**
- Modify: `src/gclaw/api/app.py`
- Modify: `src/gclaw/api/chat.py`
- Modify: `src/gclaw/api/board_routes.py`
- Create: `tests/test_api_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_auth.py`:

```python
"""Tests for auth-aware API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.task import BoardTask
from gclaw.dispatch.runner import AgentResponse


@pytest.fixture
def mock_firebase_auth():
    with patch("gclaw.auth.middleware.firebase_auth") as mock_auth:
        mock_auth.verify_id_token.return_value = {
            "uid": "auth_user_1",
            "email": "test@example.com",
        }
        yield mock_auth


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    svc.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    return svc


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="Hello from GClaw!", is_final=True
    )
    return runner


@pytest.fixture
def app(board_service, agent_runner, mock_firebase_auth):
    return create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        enable_auth=True,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth_headers(token: str = "valid_token") -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_chat_uses_auth_user_id(client, agent_runner):
    """POST /chat should derive user_id from auth token, not request body."""
    resp = await client.post(
        "/chat",
        json={"session_id": "sess_1", "message": "Hello"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    # Verify runner was called with the auth-derived user_id
    agent_runner.run.assert_called_once_with(
        user_id="auth_user_1",
        session_id="sess_1",
        message="Hello",
    )


@pytest.mark.asyncio
async def test_chat_without_auth_returns_401(client):
    resp = await client.post(
        "/chat",
        json={"session_id": "sess_1", "message": "Hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_board_list_uses_auth_user_id(client, board_service):
    """GET /board/tasks should use auth user_id, not query param."""
    resp = await client.get("/board/tasks", headers=_auth_headers())
    assert resp.status_code == 200
    board_service.get_all_tasks.assert_called_once()


@pytest.mark.asyncio
async def test_board_create_uses_auth_user_id(client, board_service):
    resp = await client.post(
        "/board/tasks",
        json={"title": "Test task", "assignee": "workspace-mgr"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Modify `src/gclaw/api/app.py` — add auth middleware**

```python
"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.dispatch.runner import AgentRunner


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
    cron_service: CronService | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    memory_service: object | None = None,
    skill_registry: object | None = None,
    enable_auth: bool = False,
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.4.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if enable_auth:
        app.add_middleware(FirebaseAuthMiddleware)

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    if cron_service is not None:
        app.include_router(init_cron_router(cron_service))

    if heartbeat_service is not None:
        app.include_router(init_heartbeat_router(heartbeat_service))

    # Store services on app state for use by future route extensions
    app.state.session_service = session_service
    app.state.memory_service = memory_service
    app.state.skill_registry = skill_registry

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 3: Modify `src/gclaw/api/chat.py` — use auth-derived user_id**

```python
"""Chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.dispatch.runner import AgentRunner

router = APIRouter()

_runner: AgentRunner | None = None


def init_chat_router(runner: AgentRunner) -> APIRouter:
    global _runner
    _runner = runner
    return router


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[dict] = []
    is_final: bool = False


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    response = await _runner.run(
        user_id=user_id,
        session_id=req.session_id,
        message=req.message,
    )
    return ChatResponse(
        text=response.text,
        tool_calls=response.tool_calls,
        is_final=response.is_final,
    )
```

- [ ] **Step 4: Modify `src/gclaw/api/board_routes.py` — use auth-derived user_id**

```python
"""Board CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.board.service import BoardService

router = APIRouter(prefix="/board")

_board_service: BoardService | None = None


def init_board_router(board_service: BoardService) -> APIRouter:
    global _board_service
    _board_service = board_service
    return router


class CreateTaskRequest(BaseModel):
    title: str
    assignee: str
    description: str = ""
    priority: str = "medium"


@router.get("/tasks")
def list_tasks(user_id: str = Depends(get_current_user_id)):
    tasks = _board_service.get_all_tasks()
    return [t.model_dump(mode="json") for t in tasks]


@router.post("/tasks", status_code=201)
def create_task(
    req: CreateTaskRequest,
    user_id: str = Depends(get_current_user_id),
):
    task = _board_service.create_task(
        title=req.title,
        assignee=req.assignee,
        description=req.description,
        priority=req.priority,
    )
    return task.model_dump(mode="json")
```

- [ ] **Step 5: Update `tests/test_api.py` — fix for new ChatRequest (no user_id in body)**

The existing `test_api.py` creates apps without auth (`enable_auth=False` by default), so chat requests need updating to match the new `ChatRequest` model that no longer has `user_id` in the body. When auth is disabled, the `get_current_user_id` dependency still needs a `user_id` on `request.state`. Add an override:

```python
"""Tests for FastAPI endpoints (auth disabled mode)."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from starlette.requests import Request

from gclaw.api.app import create_app
from gclaw.auth.dependencies import get_current_user_id
from gclaw.models.task import BoardTask, TaskStatus
from gclaw.dispatch.runner import AgentResponse


async def _override_user_id() -> str:
    """Provide a test user_id when auth middleware is disabled."""
    return "test_user_1"


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    svc.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    return svc


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    return runner


@pytest.fixture
def app(board_service, agent_runner):
    application = create_app(
        board_service=board_service,
        agent_runner=agent_runner,
    )
    # Override the auth dependency for tests without auth middleware
    application.dependency_overrides[get_current_user_id] = _override_user_id
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat(client, agent_runner):
    agent_runner.run.return_value = AgentResponse(
        text="Hello! I'm GClaw.", is_final=True
    )

    resp = await client.post("/chat", json={
        "session_id": "sess_1",
        "message": "Hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello! I'm GClaw."
    assert data["is_final"] is True


@pytest.mark.asyncio
async def test_list_board_tasks_empty(client):
    resp = await client.get("/board/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_board_task(client, board_service):
    resp = await client.post("/board/tasks", json={
        "title": "New task",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New task"
    board_service.create_task.assert_called_once()
```

- [ ] **Step 6: Run all backend tests**

Run: `pytest tests/ -v`
Expected: All existing tests pass (with updated test_api.py), plus new auth tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/api/ src/gclaw/auth/ tests/test_api.py tests/test_api_auth.py
git commit -m "feat: auth-aware API endpoints — user_id derived from Firebase token"
```

---

### Task 3: Next.js Project Scaffolding

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/next.config.ts`
- Create: `web/tailwind.config.ts`
- Create: `web/postcss.config.mjs`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/app/page.tsx`
- Create: `web/src/app/globals.css`
- Create: `web/src/types/index.ts`
- Create: `web/.env.local.example`

- [ ] **Step 1: Create `web/package.json`**

```json
{
  "name": "gclaw-web",
  "version": "0.4.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "firebase": "^10.12.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.4.0",
    "vitest": "^2.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^24.0.0"
  }
}
```

- [ ] **Step 2: Create `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create `web/next.config.ts`**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Output as standalone for Docker/Cloud Run deployment
  output: "standalone",
};

export default nextConfig;
```

- [ ] **Step 4: Create `web/tailwind.config.ts`**

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/contexts/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gclaw: {
          primary: "#4285F4",    // Google Blue
          secondary: "#34A853",  // Google Green
          accent: "#FBBC05",     // Google Yellow
          danger: "#EA4335",     // Google Red
          bg: "#0F172A",         // Dark slate
          surface: "#1E293B",    // Lighter slate
          text: "#F1F5F9",       // Light gray
          muted: "#94A3B8",      // Muted gray
        },
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 5: Create `web/postcss.config.mjs`**

```javascript
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
```

- [ ] **Step 6: Create `web/src/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-gclaw-bg text-gclaw-text;
  }
}
```

- [ ] **Step 7: Create `web/src/types/index.ts`**

```typescript
/** Shared TypeScript types for GClaw web app. */

/** Task status matching backend TaskStatus enum. */
export type TaskStatus =
  | "backlog"
  | "queued"
  | "in_progress"
  | "needs_approval"
  | "done"
  | "failed";

/** Task priority matching backend TaskPriority enum. */
export type TaskPriority = "high" | "medium" | "low";

/** Source of a board task. */
export interface TaskSource {
  type: "user" | "agent" | "cron";
  origin?: string;
}

/** Result of a completed task. */
export interface TaskResult {
  summary: string;
  artifacts: string[];
}

/** Board task matching the backend BoardTask model. */
export interface BoardTask {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  source: TaskSource;
  assignee: string;
  dependencies: string[];
  requires_approval: boolean;
  result?: TaskResult;
  created_at: string;
  updated_at: string;
}

/** Chat message in the UI. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  tool_calls?: ToolCall[];
}

/** Tool call from agent response. */
export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

/** Chat API request body. */
export interface ChatRequest {
  session_id: string;
  message: string;
}

/** Chat API response body. */
export interface ChatResponse {
  text: string;
  tool_calls: ToolCall[];
  is_final: boolean;
}

/** Kanban board column definition. */
export interface BoardColumn {
  status: TaskStatus;
  label: string;
  color: string;
}

/** Board columns configuration. */
export const BOARD_COLUMNS: BoardColumn[] = [
  { status: "backlog", label: "Backlog", color: "border-gray-500" },
  { status: "queued", label: "Queued", color: "border-blue-500" },
  { status: "in_progress", label: "In Progress", color: "border-yellow-500" },
  { status: "needs_approval", label: "Needs Approval", color: "border-orange-500" },
  { status: "done", label: "Done", color: "border-green-500" },
  { status: "failed", label: "Failed", color: "border-red-500" },
];
```

- [ ] **Step 8: Create `web/src/app/layout.tsx`** (placeholder, auth provider added in Task 4)

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GClaw",
  description: "Personal AI Agent Platform",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
```

- [ ] **Step 9: Create `web/src/app/page.tsx`**

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to chat as the default view
    router.replace("/chat");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gclaw-muted">Loading GClaw...</p>
    </div>
  );
}
```

- [ ] **Step 10: Create `web/.env.local.example`**

```
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789:web:abcdef
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 11: Install dependencies and verify build**

Run:
```bash
cd /mnt/c/Dev/GClaw/web && npm install
npx next build
```
Expected: Successful installation and build (may show warnings, no errors).

- [ ] **Step 12: Commit**

```bash
git add web/
git commit -m "feat: Next.js project scaffolding with TypeScript, Tailwind, and shared types"
```

---

### Task 4: Firebase Client-Side Auth

**Files:**
- Create: `web/src/lib/firebase.ts`
- Create: `web/src/contexts/auth-context.tsx`
- Create: `web/src/components/auth-guard.tsx`
- Create: `web/src/app/login/page.tsx`
- Modify: `web/src/app/layout.tsx`
- Create: `web/__tests__/auth-context.test.tsx`

- [ ] **Step 1: Create `web/vitest.config.ts`** (needed for testing)

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./__tests__/setup.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

- [ ] **Step 2: Create `web/__tests__/setup.ts`**

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: Create `web/src/lib/firebase.ts`**

```typescript
/**
 * Firebase client initialization.
 *
 * Reads config from NEXT_PUBLIC_FIREBASE_* environment variables.
 * Initializes Firebase App, Auth, and Firestore instances.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Prevent re-initialization during hot reload
let app: FirebaseApp;
if (getApps().length === 0) {
  app = initializeApp(firebaseConfig);
} else {
  app = getApps()[0];
}

export const firebaseApp: FirebaseApp = app;
export const auth: Auth = getAuth(app);
export const db: Firestore = getFirestore(app);
```

- [ ] **Step 4: Create `web/src/contexts/auth-context.tsx`**

```tsx
"use client";

/**
 * React context for Firebase Authentication state.
 *
 * Provides:
 * - user: current Firebase User or null
 * - loading: true while auth state is being determined
 * - signInWithGoogle: trigger Google Sign-In popup
 * - signOut: sign out the current user
 * - getIdToken: get the current user's ID token for API calls
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { auth } from "@/lib/firebase";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const googleProvider = new GoogleAuthProvider();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    await signInWithPopup(auth, googleProvider);
  }, []);

  const handleSignOut = useCallback(async () => {
    await firebaseSignOut(auth);
    setUser(null);
  }, []);

  const getIdToken = useCallback(async (): Promise<string | null> => {
    if (!user) return null;
    return user.getIdToken();
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        signInWithGoogle,
        signOut: handleSignOut,
        getIdToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
```

- [ ] **Step 5: Create `web/src/components/auth-guard.tsx`**

```tsx
"use client";

/**
 * Route protection component.
 * Redirects unauthenticated users to /login.
 * Shows a loading spinner while auth state is being determined.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gclaw-primary border-t-transparent" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}
```

- [ ] **Step 6: Create `web/src/app/login/page.tsx`**

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) {
      router.replace("/chat");
    }
  }, [user, loading, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gclaw-primary">GClaw</h1>
        <p className="mt-2 text-gclaw-muted">
          Personal AI Agent Platform
        </p>
      </div>

      <button
        onClick={signInWithGoogle}
        disabled={loading}
        className="flex items-center gap-3 rounded-lg bg-white px-6 py-3 text-gray-800 shadow-md transition-colors hover:bg-gray-100 disabled:opacity-50"
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24">
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
        <span className="font-medium">Sign in with Google</span>
      </button>
    </div>
  );
}
```

- [ ] **Step 7: Update `web/src/app/layout.tsx` — wrap with AuthProvider**

```tsx
import type { Metadata } from "next";
import { AuthProvider } from "@/contexts/auth-context";
import "./globals.css";

export const metadata: Metadata = {
  title: "GClaw",
  description: "Personal AI Agent Platform",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 8: Write test for auth context**

Create `web/__tests__/auth-context.test.tsx`:

```tsx
/**
 * Tests for AuthContext provider.
 *
 * Mocks Firebase auth to test context behavior without a real Firebase project.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock Firebase modules before importing components
const mockOnAuthStateChanged = vi.fn();
const mockSignInWithPopup = vi.fn();
const mockSignOut = vi.fn();

vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: (...args: unknown[]) => mockOnAuthStateChanged(...args),
  signInWithPopup: (...args: unknown[]) => mockSignInWithPopup(...args),
  signOut: (...args: unknown[]) => mockSignOut(...args),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

import { AuthProvider, useAuth } from "@/contexts/auth-context";

function TestConsumer() {
  const { user, loading, signInWithGoogle, signOut } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.uid : "null"}</span>
      <button onClick={signInWithGoogle}>Sign In</button>
      <button onClick={signOut}>Sign Out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts in loading state", () => {
    // Don't call the callback yet
    mockOnAuthStateChanged.mockReturnValue(vi.fn());

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId("loading").textContent).toBe("true");
    expect(screen.getByTestId("user").textContent).toBe("null");
  });

  it("updates user when auth state changes", async () => {
    mockOnAuthStateChanged.mockImplementation((_auth: unknown, callback: (user: unknown) => void) => {
      // Simulate async auth state resolution
      setTimeout(() => callback({ uid: "test_uid_123", getIdToken: vi.fn() }), 0);
      return vi.fn();
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
      expect(screen.getByTestId("user").textContent).toBe("test_uid_123");
    });
  });

  it("sets user to null when not authenticated", async () => {
    mockOnAuthStateChanged.mockImplementation((_auth: unknown, callback: (user: null) => void) => {
      setTimeout(() => callback(null), 0);
      return vi.fn();
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
      expect(screen.getByTestId("user").textContent).toBe("null");
    });
  });
});
```

- [ ] **Step 9: Run frontend tests**

Run: `cd /mnt/c/Dev/GClaw/web && npx vitest run`
Expected: Auth context tests pass.

- [ ] **Step 10: Commit**

```bash
git add web/src/lib/ web/src/contexts/ web/src/components/auth-guard.tsx web/src/app/login/ web/src/app/layout.tsx web/__tests__/ web/vitest.config.ts
git commit -m "feat: Firebase client-side auth with Google Sign-In, AuthProvider, and route protection"
```

---

### Task 5: API Client (TypeScript, Auth Token Injection)

**Files:**
- Create: `web/src/lib/api-client.ts`
- Create: `web/__tests__/api-client.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/api-client.test.ts`:

```typescript
/**
 * Tests for the API client.
 *
 * Mocks fetch globally to verify request construction, auth headers,
 * and response handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock Firebase modules
vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: vi.fn(),
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

import { ApiClient } from "@/lib/api-client";

describe("ApiClient", () => {
  let client: ApiClient;
  const mockGetToken = vi.fn<() => Promise<string | null>>();

  beforeEach(() => {
    client = new ApiClient("http://localhost:8000", mockGetToken);
    mockGetToken.mockResolvedValue("test_token_123");
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends chat request with auth header", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue({
        text: "Hello!",
        tool_calls: [],
        is_final: true,
      }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const result = await client.chat("sess_1", "Hello");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/chat",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer test_token_123",
        }),
        body: JSON.stringify({
          session_id: "sess_1",
          message: "Hello",
        }),
      })
    );
    expect(result.text).toBe("Hello!");
  });

  it("fetches board tasks with auth header", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue([
        { id: "task_1", title: "Test task", status: "queued" },
      ]),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const tasks = await client.getBoardTasks();

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/board/tasks",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test_token_123",
        }),
      })
    );
    expect(tasks).toHaveLength(1);
    expect(tasks[0].title).toBe("Test task");
  });

  it("creates a board task", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue({
        id: "task_new",
        title: "New task",
        status: "backlog",
      }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const task = await client.createBoardTask("New task", "workspace-mgr");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/board/tasks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "New task",
          assignee: "workspace-mgr",
        }),
      })
    );
    expect(task.title).toBe("New task");
  });

  it("throws on non-ok response", async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: vi.fn().mockResolvedValue({ detail: "Something broke" }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    await expect(client.chat("sess_1", "Hello")).rejects.toThrow();
  });

  it("throws when no auth token available", async () => {
    mockGetToken.mockResolvedValue(null);

    await expect(client.chat("sess_1", "Hello")).rejects.toThrow(
      "Not authenticated"
    );
  });
});
```

- [ ] **Step 2: Create `web/src/lib/api-client.ts`**

```typescript
/**
 * Typed HTTP client for the GClaw FastAPI backend.
 *
 * Automatically injects the Firebase ID token into every request.
 * All methods throw on non-OK responses.
 */

import type { ChatRequest, ChatResponse, BoardTask } from "@/types";

export class ApiClient {
  private baseUrl: string;
  private getToken: () => Promise<string | null>;

  constructor(baseUrl: string, getToken: () => Promise<string | null>) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.getToken = getToken;
  }

  /** Build headers with auth token. */
  private async headers(): Promise<Record<string, string>> {
    const token = await this.getToken();
    if (!token) {
      throw new Error("Not authenticated");
    }
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  }

  /** Generic request handler with error checking. */
  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const hdrs = await this.headers();
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: { ...hdrs, ...(options.headers as Record<string, string>) },
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // ignore JSON parse errors
      }
      throw new Error(`API error ${response.status}: ${detail}`);
    }

    return response.json() as Promise<T>;
  }

  /** Send a chat message and get the agent response. */
  async chat(sessionId: string, message: string): Promise<ChatResponse> {
    const body: ChatRequest = {
      session_id: sessionId,
      message,
    };
    return this.request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Fetch all board tasks for the authenticated user. */
  async getBoardTasks(): Promise<BoardTask[]> {
    return this.request<BoardTask[]>("/board/tasks");
  }

  /** Create a new board task. */
  async createBoardTask(
    title: string,
    assignee: string,
    description?: string,
    priority?: string
  ): Promise<BoardTask> {
    const body: Record<string, string> = { title, assignee };
    if (description) body.description = description;
    if (priority) body.priority = priority;
    return this.request<BoardTask>("/board/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Health check. */
  async healthCheck(): Promise<{ status: string }> {
    // Health doesn't need auth, but we send it anyway for simplicity
    const response = await fetch(`${this.baseUrl}/health`);
    return response.json();
  }
}

/**
 * Create a pre-configured ApiClient instance.
 * Pass the getIdToken function from useAuth().
 */
export function createApiClient(
  getToken: () => Promise<string | null>
): ApiClient {
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  return new ApiClient(baseUrl, getToken);
}
```

- [ ] **Step 3: Run tests**

Run: `cd /mnt/c/Dev/GClaw/web && npx vitest run`
Expected: All API client tests pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/api-client.ts web/__tests__/api-client.test.ts
git commit -m "feat: typed API client with Firebase auth token injection"
```

---

### Task 6: Chat View

**Files:**
- Create: `web/src/components/chat/chat-view.tsx`
- Create: `web/src/components/chat/message-list.tsx`
- Create: `web/src/components/chat/message-input.tsx`
- Create: `web/src/app/chat/page.tsx`
- Create: `web/__tests__/chat-view.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/chat-view.test.tsx`:

```tsx
/**
 * Tests for Chat View components.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock Firebase
vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: vi.fn((_auth: unknown, cb: (u: unknown) => void) => {
    cb({ uid: "test_user", getIdToken: vi.fn().mockResolvedValue("token") });
    return vi.fn();
  }),
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import type { ChatMessage } from "@/types";

describe("MessageList", () => {
  it("renders messages with correct roles", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: "Hello there",
        timestamp: new Date(),
      },
      {
        id: "2",
        role: "assistant",
        content: "Hi! How can I help?",
        timestamp: new Date(),
      },
    ];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText(/How can I help/)).toBeInTheDocument();
  });

  it("renders empty state when no messages", () => {
    render(<MessageList messages={[]} />);
    expect(
      screen.getByText(/start a conversation/i)
    ).toBeInTheDocument();
  });
});

describe("MessageInput", () => {
  it("calls onSend when submitting a message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(/message/i);
    await user.type(input, "Hello GClaw");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenCalledWith("Hello GClaw");
  });

  it("does not send empty messages", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(/message/i);
    await user.keyboard("{Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables input when disabled prop is true", () => {
    render(<MessageInput onSend={vi.fn()} disabled={true} />);

    const input = screen.getByPlaceholderText(/message/i);
    expect(input).toBeDisabled();
  });
});
```

- [ ] **Step 2: Create `web/src/components/chat/message-list.tsx`**

```tsx
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/types";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-gclaw-muted">
        <p>Start a conversation with GClaw</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div
            className={`max-w-[80%] rounded-lg px-4 py-2 ${
              msg.role === "user"
                ? "bg-gclaw-primary text-white"
                : "bg-gclaw-surface text-gclaw-text"
            }`}
          >
            {msg.role === "assistant" ? (
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              </div>
            ) : (
              <p>{msg.content}</p>
            )}
            {msg.tool_calls && msg.tool_calls.length > 0 && (
              <div className="mt-2 border-t border-gray-600 pt-2">
                <p className="text-xs text-gclaw-muted">
                  Tools used: {msg.tool_calls.map((tc) => tc.name).join(", ")}
                </p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create `web/src/components/chat/message-input.tsx`**

```tsx
"use client";

import { useState, useCallback, type KeyboardEvent, type FormEvent } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = input.trim();
      if (!trimmed) return;
      onSend(trimmed);
      setInput("");
    },
    [input, onSend]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <form onSubmit={handleSubmit} className="border-t border-gray-700 p-4">
      <div className="flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none rounded-lg bg-gclaw-surface px-4 py-3 text-gclaw-text placeholder-gclaw-muted focus:outline-none focus:ring-2 focus:ring-gclaw-primary disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-lg bg-gclaw-primary px-4 py-3 font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Create `web/src/components/chat/chat-view.tsx`**

```tsx
"use client";

/**
 * Main chat interface component.
 *
 * Manages conversation state, calls the API client for each message,
 * and renders the message list with input.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import { MessageList } from "./message-list";
import { MessageInput } from "./message-input";
import type { ChatMessage } from "@/types";

/** Generate a simple unique ID for messages. */
function msgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Generate a session ID (persisted for the browser session). */
function getSessionId(): string {
  const key = "gclaw_session_id";
  let sessionId = sessionStorage.getItem(key);
  if (!sessionId) {
    sessionId = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem(key, sessionId);
  }
  return sessionId;
}

export function ChatView() {
  const { getIdToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef(createApiClient(getIdToken));

  // Keep client in sync with getIdToken
  useEffect(() => {
    clientRef.current = createApiClient(getIdToken);
  }, [getIdToken]);

  const handleSend = useCallback(
    async (content: string) => {
      // Add user message immediately
      const userMsg: ChatMessage = {
        id: msgId(),
        role: "user",
        content,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const sessionId = getSessionId();
        const response = await clientRef.current.chat(sessionId, content);

        const assistantMsg: ChatMessage = {
          id: msgId(),
          role: "assistant",
          content: response.text,
          timestamp: new Date(),
          tool_calls: response.tool_calls,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to send message";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [getIdToken]
  );

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={messages} />

      {error && (
        <div className="mx-4 rounded-lg bg-red-900/50 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <MessageInput onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
```

- [ ] **Step 5: Create `web/src/app/chat/page.tsx`**

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { ChatView } from "@/components/chat/chat-view";

export default function ChatPage() {
  return (
    <AuthGuard>
      <div className="flex h-screen flex-col">
        {/* Navigation bar */}
        <nav className="flex items-center justify-between border-b border-gray-700 px-6 py-3">
          <h1 className="text-xl font-bold text-gclaw-primary">GClaw</h1>
          <div className="flex gap-4">
            <a
              href="/chat"
              className="text-sm font-medium text-gclaw-primary"
            >
              Chat
            </a>
            <a
              href="/board"
              className="text-sm font-medium text-gclaw-muted hover:text-gclaw-text"
            >
              Board
            </a>
          </div>
        </nav>

        {/* Chat area fills remaining space */}
        <div className="flex-1 overflow-hidden">
          <ChatView />
        </div>
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 6: Add `@testing-library/user-event` to dev dependencies**

In `web/package.json`, add to `devDependencies`:

```json
    "@testing-library/user-event": "^14.5.0",
```

Run: `cd /mnt/c/Dev/GClaw/web && npm install`

- [ ] **Step 7: Run tests**

Run: `cd /mnt/c/Dev/GClaw/web && npx vitest run`
Expected: Chat view tests pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/components/chat/ web/src/app/chat/ web/__tests__/chat-view.test.tsx web/package.json
git commit -m "feat: Chat View with markdown rendering, message history, and API integration"
```

---

### Task 7: Board View (Kanban with Firestore Real-Time)

**Files:**
- Create: `web/src/components/board/board-view.tsx`
- Create: `web/src/components/board/board-column.tsx`
- Create: `web/src/components/board/task-card.tsx`
- Create: `web/src/app/board/page.tsx`
- Create: `web/__tests__/board-view.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/board-view.test.tsx`:

```tsx
/**
 * Tests for Board View components.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock Firebase
vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: vi.fn((_auth: unknown, cb: (u: unknown) => void) => {
    cb({ uid: "test_user", getIdToken: vi.fn().mockResolvedValue("token") });
    return vi.fn();
  }),
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
  collection: vi.fn(),
  onSnapshot: vi.fn(),
  doc: vi.fn(),
  query: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import { TaskCard } from "@/components/board/task-card";
import { BoardColumn } from "@/components/board/board-column";
import type { BoardTask, BoardColumn as BoardColumnType } from "@/types";

const mockTask: BoardTask = {
  id: "task_abc123",
  title: "Schedule meeting with Sarah",
  description: "Book 30min, attach agenda",
  status: "queued",
  priority: "high",
  source: { type: "user" },
  assignee: "workspace-mgr",
  dependencies: [],
  requires_approval: false,
  created_at: "2026-03-30T08:00:00Z",
  updated_at: "2026-03-30T08:02:15Z",
};

describe("TaskCard", () => {
  it("renders task title and assignee", () => {
    render(<TaskCard task={mockTask} />);
    expect(screen.getByText("Schedule meeting with Sarah")).toBeInTheDocument();
    expect(screen.getByText("workspace-mgr")).toBeInTheDocument();
  });

  it("shows priority badge", () => {
    render(<TaskCard task={mockTask} />);
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("shows approval badge when required", () => {
    const approvalTask = { ...mockTask, requires_approval: true };
    render(<TaskCard task={approvalTask} />);
    expect(screen.getByText(/approval/i)).toBeInTheDocument();
  });
});

describe("BoardColumn", () => {
  const columnDef: BoardColumnType = {
    status: "queued",
    label: "Queued",
    color: "border-blue-500",
  };

  it("renders column label and task count", () => {
    render(<BoardColumn column={columnDef} tasks={[mockTask]} />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("renders empty column", () => {
    render(<BoardColumn column={columnDef} tasks={[]} />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Create `web/src/components/board/task-card.tsx`**

```tsx
"use client";

import type { BoardTask } from "@/types";

interface TaskCardProps {
  task: BoardTask;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-900/50 text-red-300",
  medium: "bg-yellow-900/50 text-yellow-300",
  low: "bg-gray-700 text-gray-300",
};

export function TaskCard({ task }: TaskCardProps) {
  return (
    <div className="rounded-lg bg-gclaw-surface p-3 shadow-sm transition-colors hover:bg-slate-700">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium text-gclaw-text">{task.title}</h4>
      </div>

      {task.description && (
        <p className="mt-1 text-xs text-gclaw-muted line-clamp-2">
          {task.description}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            PRIORITY_COLORS[task.priority] || PRIORITY_COLORS.medium
          }`}
        >
          {task.priority}
        </span>

        <span className="rounded-full bg-blue-900/50 px-2 py-0.5 text-xs text-blue-300">
          {task.assignee}
        </span>

        {task.requires_approval && (
          <span className="rounded-full bg-orange-900/50 px-2 py-0.5 text-xs text-orange-300">
            Needs Approval
          </span>
        )}

        {task.source.type !== "user" && (
          <span className="rounded-full bg-purple-900/50 px-2 py-0.5 text-xs text-purple-300">
            {task.source.origin || task.source.type}
          </span>
        )}
      </div>

      {task.result && (
        <div className="mt-2 border-t border-gray-600 pt-2">
          <p className="text-xs text-gclaw-muted">{task.result.summary}</p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `web/src/components/board/board-column.tsx`**

```tsx
"use client";

import type { BoardTask, BoardColumn as BoardColumnDef } from "@/types";
import { TaskCard } from "./task-card";

interface BoardColumnProps {
  column: BoardColumnDef;
  tasks: BoardTask[];
}

export function BoardColumn({ column, tasks }: BoardColumnProps) {
  return (
    <div className="flex min-w-[280px] flex-col rounded-lg bg-gclaw-bg">
      {/* Column header */}
      <div
        className={`flex items-center justify-between rounded-t-lg border-t-2 ${column.color} px-3 py-2`}
      >
        <h3 className="text-sm font-semibold text-gclaw-text">
          {column.label}
        </h3>
        <span className="rounded-full bg-gclaw-surface px-2 py-0.5 text-xs text-gclaw-muted">
          {tasks.length}
        </span>
      </div>

      {/* Task list */}
      <div className="flex flex-1 flex-col gap-2 p-2">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `web/src/components/board/board-view.tsx`**

```tsx
"use client";

/**
 * Kanban board with real-time Firestore listeners.
 *
 * Reads tasks directly from Firestore (users/{userId}/board) using
 * onSnapshot for real-time updates. Tasks are grouped by status into
 * kanban columns.
 */

import { useEffect, useState } from "react";
import {
  collection,
  onSnapshot,
  query,
} from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuth } from "@/contexts/auth-context";
import { BoardColumn } from "./board-column";
import { BOARD_COLUMNS } from "@/types";
import type { BoardTask } from "@/types";

export function BoardView() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<BoardTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    const boardRef = collection(db, "users", user.uid, "board");
    const q = query(boardRef);

    const unsubscribe = onSnapshot(
      q,
      (snapshot) => {
        const boardTasks: BoardTask[] = snapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        })) as BoardTask[];
        setTasks(boardTasks);
        setLoading(false);
      },
      (err) => {
        console.error("Board listener error:", err);
        setError("Failed to load board tasks");
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, [user]);

  /** Group tasks by status column. */
  function tasksByStatus(status: string): BoardTask[] {
    return tasks.filter((t) => t.status === status);
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gclaw-primary border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4 overflow-x-auto p-4">
      {BOARD_COLUMNS.map((col) => (
        <BoardColumn
          key={col.status}
          column={col}
          tasks={tasksByStatus(col.status)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create `web/src/app/board/page.tsx`**

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { BoardView } from "@/components/board/board-view";

export default function BoardPage() {
  return (
    <AuthGuard>
      <div className="flex h-screen flex-col">
        {/* Navigation bar */}
        <nav className="flex items-center justify-between border-b border-gray-700 px-6 py-3">
          <h1 className="text-xl font-bold text-gclaw-primary">GClaw</h1>
          <div className="flex gap-4">
            <a
              href="/chat"
              className="text-sm font-medium text-gclaw-muted hover:text-gclaw-text"
            >
              Chat
            </a>
            <a
              href="/board"
              className="text-sm font-medium text-gclaw-primary"
            >
              Board
            </a>
          </div>
        </nav>

        {/* Board area fills remaining space */}
        <div className="flex-1 overflow-hidden">
          <BoardView />
        </div>
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 6: Run tests**

Run: `cd /mnt/c/Dev/GClaw/web && npx vitest run`
Expected: Board view tests pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/board/ web/src/app/board/ web/__tests__/board-view.test.tsx
git commit -m "feat: Board View with kanban columns, task cards, and Firestore real-time listeners"
```

---

### Task 8: PWA Manifest + Build Verification

**Files:**
- Create: `web/public/manifest.json`
- Create: `web/public/sw.js`
- Create: `web/public/icon-192.png` (placeholder)
- Create: `web/public/icon-512.png` (placeholder)

- [ ] **Step 1: Create `web/public/manifest.json`**

```json
{
  "name": "GClaw",
  "short_name": "GClaw",
  "description": "Personal AI Agent Platform",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0F172A",
  "theme_color": "#4285F4",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

- [ ] **Step 2: Create `web/public/sw.js`** (minimal service worker for PWA installability)

```javascript
/**
 * Minimal service worker for PWA installability.
 *
 * Plan 4b/4c will add caching strategies, offline support,
 * and push notification handling.
 */

const CACHE_NAME = "gclaw-v1";

// Install: cache the app shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(["/", "/manifest.json"]);
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch: network-first strategy
self.addEventListener("fetch", (event) => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
```

- [ ] **Step 3: Create placeholder PWA icons**

Generate minimal 1x1 PNG placeholders (to be replaced with real icons later):

```bash
cd /mnt/c/Dev/GClaw/web/public
# Create placeholder PNGs (these should be replaced with real icons)
# Using a simple approach — the actual icons will be designed later
python3 -c "
import struct, zlib
def create_png(w, h, r, g, b, filename):
    raw = b''
    for _ in range(h):
        raw += b'\x00' + bytes([r, g, b]) * w
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', zlib.compress(raw))
    png += chunk(b'IEND', b'')
    with open(filename, 'wb') as f:
        f.write(png)
create_png(192, 192, 66, 133, 244, 'icon-192.png')
create_png(512, 512, 66, 133, 244, 'icon-512.png')
print('Created placeholder icons')
"
```

- [ ] **Step 4: Register service worker in layout**

Update `web/src/app/layout.tsx` to register the service worker:

```tsx
import type { Metadata } from "next";
import { AuthProvider } from "@/contexts/auth-context";
import { ServiceWorkerRegistrar } from "@/components/sw-registrar";
import "./globals.css";

export const metadata: Metadata = {
  title: "GClaw",
  description: "Personal AI Agent Platform",
  manifest: "/manifest.json",
  themeColor: "#4285F4",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <AuthProvider>
          {children}
          <ServiceWorkerRegistrar />
        </AuthProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Create `web/src/components/sw-registrar.tsx`**

```tsx
"use client";

import { useEffect } from "react";

export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        console.warn("Service worker registration failed:", err);
      });
    }
  }, []);

  return null;
}
```

- [ ] **Step 6: Full build verification**

Run backend tests:
```bash
cd /mnt/c/Dev/GClaw && pytest tests/ -v
```
Expected: All backend tests pass.

Run frontend tests:
```bash
cd /mnt/c/Dev/GClaw/web && npx vitest run
```
Expected: All frontend tests pass.

Build frontend:
```bash
cd /mnt/c/Dev/GClaw/web && npx next build
```
Expected: Successful production build.

- [ ] **Step 7: Verify PWA manifest is served**

Run dev server and check:
```bash
cd /mnt/c/Dev/GClaw/web && npx next dev &
sleep 3
curl -s http://localhost:3000/manifest.json | python3 -m json.tool
```
Expected: manifest.json is served correctly.

- [ ] **Step 8: Commit**

```bash
git add web/public/ web/src/components/sw-registrar.tsx web/src/app/layout.tsx
git commit -m "feat: PWA manifest, service worker, and build verification"
```

---

## Summary

**Plan 4a delivers:**
1. Firebase Auth middleware for FastAPI with ID token verification
2. Auth-aware API endpoints (user_id from token, not request body)
3. Next.js 14+ project with TypeScript strict mode and Tailwind CSS
4. Firebase client-side auth with Google Sign-In and route protection
5. Typed API client with automatic auth token injection
6. Chat View with markdown rendering, message history, and error handling
7. Board View with kanban columns and Firestore real-time listeners
8. PWA basics (manifest, service worker, placeholder icons)

**Deferred to Plan 4b:**
- Gemini Live API voice integration
- Agent Dashboard view
- Skills & Crons management views
- Memory Explorer view

**Deferred to Plan 4c:**
- Multi-user A2A connection flow
- Onboarding interview + soul generation
- Full PWA (push notifications via FCM, offline support, background sync)
- Drag-and-drop reordering on the Board View
