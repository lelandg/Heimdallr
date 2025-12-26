"""REST API for AWS Monitor management.

Provides HTTP endpoints for:
- Status and health checks
- Manual trigger endpoints
- Configuration management
- Alert and action management
- Secure alert API for external triggers
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api_auth import APIAuthenticator

log = logging.getLogger("monitor.api")

# FastAPI app
app = FastAPI(
    title="AWS Monitor API",
    description="LLM-powered AWS service monitoring and remediation",
    version="0.1.0",
)

# Global reference to MonitorApp (set by main.py)
_monitor_app = None

# Global API authenticator (set by main.py)
_api_auth: Optional[APIAuthenticator] = None


def set_monitor_app(monitor_app) -> None:
    """Set the global monitor app reference."""
    global _monitor_app, _api_auth
    _monitor_app = monitor_app

    # Set up API authenticator using ChatMaster credentials
    chatmaster = monitor_app.config.notifications.chatmaster
    if chatmaster.api_key and chatmaster.api_secret:
        _api_auth = APIAuthenticator(chatmaster.api_key, chatmaster.api_secret)
        log.info("API authentication configured using ChatMaster credentials")
    else:
        log.warning("API authentication not configured (no ChatMaster credentials)")


def get_monitor_app():
    """Get the monitor app, raising if not initialized."""
    if _monitor_app is None:
        raise HTTPException(status_code=503, detail="Monitor not initialized")
    return _monitor_app


def get_api_auth() -> APIAuthenticator:
    """Get the API authenticator, raising if not configured."""
    if _api_auth is None:
        raise HTTPException(status_code=503, detail="API authentication not configured")
    return _api_auth


# ============================================================================
# Request/Response Models
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    uptime_s: Optional[int] = None
    components: Dict[str, str] = Field(default_factory=dict)


class ServiceHealthResponse(BaseModel):
    """Service health status."""
    service_id: str
    service_name: str
    service_type: str
    state: str
    message: str
    last_check: str


class AlertResponse(BaseModel):
    """Alert information."""
    alert_id: str
    title: str
    message: str
    priority: str
    status: str
    source_service: str
    created_at: str
    occurrence_count: int


class ActionRequest(BaseModel):
    """Request to execute an action."""
    action_type: str
    target_service: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class ActionResponse(BaseModel):
    """Action execution response."""
    status: str
    action_type: str
    target_service: str
    message: str
    duration_ms: int = 0


class AnalysisRequest(BaseModel):
    """Request for error analysis."""
    error_message: str
    service_name: str = "unknown"
    context: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Error analysis response."""
    category: str
    severity: str
    root_cause: str
    recommended_action: str
    confidence: float


class StatsResponse(BaseModel):
    """System statistics."""
    monitoring: Dict[str, Any]
    alerts: Dict[str, Any]
    actions: Dict[str, Any]
    llm: Dict[str, Any]


class SendAlertRequest(BaseModel):
    """Request to send a custom alert."""
    service: str = Field(..., description="Service name (e.g., 'Heimdallr', 'ChameleonLabs')")
    priority: str = Field(..., description="Priority level: P1, P2, P3, or P4")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message body")
    details: Dict[str, Any] = Field(default_factory=dict, description="Optional additional details")


class SendAlertResponse(BaseModel):
    """Response from sending an alert."""
    success: bool
    channels: Dict[str, bool] = Field(default_factory=dict, description="Success status per channel")
    message: str


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Check overall system health."""
    monitor = get_monitor_app()

    components = {}

    # Check AWS connectivity
    try:
        aws_results = await monitor.aws_client.test_connection()
        components["aws"] = "healthy" if any(aws_results.values()) else "degraded"
    except Exception:
        components["aws"] = "unhealthy"

    # Check LLM connectivity
    try:
        llm_results = await monitor.llm_client.test_connection()
        components["llm"] = "healthy" if any(llm_results.values()) else "degraded"
    except Exception:
        components["llm"] = "unhealthy"

    # Overall status
    if all(s == "healthy" for s in components.values()):
        status = "healthy"
    elif any(s == "unhealthy" for s in components.values()):
        status = "unhealthy"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
    )


@app.get("/health/services", response_model=List[ServiceHealthResponse], tags=["Health"])
async def get_service_health() -> List[ServiceHealthResponse]:
    """Get health status of all monitored services."""
    monitor = get_monitor_app()

    health_map = monitor.service_monitor.get_all_health()

    return [
        ServiceHealthResponse(
            service_id=h.service_id,
            service_name=h.service_name,
            service_type=h.service_type,
            state=h.state.value,
            message=h.message,
            last_check=h.last_check.isoformat(),
        )
        for h in health_map.values()
    ]


@app.get("/health/services/{service_id}", response_model=ServiceHealthResponse, tags=["Health"])
async def get_service_health_by_id(service_id: str) -> ServiceHealthResponse:
    """Get health status of a specific service."""
    monitor = get_monitor_app()

    health = monitor.service_monitor.get_health(service_id)
    if not health:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")

    return ServiceHealthResponse(
        service_id=health.service_id,
        service_name=health.service_name,
        service_type=health.service_type,
        state=health.state.value,
        message=health.message,
        last_check=health.last_check.isoformat(),
    )


# ============================================================================
# Alert Endpoints
# ============================================================================

@app.get("/alerts", response_model=List[AlertResponse], tags=["Alerts"])
async def get_alerts(
    priority: Optional[str] = Query(None, description="Filter by priority (P1-P4)"),
    limit: int = Query(50, ge=1, le=200),
) -> List[AlertResponse]:
    """Get open alerts."""
    monitor = get_monitor_app()

    from app.alert_manager import AlertPriority

    priority_filter = None
    if priority:
        try:
            priority_filter = AlertPriority(priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")

    alerts = monitor.alert_manager.get_open_alerts(priority_filter)[:limit]

    return [
        AlertResponse(
            alert_id=a.alert_id,
            title=a.title,
            message=a.message,
            priority=a.priority.value,
            status=a.status.value,
            source_service=a.source_service,
            created_at=a.created_at.isoformat(),
            occurrence_count=a.occurrence_count,
        )
        for a in alerts
    ]


@app.get("/alerts/{alert_id}", response_model=AlertResponse, tags=["Alerts"])
async def get_alert(alert_id: str) -> AlertResponse:
    """Get a specific alert."""
    monitor = get_monitor_app()

    alert = monitor.alert_manager.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")

    return AlertResponse(
        alert_id=alert.alert_id,
        title=alert.title,
        message=alert.message,
        priority=alert.priority.value,
        status=alert.status.value,
        source_service=alert.source_service,
        created_at=alert.created_at.isoformat(),
        occurrence_count=alert.occurrence_count,
    )


@app.post("/alerts/{alert_id}/acknowledge", tags=["Alerts"])
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Query("api", description="Who acknowledged"),
) -> Dict[str, str]:
    """Acknowledge an alert."""
    monitor = get_monitor_app()

    success = monitor.alert_manager.acknowledge_alert(alert_id, acknowledged_by)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")

    return {"status": "acknowledged", "alert_id": alert_id}


@app.post("/alerts/{alert_id}/resolve", tags=["Alerts"])
async def resolve_alert(
    alert_id: str,
    resolved_by: str = Query("api", description="Who resolved"),
    message: str = Query("", description="Resolution message"),
) -> Dict[str, str]:
    """Resolve an alert."""
    monitor = get_monitor_app()

    success = monitor.alert_manager.resolve_alert(alert_id, resolved_by, message)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")

    return {"status": "resolved", "alert_id": alert_id}


# ============================================================================
# Action Endpoints
# ============================================================================

@app.post("/actions/execute", response_model=ActionResponse, tags=["Actions"])
async def execute_action(
    request: ActionRequest,
    background_tasks: BackgroundTasks,
) -> ActionResponse:
    """Execute a remediation action."""
    monitor = get_monitor_app()

    from app.action_recommender import ActionType, ActionRisk

    try:
        action_type = ActionType(request.action_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action type: {request.action_type}")

    # Check safety
    from app.safety_guard import SafetyCheckResult

    safety_result = monitor.safety_guard.check_action(
        action_type,
        request.target_service,
        ActionRisk.MEDIUM,  # Default risk level
    )

    if safety_result not in {SafetyCheckResult.ALLOWED, SafetyCheckResult.REQUIRES_APPROVAL}:
        raise HTTPException(
            status_code=403,
            detail=f"Action blocked: {safety_result.value}",
        )

    # Execute action
    result = await monitor.action_executor.execute_single_action(
        action_type=action_type,
        target_service=request.target_service,
        parameters=request.parameters,
        dry_run=request.dry_run,
    )

    return ActionResponse(
        status=result.status.value,
        action_type=result.action_type.value,
        target_service=result.target_service,
        message=result.message,
        duration_ms=result.duration_ms,
    )


@app.get("/actions/history", tags=["Actions"])
async def get_action_history(
    limit: int = Query(20, ge=1, le=100),
) -> List[Dict]:
    """Get recent action execution history."""
    monitor = get_monitor_app()

    results = monitor.action_executor.get_recent_executions(limit)

    return [
        {
            "plan_id": r.plan_id,
            "status": r.overall_status.value,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "success_count": r.success_count,
            "failure_count": r.failure_count,
        }
        for r in results
    ]


# ============================================================================
# Analysis Endpoints
# ============================================================================

@app.post("/analyze", response_model=AnalysisResponse, tags=["Analysis"])
async def analyze_error(request: AnalysisRequest) -> AnalysisResponse:
    """Analyze an error message using LLM."""
    monitor = get_monitor_app()

    from app.log_collector import DetectedError, ErrorSeverity

    # Create a synthetic error for analysis
    error = DetectedError(
        message=request.error_message,
        severity=ErrorSeverity.ERROR,
        source_app=request.service_name,
        log_group="manual",
        timestamp=datetime.now(timezone.utc),
        error_type="manual",
    )

    analysis = await monitor.error_analyzer.quick_triage(error)

    return AnalysisResponse(
        category=analysis.category.value,
        severity=analysis.severity.value,
        root_cause=analysis.root_cause,
        recommended_action=analysis.recommended_action.value,
        confidence=analysis.confidence,
    )


# ============================================================================
# Statistics Endpoints
# ============================================================================

@app.get("/stats", response_model=StatsResponse, tags=["Statistics"])
async def get_stats() -> StatsResponse:
    """Get system statistics."""
    monitor = get_monitor_app()

    return StatsResponse(
        monitoring={
            "log_collector": monitor.log_collector.get_stats(),
            "service_monitor": monitor.service_monitor.get_stats(),
        },
        alerts=monitor.alert_manager.get_stats(),
        actions={
            "executor": monitor.action_executor.get_execution_stats(),
            "safety": monitor.safety_guard.get_stats(),
        },
        llm=monitor.llm_orchestrator.get_usage_stats(),
    )


@app.get("/stats/llm", tags=["Statistics"])
async def get_llm_stats() -> Dict:
    """Get LLM usage statistics."""
    monitor = get_monitor_app()

    return {
        "usage": monitor.llm_orchestrator.get_usage_stats(),
        "health": monitor.llm_orchestrator.get_model_health(),
    }


# ============================================================================
# Configuration Endpoints
# ============================================================================

@app.get("/config", tags=["Configuration"])
async def get_config() -> Dict:
    """Get current configuration (sensitive values redacted)."""
    monitor = get_monitor_app()

    config = monitor.config
    return {
        "aws": {
            "region": config.aws.region,
        },
        "monitoring": {
            "amplify_apps": [
                {"app_id": a.app_id, "name": a.name}
                for a in config.monitoring.amplify_apps
            ],
            "ec2_instances": [
                {"instance_id": i.instance_id, "name": i.name}
                for i in config.monitoring.ec2_instances
            ],
            "log_poll_interval": config.monitoring.log_poll_interval,
            "health_check_interval": config.monitoring.health_check_interval,
        },
        "llm": {
            "primary_model": config.llm.primary_model,
            "analysis_model": config.llm.analysis_model,
            "fallback_models": config.llm.fallback_models,
        },
        "actions": {
            "allow_restart": config.actions.allow_restart,
            "allow_redeploy": config.actions.allow_redeploy,
            "max_restarts_per_hour": config.actions.max_restarts_per_hour,
            "cooldown_minutes": config.actions.cooldown_minutes,
        },
        "notifications": {
            "enabled": config.notifications.enabled,
            "email_enabled": config.notifications.email_enabled,
            "slack_enabled": config.notifications.slack_enabled,
            "discord_enabled": config.notifications.discord_enabled,
            "chatmaster_enabled": config.notifications.chatmaster.enabled,
        },
    }


@app.post("/config/model", tags=["Configuration"])
async def switch_model(
    model: str = Query(..., description="Model identifier"),
    model_type: str = Query("primary", description="primary or analysis"),
) -> Dict[str, str]:
    """Switch the active LLM model."""
    monitor = get_monitor_app()

    if model_type == "primary":
        monitor.llm_client.set_model(model)
    elif model_type == "analysis":
        monitor.llm_client.set_analysis_model(model)
    else:
        raise HTTPException(status_code=400, detail="Invalid model_type")

    return {"status": "switched", "model": model, "type": model_type}


# ============================================================================
# Audit Endpoints
# ============================================================================

@app.get("/audit", tags=["Audit"])
async def get_audit_log(
    event_type: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict]:
    """Get audit log entries."""
    monitor = get_monitor_app()

    from app.audit_logger import AuditEventType

    type_filter = None
    if event_type:
        try:
            type_filter = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")

    events = monitor.audit_logger.search_events(
        event_type=type_filter,
        target_service=service,
        limit=limit,
    )

    return [e.to_dict() for e in events]


@app.get("/audit/report", tags=["Audit"])
async def get_compliance_report(
    days: int = Query(7, ge=1, le=90),
) -> Dict:
    """Generate compliance report."""
    monitor = get_monitor_app()

    from datetime import timedelta

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    return monitor.audit_logger.generate_compliance_report(start_date, end_date)


# ============================================================================
# Manual Triggers
# ============================================================================

@app.post("/trigger/health-check", tags=["Triggers"])
async def trigger_health_check(
    service_id: Optional[str] = Query(None, description="Specific service or all"),
) -> Dict:
    """Trigger immediate health check."""
    monitor = get_monitor_app()

    results = await monitor.service_monitor.force_check(service_id)

    return {
        "status": "completed",
        "checked": len(results),
        "results": [
            {"service_id": r.service_id, "state": r.state.value}
            for r in results
        ],
    }


@app.post("/trigger/log-scan", tags=["Triggers"])
async def trigger_log_scan(
    app_id: Optional[str] = Query(None, description="Specific app or all"),
    minutes: int = Query(5, ge=1, le=60),
) -> Dict:
    """Trigger immediate log scan for errors."""
    monitor = get_monitor_app()

    errors = await monitor.log_collector.fetch_recent_errors(
        app_id=app_id,
        minutes=minutes,
    )

    return {
        "status": "completed",
        "errors_found": len(errors),
        "errors": [
            {
                "fingerprint": e.fingerprint,
                "severity": e.severity.value,
                "type": e.error_type,
                "message": e.message[:200],
            }
            for e in errors[:20]  # Limit response size
        ],
    }


# ============================================================================
# Secure Alert API (authenticated via HMAC)
# ============================================================================

async def require_auth(request: Request):
    """Dependency that requires API authentication."""
    auth = get_api_auth()
    await auth(request)


@app.post(
    "/api/v1/alert/send",
    response_model=SendAlertResponse,
    tags=["Secure API"],
    summary="Send a custom alert",
    description="Send a custom alert through all configured notification channels. "
                "Requires HMAC-SHA256 authentication using ChatMaster credentials.",
)
async def send_custom_alert(
    request: Request,
    body: SendAlertRequest,
    _auth: None = Depends(require_auth),
) -> SendAlertResponse:
    """Send a custom alert through notification channels.

    This endpoint requires HMAC-SHA256 authentication.
    Use the same credentials configured for ChatMaster.

    Headers required:
    - X-API-Key: Your API key
    - X-Timestamp: Unix timestamp (seconds)
    - X-Signature: HMAC-SHA256(secret, f"{timestamp}.{body}")
    """
    monitor = get_monitor_app()

    from app.notifier import Notification, NotificationPriority, NotificationChannel

    # Validate and map priority
    priority_map = {
        "P1": NotificationPriority.CRITICAL,
        "P2": NotificationPriority.HIGH,
        "P3": NotificationPriority.NORMAL,
        "P4": NotificationPriority.LOW,
    }

    if body.priority.upper() not in priority_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {body.priority}. Must be P1, P2, P3, or P4",
        )

    priority = priority_map[body.priority.upper()]

    # Build channel list based on configuration
    channels = []
    settings = monitor.config.notifications

    if settings.email_enabled:
        channels.append(NotificationChannel.EMAIL)
    if settings.slack_enabled:
        channels.append(NotificationChannel.SLACK)
    if settings.discord_enabled:
        channels.append(NotificationChannel.DISCORD)
    if settings.chatmaster.enabled:
        channels.append(NotificationChannel.CHATMASTER)

    if not channels:
        return SendAlertResponse(
            success=False,
            channels={},
            message="No notification channels configured",
        )

    # Create and send notification
    notification = Notification(
        title=body.title,
        message=body.message,
        priority=priority,
        channels=channels,
        service=body.service,
        details=body.details,
    )

    results = await monitor.notifier.send_notification(notification)

    # Check if any channel succeeded
    any_success = any(results.values())

    return SendAlertResponse(
        success=any_success,
        channels=results,
        message="Alert sent successfully" if any_success else "All channels failed",
    )


@app.get(
    "/api/v1/alert/test",
    tags=["Secure API"],
    summary="Test authentication",
    description="Test if API authentication is working (no auth required for this endpoint)",
)
async def test_auth_status() -> Dict[str, Any]:
    """Check if API authentication is configured."""
    return {
        "auth_configured": _api_auth is not None and _api_auth.is_configured,
        "message": "Use POST /api/v1/alert/send with HMAC authentication to send alerts",
    }
