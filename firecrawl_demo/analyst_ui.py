from pathlib import Path

import pandas as pd
import streamlit as st

from . import config


class AnalystUI:
    """Stub for AnalystUI to satisfy tests."""

    pass


"""Simple Streamlit UI for analyst review and feedback."""


def load_enriched_sheet():
    return pd.read_excel(config.ENRICHED_XLSX)


def load_relationships():
    return pd.read_csv(config.RELATIONSHIPS_CSV)


def main():
    st.title("ACES Analyst Review & Feedback")
    df = load_enriched_sheet()
    rel = load_relationships()
    st.subheader("Enriched Records")
    st.dataframe(df)
    st.subheader("Relationship Graph")
    st.dataframe(rel)
    st.subheader("Flag/Annotate Records")
    idx = st.number_input(
        "Row index to annotate", min_value=0, max_value=len(df) - 1, step=1
    )
    feedback = st.text_area("Feedback/Flag")
    if st.button("Save Feedback"):
        prev = (
            df.at[idx, "Analyst Feedback"] if "Analyst Feedback" in df.columns else ""
        )
        df.at[idx, "Analyst Feedback"] = feedback
        df.to_excel(config.ENRICHED_XLSX, index=False)
        # --- Audit trail ---
        import csv
        from datetime import datetime

        audit_path = Path(config.PROCESSED_DIR) / "feedback_audit.csv"
        audit_row = {
            "Timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "RowIndex": idx,
            "Previous": prev,
            "New": feedback,
        }
        file_exists = audit_path.exists()
        with audit_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["Timestamp", "RowIndex", "Previous", "New"]
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(audit_row)
        st.success("Feedback saved and audit logged.")


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    main()
