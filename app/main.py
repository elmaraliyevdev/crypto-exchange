"""FastAPI application entrypoint: app instance, lifespan, and global middleware."""

from fastapi import FastAPI

from app.api.v1.router import api_router

app = FastAPI(title="Crypto Exchange API")

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}
