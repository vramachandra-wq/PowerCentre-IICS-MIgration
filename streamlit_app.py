"""
Support streamlit app for PowerCenter to IICS migration support.
Keeps the application workflow organized.
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
    """Handle main for the migration workflow."""

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
    """Load evaluation using the provided base_url."""

    return AIAPIClient(base_url=base_url).evaluation()


@st.cache_data(ttl=60, show_spinner=False)
def load_recommendations(base_url: str) -> list[dict[str, object]]:
    """Load recommendations using the provided base_url."""

    return AIAPIClient(base_url=base_url).recommendations()


def render_evaluation(client: AIAPIClient) -> None:
    """Render evaluation using the provided client."""

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
    """Render recommendations using the provided client."""

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


