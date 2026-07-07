"""
Slancio Crypto Algo Treding Engine — FastAPI Application Entry Point
======================================================
Combines the backend API and serves the frontend Web App.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from core.config import get_settings
from backend.auth.router import router as auth_router
from backend.users.router import router as users_router
from backend.admin.router import router as admin_router
from backend.scheduler import start_scheduler
from database.connection import init_db_schema

settings = get_settings()

app = FastAPI(
    title="Slancio Crypto Algo Treding Engine",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)


@app.on_event("startup")
async def startup_event():
    """Initialize DB on startup — works for both SQLite (dev) and PostgreSQL (Neon)"""
    logger.info("Starting up Slancio Crypto Algo Engine Backend...")
    await init_db_schema()  # Safe for both SQLite and Postgres — skips existing tables
    start_scheduler()  # Start the fully autonomous background scheduler!


@app.get("/api/health")
async def health_check():
    """Endpoint for Render/Uptime monitors to ping every 10 mins"""
    return {"status": "healthy", "engine": "running"}


# ── UNIFIED RENDER DEPLOYMENT ──
# Mount the React/Vue frontend static files. 
# This assumes you have built your frontend into the /public directory.

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")

if os.path.exists(PUBLIC_DIR):
    # Mount everything else (js, css, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(PUBLIC_DIR, "assets")), name="assets")
    
    # Catch-all route to serve index.html for SPA client-side routing
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Prevent capturing /api routes
        if full_path.startswith("api/"):
            return None
        return FileResponse(os.path.join(PUBLIC_DIR, "index.html"))
else:
    logger.warning(f"Public directory '{PUBLIC_DIR}' not found. Only API routes will be served.")
