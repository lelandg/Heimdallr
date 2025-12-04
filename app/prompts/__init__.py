"""Prompt templates for LLM interactions.

This module provides reusable prompt templates for various
analysis and decision-making tasks.
"""
from __future__ import annotations

from .error_analysis import (
    ERROR_ANALYSIS_SYSTEM,
    ERROR_TRIAGE_SYSTEM,
    build_error_analysis_prompt,
    build_triage_prompt,
)

from .diagnosis import (
    ROOT_CAUSE_SYSTEM,
    build_root_cause_prompt,
    build_impact_analysis_prompt,
)

from .action_decision import (
    ACTION_DECISION_SYSTEM,
    build_action_decision_prompt,
    build_remediation_steps_prompt,
)

__all__ = [
    "ERROR_ANALYSIS_SYSTEM",
    "ERROR_TRIAGE_SYSTEM",
    "build_error_analysis_prompt",
    "build_triage_prompt",
    "ROOT_CAUSE_SYSTEM",
    "build_root_cause_prompt",
    "build_impact_analysis_prompt",
    "ACTION_DECISION_SYSTEM",
    "build_action_decision_prompt",
    "build_remediation_steps_prompt",
]
