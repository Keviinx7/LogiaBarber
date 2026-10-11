from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.public import router as public_router

app = FastAPI(title="Sistema de Gestión para Logia Barber", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(public_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
