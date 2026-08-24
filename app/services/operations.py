import re
import time
import random
import string
from typing import List, Dict, Any, Optional
from app.services.pipeline_compiler import SafeEvaluator
from app.utils.compute_agg import compute_agg

def generate_id(prefix: str = "op") -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{int(time.time())}_{suffix}"

def greedy_column_lookup(text: str, columns: List[str]) -> Optional[Dict[str, str]]:
    sorted_cols = sorted(columns, key=len, reverse=True)
    lower_text = text.lower()
    for col in sorted_cols:
        if lower_text.startswith(col.lower()):
            return {"col": col, "remaining": text[len(col):]}
    return None

def _strip_outer_parens(s: str) -> str:
    """Strip outer parentheses only when they wrap the entire expression."""
    while s.startswith('(') and s.endswith(')'):
        # Walk forward to find where the first '(' closes — if it closes at the
        # very last character the parens wrap everything and are safe to remove.
        depth = 0
        closes_at_end = False
        for i, ch in enumerate(s):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    closes_at_end = (i == len(s) - 1)
                    break
        if closes_at_end:
            s = s[1:-1].strip()
        else:
            break
    return s

def parse_conditions(clause_str: str, columns: List[str]) -> Optional[List[Dict[str, Any]]]:
    normalized = re.sub(r'\s+', ' ', clause_str.strip())
    # Remove outer parentheses that wrap the entire condition block.
    # e.g. "(@A >= 15 and @A <= 20)" → "@A >= 15 and @A <= 20"
    # This prevents the naive " and " split from producing unbalanced sub-expressions.
    normalized = _strip_outer_parens(normalized)
    parts = re.split(r'\s+and\s+', normalized, flags=re.IGNORECASE)
    result = []

    for part in parts:
        raw_expr = _strip_outer_parens(re.sub(r'\s+', ' ', part.strip()))
        referenced = []
        # Find @ColName
        for col in columns:
            if f"@{col}" in raw_expr:
                referenced.append(col)
        result.append({"raw": raw_expr, "referencedColumns": referenced})

    return result if result else None

def parse_command(input_str: str, columns: List[str]) -> Optional[Dict[str, Any]]:
    trimmed = input_str.strip()
    
    # Deduplicate
    if re.match(r'^(remove\s+duplicates|deduplicate)$', trimmed, re.I):
        return {"operation": "remove_duplicates"}
    
    # Delete rows
    delete_match = re.match(r'^delete\s+rows?\s+where\s+(.+)$', trimmed, re.I | re.S)
    if delete_match:
        conds = parse_conditions(delete_match.group(1), columns)
        if conds: return {"operation": "delete_rows", "conditions": conds}

    # Set with where
    set_where_match = re.match(r'^set\s+@?(.*?)\s+to\s+(.+?)\s+where\s+(.+)$', trimmed, re.I | re.S)
    if set_where_match:
        lookup = greedy_column_lookup(set_where_match.group(1), columns)
        if lookup:
            raw_val = set_where_match.group(2).strip().strip("'\"")
            is_expr = '@' in raw_val or any(op in raw_val for op in '+-*/')
            conds = parse_conditions(set_where_match.group(3), columns)
            if conds:
                return {
                    "operation": "update_cells",
                    "column": lookup["col"],
                    "valueExpr": raw_val if is_expr else None,
                    "value": None if is_expr else (float(raw_val) if raw_val.replace('.','',1).isdigit() else raw_val),
                    "conditions": conds
                }

    # Set all
    set_all_match = re.match(r'^set\s+@?(.*?)\s+to\s+(.+)$', trimmed, re.I | re.S)
    if set_all_match:
        lookup = greedy_column_lookup(set_all_match.group(1), columns)
        if lookup:
            raw_val = set_all_match.group(2).strip().strip("'\"")
            is_expr = '@' in raw_val or any(op in raw_val for op in '+-*/')
            return {
                "operation": "update_cells_all",
                "column": lookup["col"],
                "valueExpr": raw_val if is_expr else None,
                "value": None if is_expr else (float(raw_val) if raw_val.replace('.','',1).isdigit() else raw_val)
            }

    # Add column
    add_match = re.match(r'^add\s+column\s+(?:@|["\'])?(.*?)(?:["\'])?(?:\s+with\s+(?:value|default(?:value)?)(?:\s+(.+))?)?\s*$', trimmed, re.I)
    if add_match:
        col_name = add_match.group(1).strip()
        val = (add_match.group(2) or "").strip().strip("'\"")
        return {"operation": "add_column", "column": col_name, "value": val}

    # Rename column
    rename_match = re.match(r'^rename\s+(?:column\s+)?(?:@|["\'])?(.*?)(?:["\'])?\s+to\s+(?:@|["\'])?(.*?)(?:["\'])?\s*$', trimmed, re.I)
    if rename_match:
        lookup = greedy_column_lookup(rename_match.group(1), columns)
        if lookup:
            return {"operation": "rename_column", "column": lookup["col"], "newName": rename_match.group(2).strip()}

    # Highlight
    show_match = re.match(r'^(?:show|highlight)\s+where\s+(.+)$', trimmed, re.I | re.S)
    if show_match:
        conds = parse_conditions(show_match.group(1), columns)
        if conds: return {"operation": "highlight", "conditions": conds}

    # Style
    _STYLE_VALUE_TYPES = {
        "color":    "color",   # UI shows hex color picker
        "bgcolor":  "color",   # UI shows hex color picker
        "fontsize": "number",  # UI shows numeric input
        "align":    "select",  # UI shows left/center/right options
        # bold, italic, underline, strikethrough → no valueType (toggles, no value needed)
    }
    _STYLE_ALIASES = {
        "backgroundcolor": "bgcolor",
        "background-color": "bgcolor",
        "bg-color": "bgcolor",
        "font-size": "fontsize",
        "text-color": "color",
        "textcolor": "color"
    }
    style_match = re.match(r'^style\s+@?(.*?)\s+(bold|italic|underline|strikethrough|color|bgcolor|backgroundcolor|background-color|bg-color|text-color|textcolor|fontsize|font-size|align)(?:\s+([^\s]+))?(?:\s+where\s+(.+))?$', trimmed, re.I | re.S)
    if style_match:
        lookup = greedy_column_lookup(style_match.group(1), columns)
        if lookup:
            prop = style_match.group(2).lower()
            prop = _STYLE_ALIASES.get(prop, prop)
            # LLM-provided value is kept if present; UI replaces styleValue with the
            # user-selected value before sending to /pipeline/preview.
            val = style_match.group(3).strip() if style_match.group(3) else ""
            conds = parse_conditions(style_match.group(4), columns) if style_match.group(4) else None
            payload = {
                "operation": "style",
                "column": lookup["col"],
                "styleProp": prop,
                "styleValue": val,
                "conditions": conds,
            }
            value_type = _STYLE_VALUE_TYPES.get(prop)
            if value_type:
                payload["valueType"] = value_type
            return payload

    return None

def process_command(input_str: str, columns: List[str]) -> Optional[Dict[str, Any]]:
    parsed = parse_command(input_str, columns)
    if not parsed: return None
    return {
        "id": generate_id(),
        "type": parsed["operation"],
        "label": input_str.strip(),
        "payload": parsed
    }

def process_compute_command(input_str: str, data: List[Dict[str, Any]], columns: List[str], scope_ids: Optional[Set[int]] = None) -> Optional[Dict[str, Any]]:
    trimmed = input_str.strip()
    match = re.match(
        r'^(?:what\s+is\s+(?:the\s+)?)?(?:give\s+me\s+(?:the\s+)?)?(avg|average|mean|sum|min|max|median|count|std)\s*(?:\(\s*@?|\s+of\s+|\s+@?|\s*@)(.+?)\s*\)?\s*$', 
        trimmed, re.I | re.S
    )
    if not match: return None
    
    fn = match.group(1).lower()
    col_part = match.group(2).strip().replace("@", "")
    lookup = greedy_column_lookup(col_part, columns) or greedy_column_lookup(col_part.replace(" ", "_"), columns)
    if not lookup: return None
    
    col = lookup["col"]
    scoped_data = [r for r in data if r["ID"] in scope_ids] if scope_ids else data
    
    vals = []
    for r in scoped_data:
        try:
            val = r.get(col)
            if val is not None:
                vals.append(float(val))
        except (ValueError, TypeError):
            continue
            
    if not vals and fn != "count": return None
    
    result = compute_agg(fn, vals)
    
    fn_labels = {
        "avg": "Average", "average": "Average", "mean": "Average",
        "sum": "Sum", "min": "Min", "max": "Max", "median": "Median",
        "count": "Count", "std": "Std Dev"
    }
    label = f"{fn_labels.get(fn, fn)} of {col}"
    
    return {
        "label": label,
        "columnSafe": col,
        "expression": f"{fn}(@{col})",
        "value": round(result, 4) if isinstance(result, (int, float)) else result
    }
