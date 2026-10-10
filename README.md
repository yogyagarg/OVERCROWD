# Crowd Management System - Production Edition

A production-ready multi-counter order-workload system with Gemma 4 AI assistance, PostgreSQL database, and full deployment pipeline.

## Overview

This system implements a complete crowd management platform that combines:
- **Public queue display**: Aggregate active order counts with stale-state detection
- **Staff workspace**: Full order lifecycle management (PENDING → PREPARING → READY → COMPLETED)
- **AI Operations Assistant**: Gemma 4-powered natural-language queries with tool calling
- **AI-assisted order drafting**: Convert natural language to structured drafts with validation
- **Operational reports**: AI-narrated summaries of recorded activity

## Architecture

```
crowd-management/
├── app/                      # FastAPI application
│   ├── main.py              # Main application entry point
│   ├── core/                # Core configuration and security
│   │   ├── config.py        # Settings management
│   │   └── security.py      # Auth and RBAC
│   ├── db/                  # Database models and session management
│   ├── api/                 # API routes (v1)
│   │   ├── v1/__init__.py   # Router assembly
│   │   ├── auth.py          # Login/register endpoints
│   │   ├── counters.py      # Counter management
│   │   ├── orders.py        # Order CRUD and status transitions
│   │   ├── ai.py            # Gemma 4 AI assistant
│   │   ├── reports.py       # Reporting and analytics
│   │   ├── menu.py          # Menu item management
│   │   └── public.py        # Public queue endpoints
│   └── schemas/             # Pydantic request/response models
├── services/                # Business logic services
│   ├── ai/                  # Gemma 4 service integration
│   └── queue/               # Queue management and status logic
├── infra/                   # Deployment infrastructure
│   ├── Dockerfile.web       # Frontend container
│   ├── Dockerfile.api       # API container
│   └── deployment/          # Provider-specific configs
├── docs/                    # Project documentation
├── requirements.txt         # Python dependencies
├── requirements-dev.txt     # Development dependencies
├── .env.example            # Environment configuration template
├── docker-compose.yml       # Local development environment
├── run_windows.bat         # Windows launcher (POC compatibility)
└── README.md               # This file
```

## Quick Start

### Prerequisites
- Python 3.12 or newer
- PostgreSQL 13 or newer
- Redis 7 or newer (for SSE and caching)
- Docker and Docker Compose (for containerized deployment)

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repo-url>
   cd crowd-management
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Install dependencies**:
   ```bash
   python -m pip install -r requirements.txt
   ```

3. **Set up database**:
   ```bash
   createdb crowd_management
   # Apply migrations or let SQLAlchemy create tables
   python -c "from app.db.database import engine from app.db.Models import Base; Base.metadata.create_all(bind=engine)"
   ```

4. **Run the application**:
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Access the system**:
   - API: http://127.0.0.1:8000
   - Docs: http://127.0.0.1:8000/api/docs
   - Public queue: http://127.0.0.1:8000/api/v1/public/counters/{slug}/queue
   - Admin: Authenticate and use /api/v1/ endpoints

### Docker Deployment

```bash
docker-compose up -d
# Or build and run individually
docker build -t crowd-api -f infra/Dockerfile.api .
docker build -t crowd-web -f infra/Dockerfile.web .
docker-compose up -d
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Staff login
- `POST /api/v1/auth/register` - Register new user (admin only)
- `GET /api/v1/auth/me` - Get current user info
- `POST /api/v1/auth/refresh` - Refresh access token

### Counters
- `GET /api/v1/counters/` - List counters
- `POST /api/v1/counters/` - Create counter (admin)
- `GET /api/v1/counters/{counter_id}` - Get counter
- `PATCH /api/v1/counters/{counter_id}` - Update counter (admin)

### Orders
- `POST /api/v1/orders/` - Create order
- `PATCH /api/v1/orders/{order_id}/status` - Update status
- `PATCH /api/v1/orders/{order_id}/cancel` - Cancel order
- `GET /api/v1/orders/` - List orders
- `GET /api/v1/orders/{order_id}` - Get order

### AI Assistant
- `POST /api/v1/ai/assistant` - AI operations assistant
- `POST /api/v1/ai/order-draft` - AI-assisted order draft
- `POST /api/v1/ai/report` - AI operational report

### Menu
- `GET /api/v1/menu/` - List menu items
- `POST /api/v1/menu/` - Create menu item
- `GET /api/v1/menu/{item_id}` - Get menu item
- `PATCH /api/v1/menu/{item_id}` - Update menu item

### Public Queue
- `GET /api/v1/public/counters/{counter_slug}/queue` - Aggregate count
- `GET /api/v1/public/counters/{counter_slug}/queue/events` - SSE stream
- `GET /api/v1/public/counters` - List public counters

## Security

- **Authentication**: JWT bearer tokens with HS256 algorithm
- **Authorization**: Role-based access control (platform_admin > organization_admin > counter_manager > cashier)
- **Counter isolation**: Users can only access counters they have explicit permission for
- **Input validation**: All requests validated via Pydantic schemas
- **SQL injection prevention**: All queries use parameterized SQL via SQLAlchemy
- **XSS protection**: Secure headers, output encoding
- **CSRF protection**: Cookie-based sessions with SameSite=Lax

## Gemma AI Integration

The system integrates Gemma 4 as an interpretation layer:
- **Tool calling**: Gemma can call approved backend tools for database facts
- **Permission enforcement**: All tool calls validated against user scope
- **Hallucination prevention**: Model must say when data is unavailable
- **Audit logging**: Every AI action recorded with outcome and details
- **Fallback**: Manual order creation works even when Gemma is unavailable

## Production Checklist

- [ ] Domain, HTTPS, and secure headers verified
- [ ] Database migrations applied and tested
- [ ] Backup schedule and restore drill completed
- [ ] Auth, role checks, and counter isolation tested
- [ ] Status transitions and concurrent updates tested
- [ ] Idempotency behavior tested
- [ ] Public responses inspected for data leakage
- [ ] SSE disconnection and stale-state behavior tested
- [ ] AI endpoint timeout, quota, and failure behavior tested
- [ ] AI-generated order requires explicit cashier confirmation
- [ ] Logs exclude keys, passwords, tokens
- [ ] Monitoring, alerting, and incident contact defined
- [ ] Rollback strategy and migration safety reviewed
- [ ] PWA install and update tested on target browsers
- [ ] Inference API keys in server-side secrets only
- [ ] Rate limits and provider quotas configured

## License

This project is licensed under the MIT License.