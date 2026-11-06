from fastapi import FastAPI

from backend.app.auth.routes import router as auth_router

app = FastAPI(title="MemoCard AI API")
app.include_router(auth_router, prefix="/api")
