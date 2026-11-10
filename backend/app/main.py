from fastapi import FastAPI

from backend.app.auth.routes import router as auth_router
from backend.app.calendar.routes import router as calendar_router
from backend.app.chat.routes import router as chat_router
from backend.app.dashboard.routes import router as dashboard_router
from backend.app.documents.routes import router as documents_router
from backend.app.flashcards.routes import router as flashcards_router
from backend.app.review.routes import router as review_router

app = FastAPI(title="MemoCard AI API")
app.include_router(auth_router, prefix="/api")
app.include_router(calendar_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(flashcards_router, prefix="/api")
app.include_router(review_router, prefix="/api")
