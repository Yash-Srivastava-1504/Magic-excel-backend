import re
from typing import List, Dict, Any

class ColMap:
    def __init__(self, columns: List[str]):
        self.original_cols = columns
        # Map original -> safe (e.g., "Profit (%)" -> "Profit_perc")
        self.to_safe = {}
        # Map safe -> original
        self.to_orig = {}
        
        for i, col in enumerate(columns):
            # Create a safe identifier for expressions
            # Replace non-alphanumeric with undercores
            safe = re.sub(r'[^a-zA-Z0-9]', '_', col)
            # Ensure unique
            if safe in self.to_orig:
                safe = f"{safe}_{i}"
            
            self.to_safe[col] = safe
            self.to_orig[safe] = col

    def safe_columns(self) -> List[str]:
        return list(self.to_orig.keys())

    def to_safe_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        new_row = {"ID": row.get("ID")}
        for col, val in row.items():
            if col in self.to_safe:
                new_row[self.to_safe[col]] = val
        return new_row

    def to_original_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        new_row = {"ID": row.get("ID")}
        for col, val in row.items():
            if col in self.to_orig:
                new_row[self.to_orig[col]] = val
        return new_row

    def sanitize_command(self, cmd: str) -> str:
        # Sort by length descending to avoid partial matches
        sorted_cols = sorted(self.original_cols, key=len, reverse=True)
        sanitized = cmd
        for col in sorted_cols:
            # Match @ColumnName or ["ColumnName"]
            pattern = re.compile(rf'@(?:{re.escape(col)})|\["{re.escape(col)}"\]')
            sanitized = pattern.sub(f"@{self.to_safe[col]}", sanitized)
        return sanitized

    def restore_command(self, cmd: str) -> str:
        restored = cmd
        # Priority on longest safe names
        sorted_safe = sorted(self.to_orig.keys(), key=len, reverse=True)
        for safe in sorted_safe:
            restored = restored.replace(f"@{safe}", f"@{self.to_orig[safe]}")
        return restored

    def restore_operation(self, op: Dict[str, Any]) -> Dict[str, Any]:
        # Recursively restore column names in payload strings
        new_op = op.copy()
        new_op["label"] = self.restore_command(op.get("label", ""))
        
        payload = op.get("payload", {})
        new_payload = payload.copy()
        
        if "column" in new_payload:
            new_payload["column"] = self.to_orig.get(new_payload["column"], new_payload["column"])
        if "target" in new_payload:
            new_payload["target"] = self.to_orig.get(new_payload["target"], new_payload["target"])
        if "from" in new_payload:
            new_payload["from"] = self.to_orig.get(new_payload["from"], new_payload["from"])
        if "to" in new_payload:
            new_payload["to"] = self.to_orig.get(new_payload["to"], new_payload["to"])
        if "valueExpr" in new_payload and new_payload["valueExpr"]:
            new_payload["valueExpr"] = self.restore_command(new_payload["valueExpr"])
            
        if "conditions" in new_payload:
            new_conds = []
            for cond in new_payload["conditions"]:
                new_cond = cond.copy()
                new_cond["raw"] = self.restore_command(cond.get("raw", ""))
                if "referencedColumns" in new_cond:
                    new_cond["referencedColumns"] = [self.to_orig.get(c, c) for c in new_cond["referencedColumns"]]
                new_conds.append(new_cond)
            new_payload["conditions"] = new_conds
            
        new_op["payload"] = new_payload
        return new_op
