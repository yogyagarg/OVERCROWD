# Application Configuration
# Production-ready settings with environment variable overrides

import os
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Crowd Management System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = int(os.getenv("WORKERS", "1"))
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 30 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # Database
    DATABASE_URL: str = Field(
        ..., 
        env="DATABASE_URL",
        description="PostgreSQL connection string"
    )
    
    # Redis (for caching, queues, SSE)
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        env="REDIS_URL"
    )
    
    # Gemma AI
    GEMMA_API_KEY: str = Field(..., env="GEMMA_API_KEY")
    GEMMA_PROVIDER: str = "openrouter"  # or "vertexai", "self-hosted"
    GEMMA_MODEL: str = "gemma-4"
    GEMMA_TIMEOUT_SECONDS: int = 30
    GEMMA_MAX_OUTPUT_TOKENS: int = 1000
    
    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8080",
        "https://your-domain.example",
    ]
    
    # Feature flags
    AI_ASSISTANT_ENABLED: bool = True
    SSE_ENABLED: bool = True
    PUBLIC_QUEUE_ENABLED: bool = True
    
    # Order settings
    MAX_ORDER_ITEMS: int = 50
    MAX_QUEUE_COUNT_CACHE_TTL: int = 30  # seconds
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()