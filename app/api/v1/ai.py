# AI Assistant Routes
# Gemma 4 AI assistant integration

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional

from ...db.database import get_db
from ...db.models import User, ServiceCounter, Order, OrderStatus
from ...core.security import get_current_user
from ...schemas import (
    GemmaAssistantRequest,
    GemmaAssistantResponse,
    GemmaToolCall,
    UserInfo,
    TokenResponse,
)
from ...services.ai.gemma import GemmaService
from ...core.config import settings
from ...core.security import create_access_token


router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/assistant",
    response_model=GemmaAssistantResponse,
    status_code=status.HTTP_200_OK,
    tags=["ai"],
)
async def ai_assistant(
    request: GemmaAssistantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Run Gemma 4 AI assistant with approved tools."""
    gemma = GemmaService(api_key=settings.GEMMA_API_KEY)
    
    # Determine scope from authenticated user
    scope = None
    if current_user.role in ["organization_admin", "counter_manager"]:
        scope = (
            f"counter:{current_user.accessible_counter_ids[0] if current_user.accessible_counter_ids else 'none'}"
        )
    elif current_user.role == "platform_admin":
        scope = "organization:all"
    
    # Run Gemma 4 assistant
    try:
        response = await gemma.process_request(
            question=request.question,
            scope=scope,
            feature="assistant",
            user_id=current_user.id,
            db_session=db,
        )
        
        # Record the AI action in audit
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=(
                current_user.accessible_counter_ids[0] if current_user.accessible_counter_ids else 0
            ),
            feature="assistant",
            action_name=request.feature or "assistant",
            outcome="success",
            request_id=f"gemma_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "scope": scope,
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        return response
        
    except Exception as e:
        # Record failed attempt in audit
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=(
                current_user.accessible_counter_ids[0] if current_user.accessible_counter_ids else 0
            ),
            feature="assistant",
            action_name=request.feature or "assistant",
            outcome="provider_error",
            request_id=f"gemma_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "error": str(e),
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI assistant error: {str(e)}",
        )


@router.post(
    "/order-draft",
    response_model=GemmaAssistantResponse,
    status_code=status.HTTP_200_OK,
    tags=["ai"],
)
async def ai_order_draft(
    request: GemmaAssistantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Generate AI-assisted order draft."""
    gemma = GemmaService(api_key=settings.GEMMA_API_KEY)
    
    # Get user's accessible counter
    counter_id = (
        current_user.accessible_counter_ids[0] 
        if current_user.accessible_counter_ids 
        else None
    )
    
    # Determine scope
    scope = None
    if counter_id:
        scope = f"counter:{counter_id}"
    
    # Get counter menu items for context
    from ...db.models import MenuItem
    menu_items = (
        db.query(MenuItem)
        .filter(MenuItem.counter_id == counter_id, MenuItem.is_available == True)
        .limit(50)
        .all()
    )
    
    # Build enhanced question with menu context
    menu_context = "\n".join(
        [f"- {item.name} ({item.category.value})" for item in menu_items]
    )
    
    enhanced_question = f"""
    Menu available at this counter:
    {menu_context if menu_context else 'No menu items configured'}
    
    User request: {request.question}
    
    Please provide a structured order draft with valid menu items only. 
    If items are not on the menu, ask for clarification rather than inventing items.
    """
    
    # Run Gemma 4 assistant
    try:
        response = await gemma.process_request(
            question=enhanced_question,
            scope=scope,
            feature="order_draft",
            user_id=current_user.id,
            db_session=db,
        )
        
        # Record the AI action in audit
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=counter_id or 0,
            feature="order_draft",
            action_name=request.feature or "order_draft",
            outcome="success",
            request_id=f"gemma_draft_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "scope": scope,
                "menu_item_count": len(menu_items),
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        return response
        
    except Exception as e:
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=counter_id or 0,
            feature="order_draft",
            action_name=request.feature or "order_draft",
            outcome="provider_error",
            request_id=f"gemma_draft_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "error": str(e),
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI order draft error: {str(e)}",
        )


@router.post(
    "/report",
    response_model=GemmaAssistantResponse,
    status_code=status.HTTP_200_OK,
    tags=["ai"],
)
async def ai_report(
    request: GemmaAssistantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Generate AI operational report."""
    gemma = GemmaService(api_key=settings.GEMMA_API_KEY)
    
    # Get user's accessible counter
    counter_id = (
        current_user.accessible_counter_ids[0] 
        if current_user.accessible_counter_ids 
        else None
    )
    
    # Determine scope
    scope = None
    if counter_id:
        scope = f"counter:{counter_id}"
    
    # Build report question with context
    enhanced_question = f"""
    Generate a concise operational report for the period and counter specified.
    
    Scope: {scope or 'all counters'}
    Question: {request.question}
    
    Provide:
    1. Aggregate counts (created, completed, cancelled)
    2. Time period analysis
    3. Any notable patterns or observations
    
    Base all answers on actual database data. Do not invent statistics.
    """
    
    # Run Gemma 4 assistant
    try:
        response = await gemma.process_request(
            question=enhanced_question,
            scope=scope,
            feature="report",
            user_id=current_user.id,
            db_session=db,
        )
        
        # Record the AI action in audit
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=counter_id or 0,
            feature="report",
            action_name=request.feature or "report",
            outcome="success",
            request_id=f"gemma_report_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "scope": scope,
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        return response
        
    except Exception as e:
        from ...db.models import AiActionAudit
        audit_entry = AiActionAudit(
            staff_user_id=current_user.id,
            service_counter_id=counter_id or 0,
            feature="report",
            action_name=request.feature or "report",
            outcome="provider_error",
            request_id=f"gemma_report_{datetime.utcnow().timestamp()}",
            outcome_details={
                "question": request.question[:200],
                "error": str(e),
                "model": settings.GEMMA_MODEL,
            },
        )
        db.add(audit_entry)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI report error: {str(e)}",
        )