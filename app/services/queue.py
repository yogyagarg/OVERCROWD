# Queue Service
# Business logic for order queue management and active count calculation

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ...db.models import Order, OrderStatus, ServiceCounter


class QueueService:
    """Service for managing queue counts and order status logic."""
    
    @staticmethod
    def get_active_summary(counter_id: int) -> Dict[str, Any]:
        """Get active order summary for a counter."""
        # Count active orders (pending, preparing, ready_for_pickup)
        active_count = (
            func.count(Order.id)
        ).filter(
            Order.service_counter_id == counter_id,
            Order.status.in_(
                [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
            ),
        )
        
        # Total orders
        total_count = (
            func.count(Order.id)
        ).filter(
            Order.service_counter_id == counter_id
        )
        
        # Count by status
        status_counts = (
            func.count(Order.id)
        ).filter(
            Order.service_counter_id == counter_id
        ).group_by(Order.status).all()
        
        status_breakdown = {}
        for count_val, status_val in status_counts:
            status_breakdown[status_val.value if hasattr(status_val, 'value') else str(status_val)] = count_val or 0
        
        return {
            "counter_id": counter_id,
            "active_orders": active_count.scalar() or 0,
            "total_orders": total_count.scalar() or 0,
            "status_breakdown": status_breakdown,
            "last_updated": datetime.utcnow().isoformat(),
        }
    
    @staticmethod
    def recalculate_counter_count(counter_id: int, db: Session) -> int:
        """Recalculate and return the active count for a counter."""
        active_count = (
            db.query(func.count(Order.id))
            .filter(
                Order.service_counter_id == counter_id,
                Order.status.in_(
                    [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
                ),
                Order.is_active == True,  # Assuming we add is_active flag
            )
            .scalar()
        )
        
        return active_count or 0
    
    @staticmethod
    def is_order_active(order_status: OrderStatus) -> bool:
        """Check if an order status means the order is active in the queue."""
        return order_status in [
            OrderStatus.pending,
            OrderStatus.preparing,
            OrderStatus.ready_for_pickup,
        ]
    
    @staticmethod
    def get_status_transition_allowed(
        from_status: OrderStatus, 
        to_status: OrderStatus
    ) -> bool:
        """Check if a status transition is allowed."""
        allowed = {
            OrderStatus.pending: [OrderStatus.preparing, OrderStatus.cancelled],
            OrderStatus.preparing: [OrderStatus.ready_for_pickup, OrderStatus.cancelled],
            OrderStatus.ready_for_pickup: [OrderStatus.completed],
            OrderStatus.completed: [],
            OrderStatus.cancelled: [],
        }
        return to_status in allowed.get(from_status, [])
    
    @staticmethod
    def get_active_order_count(
        db: Session, 
        counter_id: int
    ) -> int:
        """Get the current active order count for a counter."""
        count = (
            db.query(func.count(Order.id))
            .filter(
                Order.service_counter_id == counter_id,
                Order.status.in_(
                    [OrderStatus.pending, OrderStatus.preparing, OrderStatus.ready_for_pickup]
                ),
            )
            .scalar()
        )
        return count or 0