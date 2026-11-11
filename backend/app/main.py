import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.analytics.routes import router as analytics_router
from backend.app.auth.routes import router as auth_router
from backend.app.calendar.routes import router as calendar_router
from backend.app.chat.routes import router as chat_router
from backend.app.dashboard.routes import router as dashboard_router
from backend.app.documents.routes import router as documents_router
from backend.app.flashcards.routes import router as flashcards_router
from backend.app.review.routes import router as review_router

app = FastAPI(title="MemoCard AI API")
frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
if frontend_origins:
    # Credentialed CORS is restricted to explicitly configured frontend origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

@app.middleware("http")
async def reject_untrusted_browser_origins(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        frontend_origins
        and origin
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and origin not in frontend_origins
    ):
        return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
    return await call_next(request)

app.include_router(analytics_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(calendar_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(flashcards_router, prefix="/api")
app.include_router(review_router, prefix="/api")
