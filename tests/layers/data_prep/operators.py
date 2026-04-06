import pandas as pd
import numpy as np
from typing import Callable, Any
from dataclasses import dataclass


@dataclass
class OperatorResult:
    tables: dict
    success: bool
    error: str = ""
    feedback: str = ""


class DataOperators:
    """
    Implements all data preparation operators inspired by DeepPrep paper.
    Each operator takes a dict of DataFrames and returns updated dict.
    """

    # ── DATA CLEANING ──────────────────────────────────────────────────────────
    @staticmethod
    def DropNA(tables: dict, table: str, subset: list = None, how: str = "any") -> OperatorResult:
        try:
            df = tables[table].copy()            if isinstance(subset, dict):
                subset = list(subset.keys())            tables[table] = df.dropna(subset=subset, how=how)
            rows_dropped = len(df) - len(tables[table])
            return OperatorResult(tables, True, feedback=f"Dropped {rows_dropped} rows with NA")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def MissingValueImputation(tables: dict, table: str, column: str, mode: str = "mean") -> OperatorResult:
        try:
            df = tables[table].copy()
            if mode == "mean":
                val = df[column].mean()
            elif mode == "median":
                val = df[column].median()
            elif mode == "mode":
                val = df[column].mode()[0]
            else:
                val = mode  # use as constant
            df[column] = df[column].fillna(val)
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Imputed {column} with {mode}={val}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Deduplicate(tables: dict, table: str, subset: list = None, keep: str = "first") -> OperatorResult:
        try:
            df = tables[table]
            before = len(df)
            if isinstance(subset, dict):
                subset = list(subset.keys())
            tables[table] = df.drop_duplicates(subset=subset, keep=keep)
            after = len(tables[table])
            return OperatorResult(tables, True, feedback=f"Removed {before - after} duplicates")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── VALUE NORMALIZATION ────────────────────────────────────────────────────
    @staticmethod
    def ValueTransform(tables: dict, table: str, column: str, expression: str) -> OperatorResult:
        """Apply a Python expression to a column. Expression uses 'x' as value."""
        try:
            tables[table] = tables[table].copy()
            tables[table][column] = tables[table][column].apply(
                lambda x: eval(expression, {"x": x, "pd": pd, "np": np})
            )
            return OperatorResult(tables, True, feedback=f"Transformed values in {column}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def CastType(tables: dict, table: str, column: str, dtype: str) -> OperatorResult:
        try:
            tables[table] = tables[table].copy()
            tables[table][column] = tables[table][column].astype(dtype)
            return OperatorResult(tables, True, feedback=f"Cast {column} to {dtype}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def StandardizeDatetime(tables: dict, table: str, column: str, fmt: str = None) -> OperatorResult:
        try:
            tables[table] = tables[table].copy()
            tables[table][column] = pd.to_datetime(
                tables[table][column], format=fmt, errors="coerce"
            )
            return OperatorResult(tables, True, feedback=f"Standardized {column} to datetime")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def NormalizeMinMax(tables: dict, table: str, column: str) -> OperatorResult:
        try:
            df = tables[table].copy()
            min_val = df[column].min()
            max_val = df[column].max()
            if max_val != min_val:
                df[column] = (df[column] - min_val) / (max_val - min_val)
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Min-max normalized {column}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def ZScoreNormalize(tables: dict, table: str, column: str) -> OperatorResult:
        try:
            df = tables[table].copy()
            mean = df[column].mean()
            std = df[column].std()
            if std != 0:
                df[column] = (df[column] - mean) / std
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Z-score normalized {column}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── SCHEMA EDITING ─────────────────────────────────────────────────────────
    @staticmethod
    def RenameColumn(tables: dict, table: str, rename_map: dict) -> OperatorResult:
        try:
            tables[table] = tables[table].rename(columns=rename_map)
            return OperatorResult(tables, True, feedback=f"Renamed columns: {rename_map}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def SelectColumn(tables: dict, table: str, columns: list) -> OperatorResult:
        try:
            available = [c for c in columns if c in tables[table].columns]
            missing = [c for c in columns if c not in tables[table].columns]
            if missing:
                return OperatorResult(
                    tables,
                    False,
                    error=f"Missing columns: {missing}",
                    feedback=f"Available columns: {list(tables[table].columns)}",
                )
            tables[table] = tables[table][available]
            return OperatorResult(tables, True, feedback=f"Selected {len(available)} columns")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def AddNewColumn(tables: dict, table: str, name: str, expression: str) -> OperatorResult:
        """Add column using a Python expression over existing columns."""
        try:
            df = tables[table].copy()
            df[name] = df.apply(
                lambda row: eval(expression, {"row": row, "pd": pd, "np": np}), axis=1
            )
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Added column {name}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def DropColumn(tables: dict, table: str, columns: list) -> OperatorResult:
        try:
            tables[table] = tables[table].drop(
                columns=[c for c in columns if c in tables[table].columns]
            )
            return OperatorResult(tables, True, feedback=f"Dropped columns: {columns}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── ROW SELECTION ──────────────────────────────────────────────────────────
    @staticmethod
    def Filter(tables: dict, table: str, condition: str) -> OperatorResult:
        """Filter rows using a pandas query string."""
        try:
            df = tables[table]
            before = len(df)
            tables[table] = df.query(condition)
            after = len(tables[table])
            return OperatorResult(tables, True, feedback=f"Filtered: {before} → {after} rows")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Sort(tables: dict, table: str, by: list, ascending: bool = True) -> OperatorResult:
        try:
            tables[table] = tables[table].sort_values(by=by, ascending=ascending)
            return OperatorResult(tables, True, feedback=f"Sorted by {by}, ascending={ascending}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Head(tables: dict, table: str, n: int = 100) -> OperatorResult:
        try:
            tables[table] = tables[table].head(n)
            return OperatorResult(tables, True, feedback=f"Kept top {n} rows")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Tail(tables: dict, table: str, n: int = 100) -> OperatorResult:
        try:
            tables[table] = tables[table].tail(n)
            return OperatorResult(tables, True, feedback=f"Kept last {n} rows")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── AGGREGATION ────────────────────────────────────────────────────────────
    @staticmethod
    def GroupBy(tables: dict, table: str, by: list, agg: dict) -> OperatorResult:
        try:
            if isinstance(by, dict):
                by = list(by.keys())
            result = tables[table].groupby(by).agg(agg).reset_index()
            tables[table] = result
            return OperatorResult(tables, True, feedback=f"GroupBy {by}, agg: {agg}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Aggregate(tables: dict, table: str, func: str = "sum") -> OperatorResult:
        """Aggregate entire numeric table with a single function."""
        try:
            agg_func = getattr(tables[table].select_dtypes("number"), func, None)
            if agg_func is None:
                return OperatorResult(tables, False, error=f"Unknown agg func: {func}")
            result = agg_func().to_frame().T.reset_index(drop=True)
            tables[table] = result
            return OperatorResult(tables, True, feedback=f"Aggregated with {func}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── TABLE COMBINATION ──────────────────────────────────────────────────────
    @staticmethod
    def Join(tables: dict, left: str, right: str, on, how: str = "inner") -> OperatorResult:
        try:
            result = pd.merge(tables[left], tables[right], on=on, how=how)
            result_name = f"{left}_{right}_join"
            tables[result_name] = result
            return OperatorResult(
                tables, True, feedback=f"Joined {left} × {right} on {on}: {len(result)} rows"
            )
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Union(tables: dict, table_names: list, how: str = "outer") -> OperatorResult:
        try:
            dfs = [tables[t] for t in table_names if t in tables]
            result = pd.concat(dfs, ignore_index=True)
            if how == "outer":
                result = result.drop_duplicates()
            result_name = "_".join(table_names) + "_union"
            tables[result_name] = result
            return OperatorResult(
                tables, True, feedback=f"Union of {table_names}: {len(result)} rows"
            )
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── TABLE RESHAPING ────────────────────────────────────────────────────────
    @staticmethod
    def Pivot(tables: dict, table: str, index: str, columns: str, values: str, aggfunc: str = "mean") -> OperatorResult:
        try:
            result = tables[table].pivot_table(
                index=index, columns=columns, values=values, aggfunc=aggfunc
            ).reset_index()
            result.columns.name = None
            tables[table] = result
            return OperatorResult(tables, True, feedback=f"Pivoted {table}: index={index}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Melt(tables: dict, table: str, id_vars: list, value_vars: list = None) -> OperatorResult:
        try:
            tables[table] = tables[table].melt(id_vars=id_vars, value_vars=value_vars)
            return OperatorResult(tables, True, feedback=f"Melted {table}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Explode(tables: dict, table: str, column: str) -> OperatorResult:
        try:
            tables[table] = tables[table].explode(column).reset_index(drop=True)
            return OperatorResult(
                tables, True, feedback=f"Exploded {column}: {len(tables[table])} rows"
            )
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def Transpose(tables: dict, table: str) -> OperatorResult:
        try:
            tables[table] = tables[table].T.reset_index()
            return OperatorResult(tables, True, feedback="Transposed table")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── FEATURE ENGINEERING ────────────────────────────────────────────────────
    @staticmethod
    def ExtractDatePart(tables: dict, table: str, column: str, part: str) -> OperatorResult:
        """Extract year/month/day/hour from datetime column."""
        try:
            df = tables[table].copy()
            dt_col = pd.to_datetime(df[column], errors="coerce")
            parts_map = {
                "year": dt_col.dt.year,
                "month": dt_col.dt.month,
                "day": dt_col.dt.day,
                "hour": dt_col.dt.hour,
                "dayofweek": dt_col.dt.dayofweek,
                "quarter": dt_col.dt.quarter,
            }
            if part not in parts_map:
                return OperatorResult(tables, False, error=f"Unknown date part: {part}")
            df[f"{column}_{part}"] = parts_map[part]
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Extracted {part} from {column}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def BinColumn(tables: dict, table: str, column: str, bins: int = 5, labels: list = None) -> OperatorResult:
        try:
            df = tables[table].copy()
            df[f"{column}_bin"] = pd.cut(df[column], bins=bins, labels=labels)
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Binned {column} into {bins} bins")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def OneHotEncode(tables: dict, table: str, column: str) -> OperatorResult:
        try:
            df = tables[table]
            dummies = pd.get_dummies(df[column], prefix=column)
            tables[table] = pd.concat([df.drop(columns=[column]), dummies], axis=1)
            return OperatorResult(
                tables, True, feedback=f"One-hot encoded {column}: {len(dummies.columns)} new cols"
            )
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    @staticmethod
    def FillConstant(tables: dict, table: str, column: str, value) -> OperatorResult:
        try:
            df = tables[table].copy()
            df[column] = df[column].fillna(value)
            tables[table] = df
            return OperatorResult(tables, True, feedback=f"Filled {column} NA with {value}")
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))

    # ── PROGRAM SYNTHESIS ──────────────────────────────────────────────────────
    @staticmethod
    def ExeCode(tables: dict, target: str, code: str) -> OperatorResult:
        """Execute LLM-synthesized Python code for custom transformations."""
        try:
            local_ns = {"tables": tables, "pd": pd, "np": np}
            exec(code, local_ns)  # noqa: S102
            if target in local_ns.get("tables", {}):
                tables = local_ns["tables"]
                return OperatorResult(
                    tables, True, feedback=f"Executed custom code, created {target}"
                )
            return OperatorResult(
                tables, False, error=f"Target table {target} not created by code"
            )
        except Exception as e:
            return OperatorResult(tables, False, error=str(e))
