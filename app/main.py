# Main FastAPI Application - Crowd Management System
# Production-ready, deployment-ready architecture

import os
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import asyncio

from .db.database import get_db, engine, Base
from .db.models import User, Counter, Order, OrderStatus, OrderItem, MenuItem
from .api.v1.routes import api_router
from .core.config import settings
from .core.security import authenticate_user, create_access_token, get_current_user
from .services.ai.gemma import GemmaService
from .services.queue import queue_service

# Initialize database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Crowd Management System",
    description="Production-ready multi-counter order-workload system with Gemma 4 AI assistance",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS configuration - production origins only
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# API v1 router
app.include_router(api_router, prefix="/api/v1")

# Health check endpoint
@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
    }

# Root endpoint
@app.get("/", tags=["system"])
async def root():
    return {
        "message": "Crowd Management System API",
        "docs": "/api/docs",
        "version": "2.0.0",
    }

# Gemma AI service health
@app.get("/ai/health", tags=["ai"])
async def ai_health():
    gemma = GemmaService()
    return await gemma.health_check()