from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderName(StrEnum):
    MOCK = "mock"
    LLM = "llm"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ReviewOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: ProviderName = ProviderName.MOCK
    max_findings: int = Field(default=100, alias="maxFindings", ge=0, le=10_000)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    diff: str
    options: ReviewOptions = Field(default_factory=ReviewOptions)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    rule_id: str = Field(alias="ruleId")
    path: str
    line: int = Field(ge=1)
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["security", "correctness", "performance", "style"]
    title: str
    evidence: str


class Usage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input_bytes: int = Field(alias="inputBytes", ge=0)
    chunks: int = Field(ge=1)
    cache_hit: bool = Field(alias="cacheHit")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class SubmitResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: Literal["queued"] = "queued"


class JobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: JobStatus
    findings: list[Finding] | None = None
    usage: Usage
    error: ErrorDetail | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    uptime_seconds: float = Field(alias="uptimeSeconds", ge=0)


class LimitsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_payload_bytes: int = Field(alias="maxPayloadBytes")
    chunk_bytes: int = Field(alias="chunkBytes")
    max_concurrent_jobs: int = Field(alias="maxConcurrentJobs")
    rate_limit_per_minute: int = Field(alias="rateLimitPerMinute")


class SpecResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    spec_version: Literal["1.0"] = Field(default="1.0", alias="specVersion")
    providers: list[Literal["mock", "llm"]]
    limits: LimitsResponse
