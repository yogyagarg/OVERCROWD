# Counter Routes
# Service counter management endpoints

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional

from ...db.database import get_db
from ...db.models import User, ServiceCounter, Organization
from ...core.security import get_current_user, check_role
from ...schemas import (
    ServiceCounterCreate,
    ServiceCounterUpdate,
    ServiceCounterResponse,
)
from ...core.config import settings

router = APIRouter(prefix="/counters", tags=["counters"])


@router.get("/", response_model=List[ServiceCounterResponse], tags=["counters"])
async def list_counters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    public_only: bool = False,
):
    """List service counters the user has access to."""
    query = db.query(ServiceCounter)
    
    if public_only:
        query = query.filter(ServiceCounter.is_public == True)
    
    # Filter by user's accessible counters
    if current_user.role.value in ["platform_admin", "organization_admin"]:
        counters = query.all()
    else:
        # Users can only access counters they have access to
        counters = query.filter(
            ServiceCounter.id.in_(current_user.accessible_counter_ids)
        ).all()
    
    return counters


@router.post(
    "/",
    response_model=ServiceCounterResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["counters"],
)
async def create_counter(
    counter_data: ServiceCounterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new service counter (platform/admin only)."""
    # Check permissions
    if current_user.role not in [
        "platform_admin",
        "organization_admin",
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create counters",
        )
    
    # Check if slug already exists in organization
    existing = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.slug == counter_data.slug)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A counter with this slug already exists in the organization",
        )
    
    # Create counter
    from sqlalchemy import event
    
    counter = ServiceCounter(
        name=counter_data.name,
        slug=counter_data.slug,
        organization_id=counter_data.organization_id,
        timezone=counter_data.timezone,
        is_public=counter_data.is_public,
        capacity=counter_data.capacity,
    )
    
    db.add(counter)
    db.commit()
    db.refresh(counter)
    
    # Grant organization admin or platform admin access to the counter
    if current_user.role == "organization_admin":
        from ...db.models import StaffCounterAccess
        access = StaffCounterAccess(
            staff_user_id=current_user.id,
            service_counter_id=counter.id,
            counter_role="manager",
        )
        db.add(access)
    
    db.commit()
    
    return counter


@router.get(
    "/{counter_id}",
    response_model=ServiceCounterResponse,
    tags=["counters"],
)
async def get_counter(
    counter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific counter by ID."""
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
    
    # Check access
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
    
    return counter


@router.patch(
    "/{counter_id}",
    response_model=ServiceCounterResponse,
    tags=["counters"],
)
async def update_counter(
    counter_id: int,
    counter_data: ServiceCounterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a service counter."""
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
    
    # Check permissions - only org admins or platform admins can update
    if current_user.role not in ["platform_admin", "organization_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    
    # Update fields
    update_data = counter_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(counter, field, value)
    
    db.commit()
    db.refresh(counter)
    
    return counter


@router.delete("/{counter_id}", tags=["counters"])
async def delete_counter(
    counter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a service counter (admin only)."""
    if current_user.role not in ["platform_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can delete counters",
        )
    
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
    
    # Check for dependent orders
    from sqlalchemy import func
    order_count = (
        db.query(func.count(Order.id))
        .filter(Order.service_counter_id == counter_id)
        .scalar()
    )
    
    if order_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete counter: {order_count} orders exist",
        )
    
    db.delete(counter)
    db.commit()
    
    return {"detail": "Counter deleted successfully"}