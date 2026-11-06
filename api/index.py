"""Vercel entry point; the runtime discovers the exported ASGI app."""

from backend.app.main import app

__all__ = ["app"]
