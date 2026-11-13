"""Placeholders for future Pydantic review-result schemas."""

from pydantic import BaseModel, Field
from typing import Literal


class Finding(BaseModel):
    """TODO: Design the structured fields for one actionable review finding."""

class ReviewFinding(BaseModel):
    file: str
    line: int| None=None
    severity: Literal["Critical", "High", "Medium", "Low"]
    category: Literal["correctness","security","performance","reliability"]
    explanation: str
    evidence: str
    suggested_fix: str

class ReviewResult(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)


# class VerifyFindings(BaseModel):
    
    

