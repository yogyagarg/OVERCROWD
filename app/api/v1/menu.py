# Menu Routes
# Menu item management endpoints

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from ...db.database import get_db
from ...db.models import User, ServiceCounter, MenuItem
from ...core.security import get_current_user, check_role
from ...schemas import (
    MenuItemCreate,
    MenuItemUpdate,
    MenuItemResponse,
)


router = APIRouter(prefix="/menu", tags=["menu"])


@router.get(
    "/",
    response_model=List[MenuItemResponse],
    status_code=status.HTTP_200_OK,
    tags=["menu"],
)
async def list_menu_items(
    counter_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List menu items for a counter."""
    query = db.query(MenuItem)
    
    if counter_id:
        # Check counter exists and user has access
        from ...db.models import ServiceCounter
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
        if current_user.role not in [
            "platform_admin",
            "organization_admin",
        ] and counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
        query = query.filter(MenuItem.counter_id == counter_id)
    
    # Filter by accessibility
    if current_user.role not in ["platform_admin", "organization_admin"]:
        query = query.filter(MenuItem.counter_id.in_(current_user.accessible_counter_ids))
    
    items = query.all()
    return items


@router.post(
    "/",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["menu"],
)
async def create_menu_item(
    menu_data: MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new menu item."""
    # Check permissions - counter managers and above can create items for their counters
    if current_user.role not in ["platform_admin", "organization_admin", "counter_manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create menu items",
        )
    
    # If counter_id specified, verify access
    if menu_data.counter_id:
        counter = (
            db.query(ServiceCounter)
            .filter(ServiceCounter.id == menu_data.counter_id)
            .first()
        )
        if not counter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter not found",
            )
        if current_user.role.value != "platform_admin":
            if counter.id not in current_user.accessible_counter_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have access to this counter",
                )
    
    # Check if normalized name already exists for this counter
    normalized_check = menu_data.name.lower().replace(" ", "_")
    existing = (
        db.query(MenuItem)
        .filter(
            MenuItem.counter_id == menu_data.counter_id,
            MenuItem.normalized_name == normalized_check,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A menu item with this name already exists for this counter",
        )
    
    # Create menu item
    from sqlalchemy import event
    
    new_item = MenuItem(
        name=menu_data.name,
        normalized_name=normalized_check,
        category=menu_data.category,
        is_available=menu_data.is_available,
        preparation_time_minutes=menu_data.preparation_time_minutes,
        price=menu_data.price,
        description=menu_data.description,
        aliases=menu_data.aliases,
        counter_id=menu_data.counter_id,
    )
    
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    
    return new_item


@router.get(
    "/{item_id}",
    response_model=MenuItemResponse,
    status_code=status.HTTP_200_OK,
    tags=["menu"],
)
async def get_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific menu item."""
    item = (
        db.query(MenuItem)
        .filter(MenuItem.id == item_id)
        .first()
    )
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )
    
    # Check access
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if item.counter_id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter's menu",
            )
    
    return item


@router.patch(
    "/{item_id}",
    response_model=MenuItemResponse,
    status_code=status.HTTP_200_OK,
    tags=["menu"],
)
async def update_menu_item(
    item_id: int,
    menu_data: MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a menu item."""
    item = (
        db.query(MenuItem)
        .filter(MenuItem.id == item_id)
        .first()
    )
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )
    
    # Check permissions
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if item.counter_id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter's menu",
            )
    
    # Update fields
    update_data = menu_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["menu"])
async def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a menu item (soft delete by setting unavailable)."""
    item = (
        db.query(MenuItem)
        .filter(MenuItem.id == item_id)
        .first()
    )
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )
    
    # Check permissions
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if item.counter_id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter's menu",
            )
    
    # Soft delete - just set as unavailable
    item.is_available = False
    db.commit()