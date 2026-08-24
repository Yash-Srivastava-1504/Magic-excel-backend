import json
import re
import time
import pandas as pd
from typing import List, Dict, Any, Optional, Set, Tuple
from app.models.schemas import CommandResponse, ComputeResult, PipelineOperation, DetectComputeAgentResponse, AgentCommandsResponse
from app.utils.llm_client import chat_completion, chat_completion_json, chat_completion_model, build_client, _log_llm_interaction
from app.utils.col_map import ColMap
from app.services.operations import process_command
from app.services.pipeline_engine import evaluate_aggregate
from app.config import settings
from app.prompts import (
    SYSTEM_PROMPT,
    DETECT_COMPUTE_AGENT_PROMPT,
    NAME_AGENT_PROMPT
)

async def run_detect_compute_stage(
    input_str: str, 
    columns: List[str], 
    preview_data: List[Dict[str, Any]], 
    scope_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    col_map = ColMap(columns)
    safe_columns = col_map.safe_columns()
    safe_data = [col_map.to_safe_row(r) for r in preview_data]
    
    user_msg = f"Available columns: {', '.join(safe_columns)}\n\n"
    if scope_ids:
        user_msg += f"Focus on selection of {len(scope_ids)} rows.\n"
    user_msg += f"Request: \"{input_str}\""

    detected = await chat_completion_model(
        DETECT_COMPUTE_AGENT_PROMPT,
        user_msg,
        DetectComputeAgentResponse,
        fallback=DetectComputeAgentResponse(),
        agent_name="Detect Compute Agent",
    )

    mode = detected.mode
    items = detected.items

    results: List[ComputeResult] = []
    df = pd.DataFrame(safe_data)  # build once; reused for every aggregate

    _fn_labels = {
        "avg": "Average", "average": "Average", "mean": "Average",
        "sum": "Sum", "min": "Min", "max": "Max",
        "median": "Median", "count": "Count", "std": "Std Dev",
    }

    for item in items:
        expr = item.computeExpression
        if not expr:
            continue

        sanitized_expr = col_map.sanitize_command(expr)
        # Match: avg(@col), average of @col, mean @col, etc.
        # Handle variations like 'average of', 'average of the', 'average(@col)'
        m = re.search(
            r'(avg|average|mean|sum|min|max|median|count|std)\s*(?:of(?:\s+the)?\s+)?\s*\(@?([^)]+)\)',
            sanitized_expr.strip(), re.I
        )
        if not m:
            continue

        fn = m.group(1).strip()
        col = m.group(2).strip().replace("@", "")

        value = evaluate_aggregate(fn, col, df, scope_ids)
        if value is None:
            continue

        label = f"{_fn_labels.get(fn.lower(), fn)} of {col}"
        expression = f"{fn}(@{col})"

        results.append(ComputeResult(
            label=col_map.restore_command(label),
            expression=col_map.restore_command(expression),
            value=value,
            columnSafe=col,
        ))

    if results:
        _log_llm_interaction(
            input_data=[{"expression": r.expression, "column": r.columnSafe} for r in results],
            response_content={r.label: r.value for r in results},
            agent_name="Aggregate Compute",
        )

    if mode == "compute_only" and results:
        return {
            "exitEarly": True,
            "computeResults": results,
            "plannerInput": input_str,
            "plainRewritten": input_str
        }

    # Rewrite query if aggregates found
    plain = input_str
    literals = {}
    for i, res in enumerate(results):
        label = res.label
        val = res.value
        literals[label] = val
        # To make aggregates dynamic for future datasets, we replace the aggregate wording
        # (e.g. "average of @Price") with the function syntax (e.g. "avg(@Price)") 
        # instead of the literal static value.
        from_str = items[i].replaceInQuery
        if from_str:
            plain = plain.replace(from_str, res.expression)

    planner_input = plain
    return {
        "exitEarly": False,
        "computeResults": results if mode == "compute_only" else [],
        "plannerInput": planner_input,
        "plainRewritten": plain
    }

async def run_agent(
    input_str: str,
    columns: List[str],
    preview_data: List[Dict[str, Any]],
    scope_ids: Optional[Set[int]] = None,
    editing_op: Optional[Any] = None,
    edit_mode: Optional[str] = "edit",
) -> List[PipelineOperation]:
    col_map = ColMap(columns)
    safe_columns = col_map.safe_columns()
    safe_data = [col_map.to_safe_row(r) for r in preview_data]

    user_msg = f"Available columns: {', '.join(safe_columns)}\n"
    if scope_ids:
        user_msg += f"Selection: {len(scope_ids)} rows.\n"

    # If editing an existing op, inject its full context so the LLM can make
    # a precise, surgical modification rather than generating from scratch.
    if editing_op is not None:
        op_dict = editing_op.dict() if hasattr(editing_op, 'dict') else editing_op
        if edit_mode == "replace":
            user_msg += (
                f"\nYou are REPLACING an existing operation.\n"
                f"Existing operation type : {op_dict.get('type')}\n"
                f"Existing operation label: {op_dict.get('label')}\n"
                f"Existing operation payload (JSON): {json.dumps(op_dict.get('payload', {}))}\n"
                f"\nThe user wants to REPLACE this operation entirely. You should output commands that represent the NEW capability requested.\n"
            )
        else:
            user_msg += (
                f"\nYou are MODIFYING an existing operation — do NOT create a new one from scratch.\n"
                f"Existing operation type : {op_dict.get('type')}\n"
                f"Existing operation label: {op_dict.get('label')}\n"
                f"Existing operation payload (JSON): {json.dumps(op_dict.get('payload', {}))}\n"
                f"\nApply ONLY the change the user requests. Keep every other field (column, conditions,"
                f" valueExpr, styleProp, etc.) exactly as-is unless explicitly mentioned.\n"
            )

    user_msg += f"Request: \"{input_str}\""

    result = await chat_completion_model(
        SYSTEM_PROMPT,
        user_msg,
        AgentCommandsResponse,
        fallback=AgentCommandsResponse(),
        agent_name="Pipeline Extraction Agent",
    )
    cmds = result.commands
    if cmds:
        return await _cmds_to_ops(cmds, safe_data, list(safe_columns), col_map, scope_ids)
    return []

async def _cmds_to_ops(cmds: List[str], safe_data, start_cols, col_map, scope_ids) -> List[PipelineOperation]:
    ops = []
    rolling_cols = list(start_cols)
    for cmd_str in cmds:
        cmd = cmd_str.strip()
        op_dict = process_command(cmd, rolling_cols)
        if op_dict:
            # Update rolling columns for next command decomposition insight
            if op_dict["type"] == "add_column":
                rolling_cols.append(op_dict["payload"].get("column"))
            elif op_dict["type"] == "rename_column":
                frm = op_dict["payload"].get("from")
                to = op_dict["payload"].get("to") or op_dict["payload"].get("newName")
                if frm in rolling_cols:
                    rolling_cols[rolling_cols.index(frm)] = to
            elif op_dict["type"] == "delete_column":
                c = op_dict["payload"].get("column")
                if c in rolling_cols: rolling_cols.remove(c)
            
            restored_op = col_map.restore_operation(op_dict)
            ops.append(PipelineOperation(**restored_op))
    return ops

async def generate_pipeline_operations(
    input_str: str,
    columns: List[str],
    preview_data: List[Dict[str, Any]],
    scope_ids: Optional[Set[int]] = None,
    editing_op: Optional[Any] = None,
    edit_mode: Optional[str] = "edit",
) -> List[PipelineOperation]:
    ops = await run_agent(input_str, columns, preview_data, scope_ids, editing_op=editing_op, edit_mode=edit_mode)
    return ops
