# Public Routes
# Public queue page endpoints - aggregate counts only

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from ...db.database import get_db
from ...db.models import User, ServiceCounter, Order, OrderStatus
from ...core.security import get_current_user, verify_counter_public_access
from ...schemas import (
    PublicQueueResponse,
    PublicQueueStats,
)


router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/counters/{counter_slug}/queue",
    response_model=PublicQueueResponse,
    status_code=status.HTTP_200_OK,
    tags=["public"],
)
async def get_public_queue(
    counter_slug: str,
    db: Session = Depends(get_db),
):
    """Get public aggregate queue count for a counter."""
    # Find counter by slug
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.slug == counter_slug)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    
    # Check if counter is public
    if not counter.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This counter's queue is not publicly exposed",
        )
    
    # Count active orders
    active_count = (
        db.query(func.count(Order.id))
        .filter(
            Order.service_counter_id == counter.id,
            Order.status.in_(
                [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
            ),
        )
        .scalar()
    )
    
    # Get last updated timestamp
    last_update = (
        db.query(Order.updated_at)
        .filter(
            Order.service_counter_id == counter.id,
        )
        .order_by(Order.updated_at.desc())
        .limit(1)
        .scalar()
    )
    
    # Determine state
    if active_count is None or active_count == 0:
        state = "live" if last_update else "error"
    else:
        state = "live" if last_update else "stale"
    
    # Determine stale status
    stale_since = None
    if last_update:
        from datetime import datetime, timedelta
        last_update_dt = last_update if isinstance(last_update, datetime) else datetime.fromisoformat(str(last_update))
        if datetime.utcnow() - last_update_dt > timedelta(seconds=300):  # 5 minutes
            stale_since = last_update
    
    return PublicQueueResponse(
        counter_id=counter.id,
        counter_slug=counter.slug,
        active_orders=active_count or 0,
        state=state,
        updated_at=last_update if last_update else datetime.utcnow(),
        stale_since=stale_since,
    )


@router.get(
    "/counters/{counter_slug}/queue/events",
    tags=["public"],
)
async def public_queue_events(
    counter_slug: str,
    db: Session = Depends(get_db),
):
    """SSE endpoint for public queue updates."""
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    from datetime import datetime
    
    # Find counter by slug
    counter = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.slug == counter_slug)
        .first()
    )
    
    if not counter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Counter not found",
        )
    
    if not counter.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This counter's queue is not publicly exposed",
        )
    
    async def event_generator():
        """Generate SSE events for queue changes."""
        last_id = 0
        stale_until = None
        
        while True:
            # Check current count
            active_count = (
                db.query(func.count(Order.id))
                .filter(
                    Order.service_counter_id == counter.id,
                    Order.status.in_(
                        [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
                    ),
                )
                .scalar()
            )
            
            now = datetime.utcnow()
            
            event_data = {
                "type": "queue_update",
                "counter_id": counter.id,
                "counter_slug": counter.slug,
                "active_orders": active_count or 0,
                "timestamp": now.isoformat(),
                "state": "live" if (active_count or 0) > 0 else "idle",
            }
            
            if stale_until and now > stale_until:
                event_data["state"] = "stale"
                event_data["stale_since"] = stale_until.isoformat()
            
            yield f"data: {json.dumps(event_data)}\n\n"
            
            # Wait before next check
            await asyncio.sleep(3)  # 3 second polling interval
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get(
    "/counters",
    response_model=List[dict],
    status_code=status.HTTP_200_OK,
    tags=["public"],
)
async def list_public_counters(
    db: Session = Depends(get_db),
):
    """List all public counters with their current queue status."""
    counters = (
        db.query(ServiceCounter)
        .filter(ServiceCounter.is_public == True, ServiceCounter.is_active == True)
        .all()
    )
    
    results = []
    from datetime import datetime, timedelta
    
    for counter in counters:
        # Get current active count
        active_count = (
            db.query(func.count(Order.id))
            .filter(
                Order.service_counter_id == counter.id,
                Order.status.in_(
                    [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
                ),
            )
            .scalar()
        )
        
        # Get last update
        last_update = (
            db.query(Order.updated_at)
            .filter(Order.service_counter_id == counter.id)
            .order_by(Order.updated_at.desc())
            .limit(1)
            .scalar()
        )
        
        # Determine state
        if active_count is None or active_count == 0:
            state = "live" if last_update else "error"
        else:
            state = "live" if last_update else "stale"
        
        stale_since = None
        if last_update:
            last_update_dt = last_update if isinstance(last_update, datetime) else datetime.fromisoformat(str(last_update))
            if datetime.utcnow() - last_update_dt > timedelta(seconds=300):
                stale_since = last_update
        
        results.append(
            {
                "counter_id": counter.id,
                "counter_slug": counter.slug,
                "counter_name": counter.name,
                "active_orders": active_count or 0,
                "state": state,
                "updated_at": last_update if last_update else datetime.utcnow(),
                "stale_since": stale_since,
                "capacity": counter.capacity,
            }
        )
    
    return results