# Reports Routes
# Reporting and analytics endpoints

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional, Dict, Any

from ...db.database import get_db
from ...db.models import User, ServiceCounter, Order, OrderStatus, OrderItem, MenuItem
from ...core.security import get_current_user
from ...schemas import (
    ReportRequest,
    ReportMetrics,
    ReportRequest as ReportSchema,
)
from datetime import date, datetime
from collections import defaultdict


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "/summary",
    response_model=ReportMetrics,
    status_code=status.HTTP_200_OK,
    tags=["reports"],
)
async def get_report_summary(
    report_request: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get report summary for a counter and time period."""
    counter_id = report_request.counter_id
    start_date = report_request.start_date
    end_date = report_request.end_date
    
    # Check user has access to counter
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == counter_id)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
    
    # Build query filter
    # Orders within the date range (business_date)
    query = db.query(Order).filter(
        Order.organization_id == counter.organization_id,
        Order.business_date >= start_date.isoformat(),
        Order.business_date <= end_date.isoformat(),
    )
    
    # If specific counter, filter further
    if counter_id:
        query = query.filter(Order.service_counter_id == counter_id)
    
    # Get counts by status
    status_counts = (
        query.with_entities(
            Order.status,
            func.count(Order.id).label("count"),
        )
        .group_by(Order.status)
        .all()
    )
    
    # Initialize metrics
    metrics = ReportMetrics(
        period_start=start_date,
        period_end=end_date,
        orders_created=0,
        orders_completed=0,
        orders_cancelled=0,
        orders_pending=0,
        orders_preparing=0,
        orders_ready_for_pickup=0,
    )
    
    # Populate metrics from query results
    for status_obj, count in status_counts:
        status_name = status_obj.value if hasattr(status_obj, 'value') else str(status_obj)
        if hasattr(metrics, f"orders_{status_name}"):
            setattr(metrics, f"orders_{status_name}", count)
    
    # Set created count (all orders)
    metrics.orders_created = (
        query.count()
        # Actually we need to count all orders regardless of status for "created"
        # Let's use a separate query
    )
    
    # Get total order count
    metrics.orders_created = (
        db.query(func.count(Order.id))
        .filter(
            Order.organization_id == counter.organization_id,
            Order.business_date >= start_date.isoformat(),
            Order.business_date <= end_date.isoformat(),
        )
        .scalar()
    )
    
    # Calculate average service time from completed orders with ready/completed timestamps
    completed_orders = (
        db.query(Order)
        .filter(
            Order.service_counter_id == counter_id,
            Order.status == OrderStatus.completed,
            Order.completed_at.isnot(None),
            Order.ready_at.isnot(None),
        )
        .all()
    )
    
    if completed_orders:
        total_time = sum(
            (o.completed_at - o.ready_at).total_seconds() / 60
            for o in completed_orders
            if o.ready_at and o.completed_at
        )
        metrics.average_service_time_minutes = (
            total_time / len(completed_orders)
            if completed_orders
            else None
        )
    
    # Calculate peak and average active counts
    # This is a simplified calculation - in production would use proper window functions
    daily_counts = (
        db.query(
            func.date_order(business_date).label("day"),
            func.count(Order.id).label("daily_count"),
        )
        .filter(
            Order.service_counter_id == counter_id,
            Order.business_date >= start_date.isoformat(),
            Order.business_date <= end_date.isoformat(),
            Order.status.in_(
                [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
            ),
        )
        .group_by(func.date_order(business_date))
        .all()
    )
    
    if daily_counts:
        counts = [c.daily_count for c in daily_counts]
        metrics.peak_active_count = max(counts) if counts else 0
        metrics.average_active_count = (
            sum(counts) / len(counts) if counts else 0.0
        )
    else:
        metrics.peak_active_count = 0
        metrics.average_active_count = 0.0
    
    return metrics


@router.get(
    "/counter/{counter_id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    tags=["reports"],
)
async def get_counter_report(
    counter_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed report for a counter."""
    # Check access
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == counter_id)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
    
    # Get orders in date range
    orders = (
        db.query(Order)
        .filter(
            Order.service_counter_id == counter_id,
            Order.business_date >= start_date.isoformat(),
            Order.business_date <= end_date.isoformat(),
        )
        .order_by(Order.created_at.desc())
        .limit(100)
        .all()
    )
    
    # Calculate metrics
    total_orders = len(orders)
    completed = sum(1 for o in orders if o.status == OrderStatus.completed)
    cancelled = sum(1 for o in orders if o.status == OrderStatus.cancelled)
    pending_preparing = sum(
        1 for o in orders 
        if o.status in [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
    )
    
    # Status distribution
    status_distribution = {}
    for status_enum in OrderStatus:
        count = sum(1 for o in orders if o.status == status_enum)
        if count > 0:
            status_distribution[status_enum.value] = count
    
    # Hourly distribution
    hourly = defaultdict(int)
    for o in orders:
        if o.created_at:
            hour = o.created_at.hour
            hourly[hour] += 1
    
    # Daily distribution
    daily = defaultdict(int)
    for o in orders:
        if o.business_date:
            daily[o.business_date] += 1
    
    return {
        "counter_id": counter_id,
        "counter_name": counter.name,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "total_orders": total_orders,
            "completed": completed,
            "cancelled": cancelled,
            "active": pending_preparing,
            "completion_rate": round(completed / total_orders * 100, 2)
            if total_orders > 0
            else 0,
        },
        "status_distribution": status_distribution,
        "hourly_distribution": dict(sorted(hourly.items())),
        "daily_distribution": dict(
            sorted(daily.items(), key=lambda x: x[0], reverse=True)
        ),
    }


@router.get(
    "/{counter_id}/queue-count",
    response_model=int,
    status_code=status.HTTP_200_OK,
    tags=["reports"],
)
async def get_queue_count(
    counter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current active order count for a counter."""
    # Check access
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == counter_id)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
    
    # Count active orders (pending, preparing, ready_for_pickup)
    active_count = (
        db.query(func.count(Order.id))
        .filter(
            Order.service_counter_id == counter_id,
            Order.status.in_(
                [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
            ),
        )
        .scalar()
    )
    
    return active_count or 0