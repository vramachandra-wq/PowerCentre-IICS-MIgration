"""
Support prompt builder for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from automation.ai.recommendation_models import FailureRecord


class RecommendationPromptBuilder:
    """Encapsulates recommendation prompt builder behavior for migration workflows."""

    REQUIRED_KEYS = ["root_cause", "recommendation", "priority", "summary", "confidence"]

    def build(self, failure: FailureRecord) -> str:
        """Build migration data using the provided failure."""

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
