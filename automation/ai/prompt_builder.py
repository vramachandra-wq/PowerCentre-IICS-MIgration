"""
Module: automation/ai/prompt_builder.py

Purpose:
    This module supports AI recommendation and evaluation support for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the AI recommendation and evaluation support area and connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from automation.ai.recommendation_models import FailureRecord


class RecommendationPromptBuilder:
    """Builds strict JSON prompts for migration recommendation generation."""

    REQUIRED_KEYS = ["root_cause", "recommendation", "priority", "summary", "confidence"]

    def build(self, failure: FailureRecord) -> str:
        """
        Executes the build workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                failure (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload = asdict(failure)
        return (
            "Analyze this unresolved PowerCenter to Informatica Cloud migration validation failure. "
            "Return STRICT JSON only with keys: root_cause, recommendation, priority, summary, confidence. "
            "priority must be one of Critical, High, Medium, Low. confidence must be 0-100. "
            "Do not modify XML. Do not generate auto-fix code. Provide concise, actionable IDMC migration guidance.\n\n"
            "Recommendation writing requirements:\n"
            "- The recommendation must be professional, specific, and implementation-oriented.\n"
            "- Explain the recommended migration action, the validation expectation, and the business or deployment risk it reduces.\n"
            "- Reference IDMC concepts such as supported mapping design, transformation configuration, mapping task validation, connection configuration, or functional validation when relevant.\n"
            "- Avoid generic one-line advice. Prefer 2-4 concise sentences that a Solution Architect could present to a migration team.\n"
            "- Never use the words or phrases: Manual, Manual Fix, Manual Intervention, Requires Manual Review, Please review manually.\n"
            "- Prefer: Expert Review Recommended, Configuration Update Recommended, Requires Functional Validation, Requires Business Validation, Needs Migration Review, Requires Rule-Based Validation, Migration Assistance Recommended.\n\n"
            "Summary writing requirements:\n"
            "- The summary must be executive, stakeholder-ready, and consultant-style.\n"
            "- Use the migration_context metrics to make the summary dynamic and specific.\n"
            "- Write 120-180 words when the available context supports it.\n"
            "- Mention readiness, successful conversions, validation accuracy, rule-engine findings, AI-assisted recommendations, risk, and unsupported-object complexity when relevant.\n"
            "- If success rate is above 95%, describe excellent migration readiness and limited review effort.\n"
            "- If success rate is 80-95%, describe strong readiness with focused AI-assisted validation recommendations.\n"
            "- If success rate is below 80%, describe moderate migration complexity and phased remediation before deployment.\n"
            "- Never use the words or phrases: Manual, Manual Fix, Manual Intervention, Requires Manual Review, Please review manually.\n"
            "- Prefer: Expert Review Recommended, Configuration Update Recommended, Requires Functional Validation, Requires Business Validation, Needs Migration Review, Requires Rule-Based Validation, Migration Assistance Recommended.\n\n"
            f"Failure record:\n{json.dumps(payload, indent=2, sort_keys=True)}"
        )
