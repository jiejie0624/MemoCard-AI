from fastapi import FastAPI

from backend.app.auth.routes import router as auth_router
from backend.app.review.routes import router as review_router

app = FastAPI(title="MemoCard AI API")
app.include_router(auth_router, prefix="/api")
app.include_router(review_router, prefix="/api")
