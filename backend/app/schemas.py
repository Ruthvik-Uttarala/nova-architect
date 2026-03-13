from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["low", "med", "high"]


class IdentifiedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue: str
    evidence: str
    severity: RiskLevel


class OptimizationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    why: str
    expected_impact: str
    risk: RiskLevel


class Tradeoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    cost_change_usd_per_month: float
    uptime_impact: str
    security_impact: str
    risk_score_0_to_10: float = Field(ge=0, le=10)


class PlanMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_cost_before: float
    monthly_cost_after_estimate: float
    uptime_risk_before_0_to_10: float = Field(ge=0, le=10)
    uptime_risk_after_0_to_10: float = Field(ge=0, le=10)
    security_risk_before_0_to_10: float = Field(ge=0, le=10)
    security_risk_after_0_to_10: float = Field(ge=0, le=10)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_summary: str
    identified_issues: List[IdentifiedIssue]
    optimization_plan: List[OptimizationStep]
    tradeoffs: List[Tradeoff]
    metrics: PlanMetrics


class SimulationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    baseline: Dict[str, float]
    after: Dict[str, float]


class SimulationCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_cost_before: float
    monthly_cost_after_estimate: float
    delta_usd_per_month: float


class SimulationRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uptime_risk_before_0_to_10: float = Field(ge=0, le=10)
    uptime_risk_after_0_to_10: float = Field(ge=0, le=10)
    security_risk_before_0_to_10: float = Field(ge=0, le=10)
    security_risk_after_0_to_10: float = Field(ge=0, le=10)


class Simulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: List[SimulationScenario]
    cost: SimulationCost
    risk: SimulationRisk


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    snapshot_mode: Literal["sample", "live_aws"] = "sample"
    discovered_snapshot: Optional[Dict[str, Any]] = None


AnalyzeMode = Literal["live_bedrock", "fallback"]


class AnalyzeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    aws_region: str
    analyze_mode: AnalyzeMode
    parse_retries_used: int
    used_fallback: bool


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: Plan
    simulation: Simulation
    used_fallback: bool
    analyze_metadata: Optional[AnalyzeMetadata] = None


VoiceMode = Literal["live_sonic", "fallback"]


class VoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str
    latest_goal: Optional[str] = None
    latest_plan_summary: Optional[str] = None


class VoiceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    aws_region: str
    voice_mode: VoiceMode
    used_fallback: bool


class VoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str
    normalized_goal: str
    spoken_summary_text: str
    voice_metadata: VoiceMetadata


ApplyStatus = Literal["success", "partial", "failed"]


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: List[str] = Field(default_factory=list)


class ApplyStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    action: str
    result: str


class ApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: ApplyStatus
    steps: List[ApplyStep]
    notes: str


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    file_path: str
    format: Literal["json", "md", "txt", "jsonl"]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: Optional[str] = None
    analyze_response: Optional[AnalyzeResponse] = None
    apply_run: Optional[ApplyResponse] = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    generated_at_utc: str
    goal: str
    executive_summary: str
    highlights: List[str]
    artifact_refs: List[ArtifactReference]
    source: Literal["request_payload", "latest_cached", "mixed"]


class DiscoveryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    caller_arn: str
    principal_type: str


class DiscoverySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ec2_count: int
    rds_count: int
    s3_count: int
    autoscaling_count: int
    partial_failure_count: int
    cache_hit: bool = False


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_refresh: bool = False
    region: Optional[str] = None


class DiscoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: DiscoveryIdentity
    snapshot: Dict[str, Any]
    summary: DiscoverySummary
    warnings: List[str]
    discovery_mode: Literal["live_aws", "fallback"]
    discovered_at_utc: str


ExecutionMode = Literal["aws_api_safe_tag", "aws_console_safe"]
ExecutionAction = Literal["apply_demo_tag", "remove_demo_tag", "open_console_view"]
ResourceType = Literal["ec2", "rds", "s3", "autoscaling"]
ExecutionStatus = Literal["success", "partial", "failed", "blocked"]
PolicyClassification = Literal["read_only", "reversible_safe", "blocked"]


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: PolicyClassification
    allowed: bool
    requires_approval: bool
    reason: str
    warnings: List[str] = Field(default_factory=list)


class ExecuteRealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_mode: ExecutionMode
    resource_arn: str
    resource_type: ResourceType
    action: ExecutionAction
    approval_confirmed: bool
    notes: Optional[str] = None


class ExecuteStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    action: str
    result: str


class ExecuteRealResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: ExecutionStatus
    execution_mode: ExecutionMode
    steps: List[ExecuteStep]
    notes: str
    evidence_refs: List[ArtifactReference] = Field(default_factory=list)
    policy_decision: PolicyDecision
