"""
Module: streamlit_app.py

Purpose:
    This module supports Streamlit user interface for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the Streamlit user interface area and presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from api.client import AIAPIClient, FastAPIClientError


RECOMMENDATION_COLUMNS = [
    # Keep this list synchronized with AIRecommendationAPIService.RESPONSE_COLUMNS.
    "Workflow -> Session -> Mapping -> Transformations",
    "Assets",
    "Failures",
    "Root Cause",
    "AI Recommendation",
    "Priority",
    "AI Summary",
]
MATRIX_COLUMNS = [
    "Average Confidence",
    "F1 Score",
    "ML Accuracy",
    "ML Precision",
    "Model Success Rate",
    "Recall",
    "Total Evaluations",
]


def main() -> None:
    """
    Executes the main workflow for Streamlit user interface.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
    None.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    st.set_page_config(page_title="PC to IDMC AI Assistant", page_icon="AI", layout="wide")
    st.title("PowerCenter to IDMC AI Assistant")

    with st.sidebar:
        st.header("FastAPI")
        base_url = st.text_input(
            "Base URL",
            value=os.getenv("PC_IICS_API_BASE_URL", "http://127.0.0.1:8000"),
        )
        refresh = st.button("Refresh", type="primary", use_container_width=True)

    client = AIAPIClient(base_url=base_url)
    if refresh:
        st.cache_data.clear()

    evaluation_tab, recommendation_tab = st.tabs(["AI Evaluation", "AI Recommendations"])

    with evaluation_tab:
        render_evaluation(client)

    with recommendation_tab:
        render_recommendations(client)


@st.cache_data(ttl=60, show_spinner=False)
def load_evaluation(base_url: str) -> dict[str, object]:
    """
    Executes the load_evaluation workflow for Streamlit user interface.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            base_url (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    return AIAPIClient(base_url=base_url).evaluation()


@st.cache_data(ttl=60, show_spinner=False)
def load_recommendations(base_url: str) -> list[dict[str, object]]:
    """
    Executes the load_recommendations workflow for Streamlit user interface.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            base_url (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    return AIAPIClient(base_url=base_url).recommendations()


def render_evaluation(client: AIAPIClient) -> None:
    """
    Executes the render_evaluation workflow for Streamlit user interface.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            client (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    st.subheader("AI Evaluation Matrix")
    try:
        payload = load_evaluation(client.base_url)
    except FastAPIClientError as exc:
        st.error(str(exc))
        return

    matrix = payload.get("matrix", {})
    if not isinstance(matrix, dict):
        st.warning("Evaluation API returned no matrix data.")
        return

    values = {column: matrix.get(column, 0) for column in MATRIX_COLUMNS}
    metric_columns = st.columns(4)
    for index, (label, value) in enumerate(values.items()):
        metric_columns[index % 4].metric(label, value)

    st.dataframe(pd.DataFrame([values]), use_container_width=True, hide_index=True)


def render_recommendations(client: AIAPIClient) -> None:
    """
    Executes the render_recommendations workflow for Streamlit user interface.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            client (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that presents AI evaluation metrics and recommendation tables by calling the FastAPI backend. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    st.subheader("AI Recommendation Report")
    try:
        rows = load_recommendations(client.base_url)
    except FastAPIClientError as exc:
        st.error(str(exc))
        return

    if not rows:
        st.info("No unresolved validation failures are currently eligible for AI recommendations.")
        return

    dataframe = pd.DataFrame(rows)
    # Display only the stakeholder-facing recommendation columns in the requested order.
    dataframe = dataframe[[column for column in RECOMMENDATION_COLUMNS if column in dataframe.columns]]

    priority_filter = st.multiselect(
        "Priority",
        options=sorted(dataframe["Priority"].dropna().unique().tolist()) if "Priority" in dataframe else [],
        default=sorted(dataframe["Priority"].dropna().unique().tolist()) if "Priority" in dataframe else [],
    )
    if priority_filter and "Priority" in dataframe:
        dataframe = dataframe[dataframe["Priority"].isin(priority_filter)]

    if dataframe.empty:
        st.info("No recommendations match the selected filters.")
        return

    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    selected_index = st.selectbox(
        "Recommendation detail",
        options=list(dataframe.index),
        format_func=lambda index: (
            f"{dataframe.at[index, 'Workflow -> Session -> Mapping -> Transformations']} - "
            f"{dataframe.at[index, 'Failures']}"
        ),
    )
    selected = dataframe.loc[selected_index]
    left, right = st.columns([1, 1])
    left.markdown("**Root Cause**")
    left.write(selected.get("Root Cause", ""))
    right.markdown("**AI Summary**")
    right.write(selected.get("AI Summary", ""))
    st.markdown("**AI Recommendation**")
    st.write(selected.get("AI Recommendation", ""))


if __name__ == "__main__":
    main()


