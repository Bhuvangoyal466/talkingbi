"""
Execution engine for DeepPrep pipelines.
Handles feedback loop and retry logic for failed operators.
"""
import copy
from typing import Callable
import pandas as pd
from core.logger import logger
from layers.data_prep.operators import DataOperators, OperatorResult
from layers.data_prep.pipeline_builder import PipelineBuilder, OP_MAP


class PipelineExecutor:
    """
    Executes a data preparation pipeline with operator-level feedback.
    Supports retry with modified parameters on failure.
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.builder = PipelineBuilder()

    def execute(self, tables: dict, operator_specs: list) -> dict:
        """
        Execute operators sequentially with feedback collection.

        Returns:
            {
                "tables": dict[str, DataFrame],
                "log": list of step feedback strings,
                "failed_ops": list of failed operator names,
                "success": bool
            }
        """
        current = copy.deepcopy(tables)
        log = []
        failed_ops = []

        for spec in operator_specs:
            op_name = spec.get("name")
            params = spec.get("params", {})

            if op_name not in OP_MAP:
                log.append(f"SKIP: Unknown operator '{op_name}'")
                continue

            op_func = OP_MAP[op_name]
            success = False

            for attempt in range(self.max_retries + 1):
                try:
                    result: OperatorResult = op_func(current, **params)
                    if result.success:
                        current = result.tables
                        log.append(f"OK [{op_name}]: {result.feedback}")
                        success = True
                        break
                    else:
                        log.append(f"FAIL [{op_name}] attempt {attempt + 1}: {result.error}")
                except Exception as exc:
                    log.append(f"EXCEPTION [{op_name}] attempt {attempt + 1}: {exc}")

            if not success:
                failed_ops.append(op_name)

        return {
            "tables": current,
            "log": log,
            "failed_ops": failed_ops,
            "success": len(failed_ops) == 0,
        }
