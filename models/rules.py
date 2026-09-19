from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .video import VideoMetadata


class Rule(BaseModel):
    rule_type: str = ""

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        raise NotImplementedError


class FieldCompareRule(Rule):
    rule_type: Literal["field_compare"] = "field_compare"
    field: str
    operator: str  # "gt" | "gte" | "lt" | "lte" | "eq"
    value: float

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        def get_value(v: VideoMetadata) -> float:
            if hasattr(v.stats, self.field):
                return float(getattr(v.stats, self.field, 0))
            if hasattr(v, self.field):
                val = getattr(v, self.field)
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, datetime):
                    return val.timestamp()
            return 0.0

        ops = {
            "gt": lambda a, b: a > b,
            "gte": lambda a, b: a >= b,
            "lt": lambda a, b: a < b,
            "lte": lambda a, b: a <= b,
            "eq": lambda a, b: a == b,
        }
        op = ops.get(self.operator)
        if op is None:
            return videos
        return [v for v in videos if op(get_value(v), self.value)]


class AuthorInRule(Rule):
    rule_type: Literal["author_in"] = "author_in"
    authors: list[str]

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        return [v for v in videos if v.author in self.authors]


class KeywordInTitleRule(Rule):
    rule_type: Literal["keyword_in_title"] = "keyword_in_title"
    keywords: list[str]
    match_all: bool = False

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        def matches(v: VideoMetadata) -> bool:
            title_lower = v.title.lower()
            if self.match_all:
                return all(k.lower() in title_lower for k in self.keywords)
            return any(k.lower() in title_lower for k in self.keywords)
        return [v for v in videos if matches(v)]


class DateRangeRule(Rule):
    rule_type: Literal["date_range"] = "date_range"
    after: datetime | None = None
    before: datetime | None = None

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        def matches(v: VideoMetadata) -> bool:
            if v.publish_time is None:
                return False
            if self.after is not None and v.publish_time < self.after:
                return False
            if self.before is not None and v.publish_time > self.before:
                return False
            return True
        return [v for v in videos if matches(v)]


class SortRule(Rule):
    rule_type: Literal["sort"] = "sort"
    sort_by: str
    descending: bool = True
    top_n: int | None = None

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        def sort_key(v: VideoMetadata):
            if hasattr(v.stats, self.sort_by):
                return getattr(v.stats, self.sort_by, 0)
            if hasattr(v, self.sort_by):
                val = getattr(v, self.sort_by)
                if isinstance(val, datetime):
                    return val.timestamp()
                if isinstance(val, (int, float)):
                    return val
            return 0

        sorted_videos = sorted(videos, key=sort_key, reverse=self.descending)
        if self.top_n is not None:
            return sorted_videos[: self.top_n]
        return sorted_videos


class AndRule(Rule):
    rule_type: Literal["and"] = "and"
    rules: list["RuleUnion"] = Field(default_factory=list)

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        result = videos
        for rule in self.rules:
            result = rule.apply(result)
        return result


class OrRule(Rule):
    rule_type: Literal["or"] = "or"
    rules: list["RuleUnion"] = Field(default_factory=list)

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        matched: set[str] = set()
        for rule in self.rules:
            for v in rule.apply(videos):
                matched.add(v.video_id)
        seen: set[str] = set()
        result: list[VideoMetadata] = []
        for v in videos:
            if v.video_id in matched and v.video_id not in seen:
                seen.add(v.video_id)
                result.append(v)
        return result


RuleUnion = Annotated[
    Union[
        FieldCompareRule,
        AuthorInRule,
        KeywordInTitleRule,
        DateRangeRule,
        SortRule,
        AndRule,
        OrRule,
    ],
    Field(discriminator="rule_type"),
]


class SelectorConfig(BaseModel):
    rules: list[RuleUnion] = Field(default_factory=list)
    platform: str = ""

    def apply(self, videos: list[VideoMetadata]) -> list[VideoMetadata]:
        for rule in self.rules:
            videos = rule.apply(videos)
        return videos