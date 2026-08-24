import statistics
from typing import List, Union

def compute_agg(fn: str, vals: List[float]) -> Union[float, int]:
    if not vals:
        return 0 if fn == "count" else 0.0
    
    fn = fn.lower()
    try:
        if fn in ["avg", "average", "mean"]:
            return sum(vals) / len(vals)
        elif fn == "sum":
            return sum(vals)
        elif fn == "min":
            return min(vals)
        elif fn == "max":
            return max(vals)
        elif fn == "median":
            return statistics.median(vals)
        elif fn == "count":
            return len(vals)
        elif fn == "std":
            return statistics.stdev(vals) if len(vals) > 1 else 0.0
        else:
            return 0.0
    except Exception:
        return 0.0
