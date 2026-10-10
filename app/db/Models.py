# Database Models
# All ORM models for the Crowd Management System
# Uses declarative base from database module

from datetime import datetime
from sql import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SQLEnum,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

import enum


# Enum types
class UserRole(enum.Enum):
    platform_admin = "platform_admin"
    organization_admin = "organization_admin"
    counter_manager = "counter_manager"
    cashier = "cashier"


class OrderStatus(enum.Enum):
    pending = "pending"
    preparing = "preparing"
    ready_for_pickup = "ready_for_pickup"
    completed = "completed"
    cancelled = "cancelled"


class OrderSource(enum.Enum):
    manual = "manual"
    ai_assisted = "ai_assisted"


class MenuItemCategory(enum.Enum):
    food = "food"
    beverage = "beverage"
    equipment = "equipment"
    other = "other"


class OrderStatusHistoryStatus(enum.Enum):
    active = "active"
    suspended = "suspended"


# Base class will be set after import in database module
# This file defines the model classes that inherit from Base


class Base:
    """Placeholder - actual Base is created in database.py"""
    pass


# ---- Models ----

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.cashier, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    # Relationships (lazy-loaded)
    organization = relationship("Organization", back_populates="users")
    counter_access = relationship("StaffCounterAccess", back_populates="user")
    created_orders = relationship("Order", back_populates="created_by", foreign_keys="Order.created_by_staff_user_id")
    ai_action_audit = relationship("AiActionAudit", back_populates="staff_user")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="active", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)

    counters = relationship("ServiceCounter", back_populates="organization")
    users = relationship("User", back_populates="organization")


class ServiceCounter(Base):
    __tablename__ = "service_counters"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    name = Column(String, nullable=False)
    slug = Column(String, index=True, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    timezone = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    capacity = Column(Integer, nullable=True)

    organization = relationship("Organization", back_populates="counters")
    menu_items = relationship("MenuItem", back_populates="counter")
    orders = relationship("Order", back_populates="counter")
    order_status_history = relationship("OrderStatusHistory", back_populates="counter")


class StaffCounterAccess(Base):
    __tablename__ = "staff_counter_access"

    id = Column(Integer, primary_key=True, index=True)
    staff_user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    service_counter_id = Column(Integer, ForeignKey("service_counters.id"), primary_key=True)
    counter_role = Column(String, nullable=True)  # manager, cashier, viewer

    user = relationship("User", back_populates="counter_access")
    counter = relationship("ServiceCounter", back_populates="counter_access")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    name = Column(String, nullable=False)
    normalized_name = Column(String, index=True, nullable=False)
    category = Column(SQLEnum(MenuItemCategory), default=MenuItemCategory.other, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    aliases = Column(JSON, nullable=True, default=list)
    description = Column(Text, nullable=True)
    preparation_time_minutes = Column(Integer, nullable=True, default=15)
    price = Column(String, nullable=True)

    counter_id = Column(Integer, ForeignKey("service_counters.id"), nullable=False)

    counter = relationship("ServiceCounter", back_populates="menu_items")
    order_items = relationship("OrderItem", back_populates="menu_item")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    order_number = Column(String, nullable=True, comment="Human-readable order number")
    business_date = Column(String, nullable=True, comment="Date in counter's timezone")
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.pending, nullable=False)
    source = Column(SQLEnum(OrderSource), default=OrderSource.manual, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)

    # Tenant filtering
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    service_counter_id = Column(Integer, ForeignKey("service_counters.id"), nullable=False)
    created_by_staff_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamps
    ready_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Relationships
    counter = relationship("ServiceCounter", back_populates="orders")
    created_by = relationship("User", back_populates="created_orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
    )

    __table_args__ = (
        UniqueConstraint(
            "service_counter_id",
            "business_date",
            "order_number",
            name="uq_order_number_scope",
        ),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    order_id = Column(Integer, ForeignKey("orders.id"), primary_key=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), primary_key=True)
    item_name_snapshot = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    item_notes = Column(Text, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_quantity_positive"),
    )

    # Relationships
    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    old_status = Column(SQLEnum(OrderStatus), nullable=True)
    new_status = Column(SQLEnum(OrderStatus), nullable=False)
    changed_by_staff_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_type = Column(String, default="staff", nullable=False)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    order = relationship("Order", back_populates="status_history")
    changed_by = relationship("User", back_populates="organization")  # General relationship


class AiActionAudit(Base):
    __tablename__ = "ai_action_audit"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    staff_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_counter_id = Column(Integer, ForeignKey("service_counters.id"), nullable=False)
    feature = Column(String, nullable=False)  # "assistant"/"order_draft"/"report"
    action_name = Column(String, nullable=False)
    outcome = Column(String, default="success", nullable=False)  # success/denied/validation_error/provider_error
    request_id = Column(String, nullable=True, index=True)
    outcome_details = Column(JSON, nullable=True)

    # Relationships
    staff_user = relationship("User", back_populates="ai_action_audit")
    counter = relationship("ServiceCounter", back_populates="ai_audit_logs")