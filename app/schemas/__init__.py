# Pydantic Schemas
# Request/response schemas for the API

from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, validator
import enum


# Enum types for schemas
class UserRole(str, enum.Enum):
    platform_admin = "platform_admin"
    organization_admin = "organization_admin"
    counter_manager = "counter_manager"
    cashier = "cashier"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    preparing = "preparing"
    ready_for_pickup = "ready_for_pickup"
    completed = "completed"
    cancelled = "cancelled"


class OrderSource(str, enum.Enum):
    manual = "manual"
    ai_assisted = "ai_assisted"


class MenuItemCategory(str, enum.Enum):
    food = "food"
    beverage = "beverage"
    equipment = "equipment"
    other = "other"


class CounterRole(str, enum.Enum):
    manager = "manager"
    cashier = "cashier"
    viewer = "viewer"


# ---- Authentication Schemas ----

class UserLogin(BaseModel):
    email: email_str = Field(..., description="Staff email address")
    password: str = Field(..., min_length=8, description="Staff password")

    @validator("password")
    def password_must_be_valid(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserRegister(BaseModel):
    email: email_str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")
    display_name: str = Field(..., min_length=1, max_length=100, display_name="Display name")
    role: Optional[UserRole] = Field(
        default="cashier", description="User role"
    )
    organization_id: Optional[int] = Field(
        default=None, description="Organization ID"
    )


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    user: "UserInfo" = Field(..., description="User information")


class UserInfo(BaseModel):
    id: int = Field(..., description="User ID")
    email: email_str = Field(..., description="User email")
    display_name: str = Field(..., description="Display name")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether user is active")
    is_superuser: bool = Field(default=False, description="Whether user is superuser")
    accessible_counter_ids: List[int] = Field(
        default_factory=list, description=" accessible counter IDs"
    )

    organization_id: Optional[int] = Field(
        default=None, description="Organization ID"
    )

    class Config:
        from_attributes = True


# ---- Counter Schemas ----

class ServiceCounterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Counter name")
    slug: str = Field(
        ..., 
        min_length=1, 
        max_length=50, 
        description="Counter slug (unique within organization)"
    )
    organization_id: int = Field(
        ..., description="Organization ID"
    )
    timezone: str = Field(
        ..., description="IANA time-zone name"
    )
    is_public: bool = Field(
        default=False, description="Whether aggregate count is exposed publicly"
    )
    capacity: Optional[int] = Field(
        default=None, description="Maximum concurrent orders"
    )


class ServiceCounterUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    slug: Optional[str] = Field(default=None, max_length=50)
    timezone: Optional[str] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    is_public: Optional[bool] = Field(default=None)
    capacity: Optional[int] = Field(default=None)


class ServiceCounterResponse(ServiceCounterCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    total_orders: int = Field(default=0, description="Total orders ever created")
    active_orders: int = Field(
        default=0, description="Currently active orders"
    )

    class Config:
        from_attributes = True


# ---- Order Schemas ----

class OrderItemCreate(BaseModel):
    menu_item_id: int = Field(..., description="Menu item ID")
    quantity: int = Field(
        ..., gt=0, description="Item quantity (must be > 0)"
    )
    item_notes: Optional[str] = Field(
        default=None, max_length=500, description="Optional item notes"
    )


class OrderItemResponse(BaseModel):
    id: int
    menu_item_id: int
    item_name_snapshot: str
    quantity: int
    item_notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    """Create a new order."""
    counter_id: int = Field(..., description="Service counter ID")
    items: List[OrderItemCreate] = Field(
        ..., 
        min_items=1, 
        max_items=50,
        description="Order items (1-50 items)"
    )
    source: OrderSource = Field(
        default=OrderSource.manual, description="Order source"
    )
    business_date: Optional[date] = Field(
        default=None, description="Business date (counter timezone)"
    )
    idempotency_key: Optional[str] = Field(
        default=None, max_length=128, description="Idempotency key for retries"
    )


class OrderUpdateStatus(BaseModel):
    """Update order status."""
    new_status: OrderStatus = Field(
        ..., description="New order status"
    )
    reason: Optional[str] = Field(
        default=None, max_length=500, description="Optional reason for transition"
    )


class OrderResponse(BaseModel):
    """Complete order response with items."""
    id: int
    order_number: Optional[str] = None
    business_date: Optional[date] = None
    status: OrderStatus
    source: OrderSource
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = Field(default_factory=list)
    total_items: int = Field(default=0, description="Total item count")
    total_price: Optional[float] = Field(
        default=None, description="Total order price"
    )
    ready_at: Optional[datetime] = Field(
        default=None, description="When order was set ready"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When order was completed"
    )
    cancelled_at: Optional[datetime] = Field(
        default=None, description="When order was cancelled"
    )

    class Config:
        from_attributes = True


# ---- Menu Schemas ----

class MenuItemCreate(BaseModel):
    """Create a new menu item."""
    name: str = Field(..., min_length=1, max_length=200, description="Menu item name")
    category: MenuItemCategory = Field(
        default=MenuItemCategory.other, description="Item category"
    )
    is_available: bool = Field(
        default=True, description="Whether item is currently available"
    )
    preparation_time_minutes: Optional[int] = Field(
        default=15, ge=1, description="Preparation time in minutes"
    )
    price: Optional[str] = Field(
        default=None, max_length=20, description="Optional price"
    )
    description: Optional[str] = Field(
        default=None, max_length=500, description="Optional description"
    )
    aliases: Optional[List[str]] = Field(
        default=None, description="Optional aliases for matching"
    )


class MenuItemUpdate(BaseModel):
    """Update a menu item."""
    name: Optional[str] = Field(default=None, max_length=200)
    category: Optional[MenuItemCategory] = Field(default=None)
    is_available: Optional[bool] = Field(default=None)
    preparation_time_minutes: Optional[int] = Field(default=None)
    price: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)
    aliases: Optional[List[str]] = Field(default=None)


class MenuItemResponse(MenuItemCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    counter_id: int

    class Config:
        from_attributes = True


# ---- AI Assistant Schemas ----

class GemmaToolCall(BaseModel):
    """Structured tool call from Gemma 4."""
    tool_name: str = Field(..., description="Name of the approved tool")
    arguments: Dict[str, Any] = Field(
        ..., 
        description="Validated tool arguments"
    )
    tool_call_id: str = Field(
        ..., description="Unique tool call identifier"
    )


class GemmaAssistantRequest(BaseModel):
    """Request to Gemma 4 AI assistant."""
    question: str = Field(..., description="Staff question or request")
    scope: Optional[str] = Field(
        default=None, description="Scope (counter ID, organization ID)"
    )
    feature: str = Field(
        default="assistant", description="Feature flag"
    )


class GemmaAssistantResponse(BaseModel):
    """Response from Gemma 4 AI assistant."""
    answer: str = Field(..., description="Natural language answer")
    used_tools: List[GemmaToolCall] = Field(
        default_factory=list, description="Tools that were called"
    )
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score"
    )
    data_as_of: Optional[datetime] = Field(
        default=None, description="When the data is from"
    )


# ---- Public Queue Schemas ----

class PublicQueueResponse(BaseModel):
    """Public queue aggregate response."""
    counter_id: int = Field(..., description="Counter ID")
    counter_slug: str = Field(..., description="Counter slug/name")
    active_orders: int = Field(
        ..., ge=0, description="Number of active orders"
    )
    state: str = Field(
        default="live", description="Service state: live/stale/error"
    )
    updated_at: datetime = Field(
        ..., description="When count was last updated"
    )
    stale_since: Optional[datetime] = Field(
        default=None, description="When data became stale"
    )


class PublicQueueStats(BaseModel):
    """Public queue statistics over time."""
    counter_id: int
    time_window: str  # "1h", "6h", "24h", "7d"
    orders_created: int = Field(default=0, ge=0)
    orders_completed: int = Field(default=0, ge=0)
    orders_cancelled: int = Field(default=0, ge=0)
    peak_active_count: int = Field(default=0, ge=0)
    average_active_count: float = Field(default=0.0, ge=0.0)


# ---- Report Schemas ----

class ReportRequest(BaseModel):
    """Request for a report."""
    counter_id: int = Field(..., description="Counter ID")
    start_date: date = Field(..., description="Report start date")
    end_date: date = Field(..., description="Report end date")
    include_charts: bool = Field(
        default=True, description="Include chart data"
    )
    format: str = Field(
        default="summary", description="Report format: summary/detailed"
    )


class ReportMetrics(BaseModel):
    """Report metrics result."""
    period_start: date
    period_end: date
    orders_created: int = Field(default=0, ge=0)
    orders_completed: int = Field(default=0, ge=0)
    orders_cancelled: int = Field(default=0, ge=0)
    orders_pending: int = Field(default=0, ge=0)
    orders_preparing: int = Field(default=0, ge=0)
    orders_ready_for_pickup: int = Field(default=0, ge=0)
    average_service_time_minutes: Optional[float] = Field(
        default=None, ge=0
    )
    peak_active_count: int = Field(default=0, ge=0)
    average_active_count: float = Field(
        default=0.0, ge=0.0
    )