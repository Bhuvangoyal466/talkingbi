"""
Unit tests for data preparation operators.
"""
import pandas as pd
import pytest
from layers.data_prep.operators import DataOperators


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "a": [1, 2, None, 4, 2],
            "b": ["x", "y", "x", None, "y"],
            "c": [10.0, 20.0, 30.0, 40.0, 20.0],
        }
    )


class TestDropNA:
    def test_drops_rows_with_any_null(self, df):
        result = DataOperators.DropNA({"main": df}, table="main")
        assert result.success
        assert result.tables["main"].isna().sum().sum() == 0

    def test_drops_specific_subset(self, df):
        result = DataOperators.DropNA({"main": df}, table="main", subset=["a"])
        assert result.success
        assert result.tables["main"]["a"].isna().sum() == 0


class TestDeduplicate:
    def test_removes_duplicates(self, df):
        result = DataOperators.Deduplicate({"main": df}, table="main")
        assert result.success
        assert len(result.tables["main"]) < len(df)

    def test_subset_dedup(self, df):
        result = DataOperators.Deduplicate({"main": df}, table="main", subset=["b"])
        assert result.success
        # Only unique values of b: x, y, None
        assert len(result.tables["main"]) <= 3


class TestRenameColumn:
    def test_renames(self, df):
        result = DataOperators.RenameColumn({"main": df}, table="main", rename_map={"a": "alpha", "b": "beta"})
        assert result.success
        assert "alpha" in result.tables["main"].columns
        assert "beta" in result.tables["main"].columns


class TestSelectColumn:
    def test_selects_columns(self, df):
        result = DataOperators.SelectColumn({"main": df}, table="main", columns=["a", "c"])
        assert result.success
        assert list(result.tables["main"].columns) == ["a", "c"]


class TestSort:
    def test_sort_ascending(self, df):
        result = DataOperators.Sort({"main": df}, table="main", by=["c"], ascending=True)
        assert result.success
        vals = result.tables["main"]["c"].dropna().tolist()
        assert vals == sorted(vals)


class TestGroupBy:
    def test_sum_aggregation(self):
        df_clean = pd.DataFrame({"cat": ["A", "B", "A", "B"], "val": [1, 2, 3, 4]})
        result = DataOperators.GroupBy({"main": df_clean}, table="main", by=["cat"], agg={"val": "sum"})
        assert result.success
        out = result.tables["main"].set_index("cat")
        assert out.loc["A", "val"] == 4
        assert out.loc["B", "val"] == 6


class TestNormalizeMinMax:
    def test_output_in_zero_one(self):
        df_numeric = pd.DataFrame({"x": [0.0, 5.0, 10.0], "y": [1.0, 2.0, 3.0]})
        result = DataOperators.NormalizeMinMax({"main": df_numeric}, table="main", column="x")
        assert result.success
        x = result.tables["main"]["x"]
        assert x.min() == pytest.approx(0.0)
        assert x.max() == pytest.approx(1.0)

