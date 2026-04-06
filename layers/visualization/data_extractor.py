import json
import pandas as pd
from typing import Optional
from core.llm_client import llm
from core.logger import logger
from layers.visualization.intent_decomposer import IntentDecomposer


class DataExtractor:
    """
    Implements Doc2Chart's iterative data extraction and refinement.
    Validates extracted data for completeness and intent alignment.
    """

    def __init__(self):
        self.decomposer = IntentDecomposer()
        self.max_refinement = 2

    def extract(self, intent: str, df: pd.DataFrame, context: str = "") -> dict:
        """
        Main extraction loop: Extract → Validate → Refine/Re-extract.
        Returns structured chart-ready JSON.
        """
        cols = list(df.columns)
        dtypes = {col: str(df[col].dtype) for col in cols}
        decomposed = self.decomposer.decompose(intent, cols, column_types=dtypes)

        extracted = self._extract_from_df(df, decomposed, intent)

        for attempt in range(self.max_refinement + 1):
            validation = self._validate(intent, extracted, df, decomposed)
            confidence = validation.get("confidence_score", 0)
            logger.info(f"Extraction attempt {attempt + 1}: confidence={confidence}")

            if not validation.get("needs_re_extraction", False) or attempt == self.max_refinement:
                corrections = validation.get("suggested_corrections_for_refinement", [])
                if corrections:
                    extracted = self._refine(extracted, corrections, intent, df)
                break
            else:
                feedback = validation.get("feedback_for_re_extraction", "")
                extracted = self._extract_from_df(df, decomposed, intent, feedback)

        return extracted

    def _extract_from_df(
        self, df: pd.DataFrame, decomposed: dict, intent: str, feedback: str = ""
    ) -> dict:
        """Directly extract data from DataFrame using decomposed intent."""
        x_col = decomposed.get("x_axis")
        y_col = decomposed.get("y_axis")
        cat_col = decomposed.get("category")
        agg = decomposed.get("aggregation", "none")
        title = decomposed.get("title", intent[:60])

        # Ensure y_col is a numeric column; auto-correct if not
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return self._llm_extract(df, intent, feedback)
        if y_col not in numeric_cols:
            alt = next((c for c in numeric_cols if c != x_col), numeric_cols[0])
            logger.warning(f"y_col '{y_col}' is non-numeric; auto-selecting '{alt}'")
            y_col = alt

        # Ensure x_col exists; default to first non-numeric column or first column
        if x_col not in df.columns:
            str_cols = df.select_dtypes(exclude="number").columns.tolist()
            x_col = str_cols[0] if str_cols else df.columns[0]

        try:
            work_df = df.copy()

            # Apply aggregation if needed
            if agg != "none" and x_col in df.columns and y_col in df.columns:
                group_cols = [x_col]
                if cat_col and cat_col in df.columns:
                    group_cols.append(cat_col)
                agg_func = {"sum": "sum", "mean": "mean", "count": "count"}.get(agg, "mean")
                work_df = work_df.groupby(group_cols)[y_col].agg(agg_func).reset_index()

            values = []
            for _, row in work_df.head(500).iterrows():
                try:
                    x_val = str(row[x_col]) if x_col in row.index else str(row.iloc[0])
                    y_val = float(row[y_col]) if y_col in row.index else float(row.iloc[1])
                    entry = {"x": x_val, "y": y_val}
                    if cat_col and cat_col in row.index:
                        entry["category"] = str(row[cat_col])
                    values.append(entry)
                except (ValueError, TypeError):
                    continue

            if not values:
                return self._llm_extract(df, intent, feedback)

            return {
                "values": values,
                "x_axis_label": x_col or "X",
                "y_axis_label": y_col or "Y",
                "title": title,
            }
        except Exception as e:
            logger.error(f"Direct extraction failed: {e}")
            return self._llm_extract(df, intent, feedback)

    def _llm_extract(self, df: pd.DataFrame, intent: str, feedback: str = "") -> dict:
        """LLM-based extraction fallback."""
        sample = df.head(10).to_dict(orient="records")
        prompt = f"""Extract chart data from this dataframe sample.
Intent: {intent}
{"Feedback: " + feedback if feedback else ""}
Sample data: {json.dumps(sample, indent=2, default=str)}

Return JSON with structure:
{{
  "values": [{{"x": "...", "y": 0.0, "category": "optional"}}],
  "x_axis_label": "...",
  "y_axis_label": "...",
  "title": "..."
}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            return json.loads(resp)
        except Exception:
            return {
                "values": [],
                "x_axis_label": "X",
                "y_axis_label": "Y",
                "title": intent[:50],
            }

    def _validate(self, intent: str, extracted: dict, df: pd.DataFrame, decomposed: dict) -> dict:
        """Validate extracted data against intent and source."""
        n_values = len(extracted.get("values", []))
        total_rows = len(df)

        prompt = f"""Validate this extracted chart data.
Original Intent: {intent}
Expected columns: x={decomposed.get('x_axis')}, y={decomposed.get('y_axis')}
Extracted {n_values} data points from {total_rows} source rows.
Extracted data preview: {json.dumps(extracted.get('values', [])[:5], indent=2)}

Return JSON:
{{
  "needs_re_extraction": false,
  "feedback_for_re_extraction": "",
  "suggested_corrections_for_refinement": [],
  "confidence_score": 7
}}"""
        try:
            resp = llm.chat(prompt, json_mode=True)
            return json.loads(resp)
        except Exception:
            return {"needs_re_extraction": False, "confidence_score": 7}

    def _refine(self, extracted: dict, corrections: list, intent: str, df: pd.DataFrame) -> dict:
        """Apply minor corrections to extracted data."""
        for correction in corrections:
            if not isinstance(correction, dict):
                continue
            field = correction.get("field_path", "")
            suggested = correction.get("suggested_value")
            if suggested:
                if field == "title":
                    extracted["title"] = suggested
                elif field == "x_axis_label":
                    extracted["x_axis_label"] = suggested
                elif field == "y_axis_label":
                    extracted["y_axis_label"] = suggested
        return extracted
