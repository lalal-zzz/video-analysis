"""Evidence and falsifiable forecasts for a daily A-share research journal."""
from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

SHANGHAI = timezone(timedelta(hours=8))


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MarketMetric(EvidenceModel):
    value: float
    unit: str = Field(min_length=1)  # pct, CNY_100m, points, count, etc.
    source_url: HttpUrl
    observed_at: AwareDatetime
    note: str = ""


class MarketSnapshot(EvidenceModel):
    trading_date: date
    is_trading_day: bool
    stage: Literal["preopen", "intraday", "close", "holiday"]
    previous_trading_date: date | None = None
    next_trading_date: date | None = None
    calendar_source_url: HttpUrl
    metrics: dict[str, MarketMetric] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_calendar(self) -> "MarketSnapshot":
        if (self.stage == "holiday") == self.is_trading_day:
            raise ValueError("holiday stage and is_trading_day disagree")
        if self.previous_trading_date and self.previous_trading_date >= self.trading_date:
            raise ValueError("previous trading date must be earlier")
        if self.next_trading_date and self.next_trading_date <= self.trading_date:
            raise ValueError("next trading date must be later")
        return self


class Forecast(EvidenceModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    creator: str = Field(min_length=1)
    creator_url: HttpUrl
    source_url: HttpUrl
    source_published_at: AwareDatetime
    transcript_artifact: str = Field(min_length=1)
    timestamp_seconds: float = Field(ge=0)
    statement: str = Field(min_length=1)
    target_trading_date: date
    metric: str | None = None
    unit: str | None = None
    operator: Literal["gt", "gte", "lt", "lte", "between"] | None = None
    threshold: float | None = None
    upper: float | None = None
    condition: str = ""
    # Conditions cannot be silently resolved from prose by the numerical scorer.
    scorable: bool = False
    not_scorable_reason: str = ""

    @model_validator(mode="after")
    def valid_rule(self) -> "Forecast":
        if self.scorable:
            if not self.metric or not self.unit or self.operator is None or self.threshold is None:
                raise ValueError("scorable forecasts need metric, unit, operator and threshold")
            if self.condition:
                raise ValueError("conditional prose needs human review; use scorable=false")
            if self.operator == "between" and (self.upper is None or self.upper < self.threshold):
                raise ValueError("between needs an upper bound at least as large as threshold")
        elif not self.not_scorable_reason.strip():
            raise ValueError("unscorable forecasts need a reason")
        return self


class DailyResearch(EvidenceModel):
    trading_date: date
    cutoff_at: AwareDatetime
    market: MarketSnapshot
    report: str = Field(min_length=1)
    transcript_artifacts: list[str] = Field(default_factory=list)
    forecasts: list[Forecast] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_evidence_window(self) -> "DailyResearch":
        if self.market.trading_date != self.trading_date:
            raise ValueError("market date must match report trading date")
        if self.cutoff_at.astimezone(SHANGHAI).date() != self.trading_date:
            raise ValueError("cutoff must fall on the report date in Asia/Shanghai")
        if len({f.id for f in self.forecasts}) != len(self.forecasts):
            raise ValueError("forecast IDs must be unique")
        for metric in self.market.metrics.values():
            if metric.observed_at > self.cutoff_at:
                raise ValueError("market evidence cannot come after cutoff")
            if metric.observed_at.astimezone(SHANGHAI).date() != self.trading_date:
                raise ValueError("market metrics must describe the report date")
        for forecast in self.forecasts:
            if forecast.source_published_at > self.cutoff_at:
                raise ValueError("forecast source cannot come after cutoff")
            if forecast.target_trading_date <= self.trading_date:
                raise ValueError("new forecasts must target a future trading date")
            if forecast.transcript_artifact not in self.transcript_artifacts:
                raise ValueError("forecast transcript must be included in source artifacts")
        return self


class SavedDailyResearch(EvidenceModel):
    revision: str
    saved_at: AwareDatetime
    record: DailyResearch
