from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator

from app.api.deps import TokenData, get_agent_repo, require_role
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.domain.enums import AgentStatus
from app.models.target_agent import TargetAgent
from app.repositories.agents import TargetAgentRepository

router = APIRouter()
logger = get_logger(__name__)


class TargetAgentCreate(BaseModel):
    name: str
    description: str | None = None
    endpoint_url: HttpUrl
    auth_config: dict = {}
    request_template: dict = {}
    response_extraction: dict = {}
    timeout_seconds: int = 30
    max_retries: int = 3
    health_check_url: HttpUrl | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Name too long")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 1 or v > 60:
            raise ValueError("timeout must be 1-60")
        return v


class TargetAgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: HttpUrl | None = None
    auth_config: dict | None = None
    request_template: dict | None = None
    response_extraction: dict | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    allowed: bool | None = None
    health_check_url: HttpUrl | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 200:
            raise ValueError("Name too long")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 60):
            raise ValueError("timeout must be 1-60")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 5):
            raise ValueError("max_retries must be 0-5")
        return v


def _sanitize_agent_response(agent, current_user: TokenData) -> dict:
    """Redact auth_config for viewer roles."""
    data = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "endpoint_url": agent.endpoint_url,
        "auth_config": agent.auth_config if "admin" in current_user.roles or "safety_engineer" in current_user.roles else {},
        "request_template": agent.request_template,
        "response_extraction": agent.response_extraction,
        "timeout_seconds": agent.timeout_seconds,
        "max_retries": agent.max_retries,
        "allowed": agent.allowed,
        "status": agent.status,
        "health_check_url": agent.health_check_url,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }
    return data


class TargetAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    endpoint_url: str
    auth_config: dict
    request_template: dict
    response_extraction: dict
    timeout_seconds: int
    max_retries: int
    allowed: bool
    status: AgentStatus
    health_check_url: str | None = None
    created_at: datetime | str
    updated_at: datetime | str


class HealthCheckResponse(BaseModel):
    healthy: bool
    latency_ms: int | None = None
    error: str | None = None


class AgentTestResponse(BaseModel):
    response: str
    raw: dict = {}
    latency_ms: int = 0


def _extract_agent_text(raw) -> str:
    """Pull the assistant text out of a target-agent response payload."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("response", "text", "content", "output", "message"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return str(raw)
    return str(raw)


@router.get("", response_model=list[TargetAgentResponse], include_in_schema=False)
@router.get("/", response_model=list[TargetAgentResponse])
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(
        require_role(["admin", "safety_engineer", "ml_engineer", "qa_engineer", "viewer"])
    ),
):
    agents = await agent_repo.list(skip=skip, limit=limit)
    return [TargetAgentResponse.model_validate(_sanitize_agent_response(a, current_user)) for a in agents]


@router.post("", response_model=TargetAgentResponse, status_code=201, include_in_schema=False)
@router.post("/", response_model=TargetAgentResponse, status_code=201)
async def create_agent(
    agent: TargetAgentCreate,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(require_role(["admin", "safety_engineer", "ml_engineer"])),
):
    existing = await agent_repo.get_by_name(agent.name)
    if existing:
        raise ConflictError(f"Agent with name '{agent.name}' already exists")

    new_agent = TargetAgent(
        **agent.model_dump(mode="json"),
        created_by=UUID(current_user.sub),
    )
    new_agent = await agent_repo.create(new_agent)
    return TargetAgentResponse.model_validate(_sanitize_agent_response(new_agent, current_user))


@router.get("/{agent_id}", response_model=TargetAgentResponse)
async def get_agent(
    agent_id: UUID,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(
        require_role(["admin", "safety_engineer", "ml_engineer", "qa_engineer", "viewer"])
    ),
):
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise NotFoundError("TargetAgent", str(agent_id))
    return TargetAgentResponse.model_validate(_sanitize_agent_response(agent, current_user))


@router.patch("/{agent_id}", response_model=TargetAgentResponse)
async def update_agent(
    agent_id: UUID,
    update: TargetAgentUpdate,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(require_role(["admin", "safety_engineer", "ml_engineer"])),
):
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise NotFoundError("TargetAgent", str(agent_id))

    update_data = update.model_dump(exclude_unset=True, mode="json")
    for key, value in update_data.items():
        setattr(agent, key, value)

    await agent_repo.session.flush()
    return TargetAgentResponse.model_validate(_sanitize_agent_response(agent, current_user))


class AgentTestRequest(BaseModel):
    input: str


@router.post("/{agent_id}/test", response_model=AgentTestResponse)
async def test_agent(
    agent_id: UUID,
    request: AgentTestRequest,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(
        require_role(["admin", "safety_engineer", "ml_engineer", "qa_engineer"])
    ),
):
    """Send a probe input to the target agent and return its actual reply."""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise NotFoundError("TargetAgent", str(agent_id))

    from app.providers.target_agent import TargetAgentProviderFactory

    try:
        provider = TargetAgentProviderFactory.create_provider(
            "http",
            endpoint_url=agent.endpoint_url,
            auth_config=agent.auth_config,
            request_template=agent.request_template,
            response_extraction=agent.response_extraction,
            timeout=agent.timeout_seconds,
            max_retries=agent.max_retries,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid target agent configuration: {e}") from e

    import time

    try:
        start = time.time()
        raw = await provider.call(request.input)
        latency = int((time.time() - start) * 1000)
        return AgentTestResponse(
            response=_extract_agent_text(raw),
            raw=raw if isinstance(raw, dict) else {"response": str(raw)},
            latency_ms=latency,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Target agent call failed: {e}") from e
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass


@router.post("/{agent_id}/call")
async def call_agent(
    agent_id: UUID,
    request: AgentTestRequest,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(
        require_role(["admin", "safety_engineer", "ml_engineer", "qa_engineer"])
    ),
):
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise NotFoundError("TargetAgent", str(agent_id))

    from app.providers.target_agent import TargetAgentProviderFactory

    provider = TargetAgentProviderFactory.create_provider(
        "http",
        endpoint_url=agent.endpoint_url,
        auth_config=agent.auth_config,
        request_template=agent.request_template,
        response_extraction=agent.response_extraction,
        timeout=agent.timeout_seconds,
        max_retries=agent.max_retries,
    )

    try:
        import time

        start = time.time()
        response = await provider.call(request.input)
        latency = int((time.time() - start) * 1000)
        return {"response": _extract_agent_text(response), "latency_ms": latency}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Target agent call failed: {e}") from e
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    agent_repo: TargetAgentRepository = Depends(get_agent_repo),
    current_user: TokenData = Depends(require_role(["admin"])),
):
    deleted = await agent_repo.delete(agent_id)
    if not deleted:
        raise NotFoundError("TargetAgent", str(agent_id))
    return {"message": "Agent deleted"}
