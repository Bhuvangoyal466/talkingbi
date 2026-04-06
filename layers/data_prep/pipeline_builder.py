"""
Pipeline builder: converts an ordered list of operator specs into
a callable pipeline function for the DeepPrep executor.
"""
import copy
from typing import Callable
from layers.data_prep.operators import DataOperators, OperatorResult
from core.logger import logger


OP_MAP = {
    "DropNA": DataOperators.DropNA,
    "MissingValueImputation": DataOperators.MissingValueImputation,
    "Deduplicate": DataOperators.Deduplicate,
    "ValueTransform": DataOperators.ValueTransform,
    "CastType": DataOperators.CastType,
    "StandardizeDatetime": DataOperators.StandardizeDatetime,
    "NormalizeMinMax": DataOperators.NormalizeMinMax,
    "ZScoreNormalize": DataOperators.ZScoreNormalize,
    "RenameColumn": DataOperators.RenameColumn,
    "SelectColumn": DataOperators.SelectColumn,
    "AddNewColumn": DataOperators.AddNewColumn,
    "DropColumn": DataOperators.DropColumn,
    "Filter": DataOperators.Filter,
    "Sort": DataOperators.Sort,
    "Head": DataOperators.Head,
    "GroupBy": DataOperators.GroupBy,
    "Join": DataOperators.Join,
    "Union": DataOperators.Union,
    "Pivot": DataOperators.Pivot,
    "Melt": DataOperators.Melt,
    "Explode": DataOperators.Explode,
    "ExtractDatePart": DataOperators.ExtractDatePart,
    "BinColumn": DataOperators.BinColumn,
    "OneHotEncode": DataOperators.OneHotEncode,
    "FillConstant": DataOperators.FillConstant,
    "ExeCode": DataOperators.ExeCode,
}


class PipelineBuilder:
    """
    Builds a callable data pipeline from a list of operator specifications.

    Each spec is a dict: {"name": "DropNA", "params": {"table": "main"}}
    """

    def build(self, operator_specs: list) -> Callable:
        """Return a function that applies the operator sequence to a tables dict."""
        valid_specs = [s for s in operator_specs if s.get("name") in OP_MAP]

        def pipeline(tables: dict) -> dict:
            current = copy.deepcopy(tables)
            for spec in valid_specs:
                op_name = spec["name"]
                params = spec.get("params", {})
                op_func = OP_MAP[op_name]
                try:
                    result: OperatorResult = op_func(current, **params)
                    if result.success:
                        current = result.tables
                        logger.debug(f"Pipeline op '{op_name}': {result.feedback}")
                    else:
                        logger.warning(f"Pipeline op '{op_name}' failed: {result.error}")
                except Exception as exc:
                    logger.error(f"Pipeline op '{op_name}' exception: {exc}")
            return current

        return pipeline
