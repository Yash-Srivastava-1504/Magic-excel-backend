import re
import logging
import pandas as pd

_log = logging.getLogger(__name__)
from typing import List, Dict, Any, Set, Optional
from app.models.schemas import (
    PipelineOperation,
    PipelineStep,
    PipelineExecutionResult,
    CellStyle,
    CellFont,
    CellFill,
    CellAlignment,
    OperationType
)
from app.services.pipeline_compiler import compile_conditions, compile_value_expr
from app.services.excel_parser import add_column_to_map


def execute_pipeline(
    raw_data: List[Dict[str, Any]],
    base_columns: List[str],
    base_styles: Dict[str, CellStyle],
    pipeline: List[PipelineOperation]
) -> PipelineExecutionResult:
    df = pd.DataFrame(raw_data)
    columns = list(base_columns)
    styles = {k: CellStyle(**v.dict()) if isinstance(v, CellStyle) else CellStyle(**v) for k, v in base_styles.items()}

    steps: List[PipelineStep] = []
    highlighted_row_ids: Set[int] = set()
    deleted_row_ids: Set[int] = set()
    active_scope_ids: Optional[Set[int]] = None

    for op in pipeline:
        try:
            if op.type == OperationType.compute:
                steps.append(PipelineStep(
                    operation=op,
                    affectedRowIds=[],
                    summary=op.payload.get("summary", "Compute operation"),
                    status="success"
                ))
                continue

            result = apply_operation_to_state(df, columns, styles, op, active_scope_ids, deleted_row_ids)
            df = result["df"]
            columns = result["columns"]
            styles = result["styles"]

            steps.append(PipelineStep(
                operation=op,
                affectedRowIds=list(result["affectedRowIds"]),
                summary=result["summary"],
                status="success"
            ))

            if op.type == OperationType.highlight:
                if result["affectedRowIds"]:
                    active_scope_ids = set(result["affectedRowIds"])
                    highlighted_row_ids.update(active_scope_ids)

            if op.type in [OperationType.delete_rows, OperationType.remove_duplicates]:
                deleted_row_ids.update(result["affectedRowIds"])

        except Exception as e:
            steps.append(PipelineStep(
                operation=op,
                affectedRowIds=[],
                summary="Error executing operation",
                status="error",
                errorMessage=str(e)
            ))

    return PipelineExecutionResult(
        transformedData=df.to_dict('records'),
        columns=columns,
        cellStyles=styles,
        steps=steps,
        highlightedRowIds=list(highlighted_row_ids),
        activeScopeIds=list(active_scope_ids) if active_scope_ids is not None else None,
        deletedRowIds=list(deleted_row_ids)
    )


def apply_operation_to_state(
    df: pd.DataFrame,
    columns: List[str],
    styles: Dict[str, CellStyle],
    op: PipelineOperation,
    scope_ids: Optional[Set[int]],
    already_deleted: Set[int]
) -> Dict[str, Any]:
    payload = op.payload
    active_mask = ~df["ID"].isin(already_deleted)
    active_df = df[active_mask]

    def apply_scope(ids: Set[int]) -> Set[int]:
        if scope_ids is None:
            return ids
        return {id_ for id_ in ids if id_ in scope_ids}

    affected_row_ids: Set[int] = set()
    summary = ""

    def expand_aggregates(expr: str, agg_df: pd.DataFrame) -> str:
        patterns = [
            (r'avg\(@(.*?)\)',     lambda s: pd.to_numeric(s, errors='coerce').dropna().mean()),
            (r'average\(@(.*?)\)', lambda s: pd.to_numeric(s, errors='coerce').dropna().mean()),
            (r'mean\(@(.*?)\)',    lambda s: pd.to_numeric(s, errors='coerce').dropna().mean()),
            (r'sum\(@(.*?)\)',     lambda s: pd.to_numeric(s, errors='coerce').dropna().sum()),
            (r'min\(@(.*?)\)',     lambda s: pd.to_numeric(s, errors='coerce').dropna().min()),
            (r'max\(@(.*?)\)',     lambda s: pd.to_numeric(s, errors='coerce').dropna().max()),
            (r'count\(@(.*?)\)',   lambda s: float(s.dropna().count())),
            (r'median\(@(.*?)\)',  lambda s: pd.to_numeric(s, errors='coerce').dropna().median()),
            (r'std\(@(.*?)\)',     lambda s: pd.to_numeric(s, errors='coerce').dropna().std()),
        ]

        expanded = expr
        sorted_cols = sorted(columns, key=len, reverse=True)

        for pattern, calc_fn in patterns:
            matches = list(re.finditer(pattern, expanded))
            for m in reversed(matches):
                content = m.group(1)
                matched_col = next((c for c in sorted_cols if content == c), None)
                if matched_col and matched_col in agg_df.columns:
                    res = calc_fn(agg_df[matched_col])
                    if pd.isna(res):
                        res = 0.0
                    replacement = str(round(float(res), 4))
                    expanded = expanded[:m.start()] + replacement + expanded[m.end():]
        return expanded

    if op.type == OperationType.delete_rows:
        conds = payload.get("conditions", [])
        expanded_conds = [{**c, "raw": expand_aggregates(c.get("raw", ""), active_df)} for c in conds]
        evaluator = compile_conditions(expanded_conds, columns)
        mask = active_df.apply(lambda row: evaluator(row.to_dict()), axis=1)
        to_delete = set(active_df[mask]["ID"].tolist())
        affected_row_ids = apply_scope(to_delete)
        summary = f"{len(affected_row_ids)} rows marked for deletion"

    elif op.type in [OperationType.update_cells, OperationType.update_cells_all]:
        col = payload.get("column") or payload.get("target")
        if not col:
            raise ValueError("No target column specified")
        if col not in columns:
            raise ValueError(f"Target column '@{col}' not found")

        conds = payload.get("conditions", [])
        expanded_conds = [{**c, "raw": expand_aggregates(c.get("raw", ""), active_df)} for c in conds]

        val_expr = payload.get("valueExpr")
        if val_expr:
            val_expr = expand_aggregates(val_expr, active_df)

        if op.type == OperationType.update_cells:
            evaluator = compile_conditions(expanded_conds, columns)
            cond_mask = active_df.apply(lambda row: evaluator(row.to_dict()), axis=1)
        else:
            cond_mask = pd.Series(True, index=active_df.index)

        if scope_ids is not None:
            cond_mask = cond_mask & active_df["ID"].isin(scope_ids)

        affected_indices = active_df[cond_mask].index
        affected_row_ids = set(df.loc[affected_indices, "ID"].tolist())

        # Ensure column can handle the value (e.g., float into int64)
        if col in df.columns:
            # If current column is int-like and we're setting a float, cast to float
            is_int = 'int' in str(df[col].dtype).lower()
            val = payload.get("value")
            if is_int and (isinstance(val, float) or (isinstance(val, str) and "." in val)):
                df[col] = df[col].astype(float)
            elif str(df[col].dtype) in ('string', 'StringDtype', 'boolean'):
                df[col] = df[col].astype(object)

        if val_expr:
            val_evaluator = compile_value_expr(val_expr, columns)
            result_series = df.loc[affected_indices].apply(
                lambda row: val_evaluator(row.to_dict()), axis=1
            )
            try:
                df.loc[affected_indices, col] = result_series
            except (TypeError, ValueError):
                df[col] = df[col].astype(object)
                df.loc[affected_indices, col] = result_series
        else:
            df.loc[affected_indices, col] = payload.get("value")

        summary = f"{len(affected_row_ids)} rows updated"

    elif op.type == OperationType.add_column:
        col_name = payload.get("column")
        if not col_name:
            raise ValueError("No column name provided")
        default_val = payload.get("value") or payload.get("default_value") or ""
        if col_name not in columns:
            columns.append(col_name)
        # Force object dtype so the column accepts any Python value (strings,
        # numbers, None). pandas 3.x re-infers StringDtype even for pd.array/
        # np.array with dtype=object when values are strings. pd.Series with
        # explicit dtype=object is the only reliable escape hatch.
        df[col_name] = pd.Series([default_val] * len(df), dtype=object, index=df.index)
        affected_row_ids = set(df["ID"].tolist())
        summary = f"Column '{col_name}' added"
        original_name = payload.get("originalName", col_name)
        try:
            add_column_to_map(col_name, original_name)
        except Exception as exc:
            _log.warning("Could not update column_maps.json: %s", exc)

    elif op.type == OperationType.delete_column:
        col_name = payload.get("column")
        if not col_name:
            raise ValueError("No column specified")
        if col_name in columns:
            columns.remove(col_name)
        if col_name in df.columns:
            df = df.drop(columns=[col_name])
        summary = f"Column '{col_name}' deleted"

    elif op.type == OperationType.rename_column:
        frm = payload.get("from")
        to = payload.get("to") or payload.get("newName")
        if not frm or not to:
            raise ValueError("Invalid rename operation")
        if frm in columns:
            idx = columns.index(frm)
            columns[idx] = to
        if frm in df.columns:
            df = df.rename(columns={frm: to})
        summary = f"Renamed '{frm}' to '{to}'"

    elif op.type == OperationType.highlight:
        conds = payload.get("conditions", [])
        expanded_conds = [{**c, "raw": expand_aggregates(c.get("raw", ""), active_df)} for c in conds]
        evaluator = compile_conditions(expanded_conds, columns)
        mask = active_df.apply(lambda row: evaluator(row.to_dict()), axis=1)
        to_highlight = set(active_df[mask]["ID"].tolist())
        affected_row_ids = apply_scope(to_highlight)
        summary = f"{len(affected_row_ids)} rows highlighted"

    elif op.type == OperationType.style:
        col = payload.get("column")
        if not col:
            raise ValueError("No target column specified")
        prop = payload.get("styleProp")
        val = payload.get("styleValue", "")
        conds = payload.get("conditions", [])

        expanded_conds = [{**c, "raw": expand_aggregates(c.get("raw", ""), active_df)} for c in conds] if conds else []
        evaluator = compile_conditions(expanded_conds, columns) if expanded_conds else (lambda r: True)

        non_deleted_df = df[active_mask]
        cond_mask = non_deleted_df.apply(lambda row: evaluator(row.to_dict()), axis=1)
        if scope_ids is not None:
            cond_mask = cond_mask & non_deleted_df["ID"].isin(scope_ids)

        for i in non_deleted_df[cond_mask].index:
            affected_row_ids.add(int(df.at[i, "ID"]))
            key = f"{i}:{col}"
            style = styles.get(key, CellStyle())

            if prop == "bold":
                style.font = (style.font or CellFont()).copy(update={"bold": True})
            elif prop == "italic":
                style.font = (style.font or CellFont()).copy(update={"italic": True})
            elif prop == "underline":
                style.font = (style.font or CellFont()).copy(update={"underline": True})
            elif prop == "strikethrough":
                style.font = (style.font or CellFont()).copy(update={"strikethrough": True})
            elif prop == "color":
                style.font = (style.font or CellFont()).copy(update={"color": val.replace("#", "")})
            elif prop == "bgcolor":
                style.fill = (style.fill or CellFill()).copy(update={"bgColor": val.replace("#", "")})
            elif prop == "fontsize":
                try:
                    style.font = (style.font or CellFont()).copy(update={"size": float(val)})
                except Exception:
                    pass
            elif prop == "align":
                style.alignment = (style.alignment or CellAlignment()).copy(update={"horizontal": val})

            styles[key] = style

        summary = f"{len(affected_row_ids)} cells styled"

    elif op.type == OperationType.remove_duplicates:
        valid_cols = [c for c in columns if c in active_df.columns]
        dup_mask = active_df.duplicated(subset=valid_cols, keep='first')
        if scope_ids is not None:
            dup_mask = dup_mask & active_df["ID"].isin(scope_ids)
        affected_row_ids = set(active_df[dup_mask]["ID"].tolist())
        summary = f"{len(affected_row_ids)} duplicates marked for removal"

    return {
        "df": df,
        "columns": columns,
        "styles": styles,
        "affectedRowIds": affected_row_ids,
        "summary": summary
    }


def evaluate_aggregate(
    fn: str,
    col: str,
    df: pd.DataFrame,
    scope_ids: Optional[Set[int]] = None
) -> Optional[float]:
    """Evaluate a single aggregate function on a column using pandas."""
    if col not in df.columns:
        return None
    working = df[df["ID"].isin(scope_ids)] if scope_ids else df
    series = pd.to_numeric(working[col], errors='coerce').dropna()
    fn_lower = fn.lower()
    if fn_lower == "count":
        return int(working[col].dropna().count())
    if series.empty:
        return None
    if fn_lower in ("avg", "average", "mean"):
        return round(float(series.mean()), 4)
    if fn_lower == "sum":
        return round(float(series.sum()), 4)
    if fn_lower == "min":
        return round(float(series.min()), 4)
    if fn_lower == "max":
        return round(float(series.max()), 4)
    if fn_lower == "median":
        return round(float(series.median()), 4)
    if fn_lower == "std":
        return round(float(series.std()), 4) if len(series) > 1 else 0.0
    return None
