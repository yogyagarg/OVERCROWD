# Order Routes
# Core order management endpoints

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from ...db.database import get_db
from ...db.models import User, ServiceCounter, Order, OrderStatus, OrderItem, MenuItem
from ...core.security import get_current_user, check_role
from ...schemas import (
    OrderCreate,
    OrderUpdateStatus,
    OrderResponse,
    OrderItemCreate,
    OrderItemResponse,
    MenuItemResponse,
    TokenResponse,
    UserInfo,
)
from ...core.config import settings
from datetime import date, datetime, timedelta


router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
async def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Create a new order transactionally."""
    # Validate counter exists and user has access
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == order_data.counter_id)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service counter not found",
        )
    
    # Check user access to counter
    if current_user.role not in ["platform_admin", "organization_admin"]:
        if counter.id not in current_user.accessible_counter_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this counter",
            )
    
    # Validate business date if provided
    business_date = order_data.business_date
    if business_date is None:
        # Use current date in counter's timezone
        business_date = date.today()
    
    # Check idempotency key if provided
    if order_data.idempotency_key:
        existing = (
            db.query(Order)
            .filter(Order.idempotency_key == order_data.idempotency_key)
            .first()
        )
        if existing:
            # Return existing order
            return OrderResponse.from_orm(existing)
    
    # Begin transaction
    try:
        # Create the order
        from ...schemas import UserRole
        
        new_order = Order(
            order_number=None,  # Will be generated
            business_date=business_date.isoformat()
            if isinstance(business_date, date)
            else business_date,
            source=order_data.source,
            organization_id=counter.organization_id,
            service_counter_id=counter_id,
            created_by_staff_user_id=current_user.id,
            idempotency_key=order_data.idempotency_key,
        )
        
        db.add(new_order)
        db.flush()  # Flush to get order ID
        
        # Generate order number (simple format: counter_prefix + date + sequence)
        # In production, this would be more sophisticated
        order_number = f"ORD-{counter.slug}-{business_date.strftime('%Y%m%d')}-{new_order.id:06d}"
        new_order.order_number = order_number
        
        # Create order items
        for item_data in order_data.items:
            # Validate menu item exists and is available
            menu_item = (
                db.query(MenuItem)
                .filter(MenuItem.id == item_data.menu_item_id)
                .first()
            )
            
            if not menu_item:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Menu item {item_data.menu_item_id} not found",
                )
            
            if not menu_item.is_available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Menu item '{menu_item.name}' is not available",
                )
            
            # Create order item
            order_item = OrderItem(
                order_id=new_order.id,
                menu_item_id=item_data.menu_item_id,
                item_name_snapshot=menu_item.name,
                quantity=item_data.quantity,
                item_notes=item_data.item_notes,
            )
            
            db.add(order_item)
        
        # Set initial status
        new_order.status = OrderStatus.pending
        
        # Write status history
        from ...db.models import OrderStatusHistory
        status_history = OrderStatusHistory(
            order_id=new_order.id,
            old_status=None,
            new_status=OrderStatus.pending,
            changed_by_staff_user_id=current_user.id,
            actor_type="staff",
            reason="Order creation",
        )
        db.add(status_history)
        
        # Commit
        db.commit()
        db.refresh(new_order)
        
        # Refresh items
        db.refresh(new_order)
        # Re-query with items loaded
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == new_order.id)
            .all()
        )
        
        # Rebuild response with items
        response_items = [
            OrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                item_name_snapshot=item.item_name_snapshot,
                quantity=item.quantity,
                item_notes=item.item_notes,
                created_at=item.created_at,
            )
            for item in items
        ]
        
        return OrderResponse(
            id=new_order.id,
            order_number=new_order.order_number,
            business_date=new_order.business_date,
            status=new_order.status,
            source=new_order.source,
            created_at=new_order.created_at,
            updated_at=new_order.updated_at,
            items=response_items,
            total_items=len(response_items),
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}",
        )


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    tags=["orders"],
)
async def update_order_status(
    order_id: int,
    status_update: OrderUpdateStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Update order status with validation."""
    # Get the order
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Check user access to counter
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == order.service_counter_id)
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
    
    # Validate status transition
    current_status = order.status
    new_status = status_update.new_status
    
    # Define allowed transitions
    allowed_transitions = {
        OrderStatus.pending: [OrderStatus.preparing, OrderStatus.cancelled],
        OrderStatus.preparing: [OrderStatus.ready_for_pickup, OrderStatus.cancelled],
        OrderStatus.ready_for_pickup: [OrderStatus.completed],
        OrderStatus.completed: [],  # No further transitions
        OrderStatus.cancelled: [],  # No further transitions
    }
    
    if new_status not in allowed_transitions.get(current_status, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition: {current_status.value} -> {new_status.value}",
        )
    
    # Begin transaction
    try:
        # Update order status
        order.status = new_status
        
        # Set timestamps based on status
        now = datetime.utcnow()
        if new_status == OrderStatus.ready_for_pickup:
            order.ready_at = now
        elif new_status == OrderStatus.completed:
            order.completed_at = now
        elif new_status == OrderStatus.cancelled:
            order.cancelled_at = now
        
        # Write status history
        from ...db.models import OrderStatusHistory
        status_history = OrderStatusHistory(
            order_id=order.id,
            old_status=current_status,
            new_status=new_status,
            changed_by_staff_user_id=current_user.id,
            actor_type="staff",
            reason=status_update.reason or "Status transition",
        )
        db.add(status_history)
        
        # Recalculate active count after status change
        # This will be picked up by the queue service
        if settings.SSE_ENABLED:
            background_tasks.add_task(
                _recalculate_queue_count,
                counter.id,
                db,
            )
        
        db.commit()
        
        # Refresh order with items
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .all()
        )
        
        response_items = [
            OrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                item_name_snapshot=item.item_name_snapshot,
                quantity=item.quantity,
                item_notes=item.item_notes,
                created_at=item.created_at,
            )
            for item in items
        ]
        
        return OrderResponse(
            id=order.id,
            order_number=order.order_number,
            business_date=order.business_date,
            status=order.status,
            source=order.source,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=response_items,
            total_items=len(response_items),
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update order status: {str(e)}",
        )


@router.get("/", response_model=List[OrderResponse], tags=["orders"])
async def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: Optional[OrderStatus] = None,
    counter_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
):
    """List orders with filtering."""
    query = db.query(Order)
    
    # Filter by counter if specified
    if counter_id:
        # Check user has access
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
        query = query.filter(Order.service_counter_id == counter_id)
    
    # Filter by status
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    # Apply user access filter
    if current_user.role not in ["platform_admin", "organization_admin"]:
        query = query.filter(
            Order.service_counter_id.in_(current_user.accessible_counter_ids)
        )
    
    # Order by creation date (newest first)
    query = query.order_by(Order.created_at.desc())
    
    # Apply pagination
    orders = query.offset(skip).limit(limit).all()
    
    # Build responses with items
    results = []
    for order in orders:
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .all()
        )
        
        response_items = [
            OrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                item_name_snapshot=item.item_name_snapshot,
                quantity=item.quantity,
                item_notes=item.item_notes,
                created_at=item.created_at,
            )
            for item in items
        ]
        
        results.append(
            OrderResponse(
                id=order.id,
                order_number=order.order_number,
                business_date=order.business_date,
                status=order.status,
                source=order.source,
                created_at=order.created_at,
                updated_at=order.updated_at,
                items=response_items,
                total_items=len(response_items),
            )
        )
    
    return results


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    tags=["orders"],
)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific order by ID."""
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Check user access to counter
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.id == order.service_counter_id)
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
    
    # Load items
    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )
    
    response_items = [
        OrderItemResponse(
            id=item.id,
            menu_item_id=item.menu_item_id,
            item_name_snapshot=item.item_name_snapshot,
            quantity=item.quantity,
            item_notes=item.item_notes,
            created_at=item.created_at,
        )
        for item in items
    ]
    
    return OrderResponse(
        id=order.id,
        order_number=order.order_number,
        business_date=order.business_date,
        status=order.status,
        source=order.source,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=response_items,
        total_items=len(response_items),
    )


@router.patch(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    tags=["orders"],
)
async def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Cancel an order."""
    return await update_order_status(
        order_id=order_id,
        status_update=OrderUpdateStatus(new_status=OrderStatus.cancelled, reason="Cancelled by staff"),
        db=db,
        current_user=current_user,
        background_tasks=background_tasks,
    )