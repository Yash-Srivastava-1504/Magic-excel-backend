import ast
import re
import operator as op
from typing import Any, Dict, Callable

# Supported operators for safe evaluation
SAFE_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.BitXor: op.xor,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
    ast.Not: op.not_,
}

class SafeEvaluator:
    def __init__(self, variables: Dict[str, Any]):
        self.variables = variables

    def eval(self, expr: str) -> Any:
        try:
            # Strip any residual whitespace or newlines that could break ast.parse
            # Use replace to handle internal newlines from LLM formatting
            clean_expr = expr.replace('\n', ' ').strip()
            # Normalize operator syntax: LLM is prompted to use = for equality,
            # but ast.parse requires ==. Convert bare = to == while leaving
            # compound operators (==, !=, <=, >=) untouched.
            clean_expr = re.sub(r'(?<![!<>=])=(?!=)', '==', clean_expr)
            # SQL-style not-equal
            clean_expr = clean_expr.replace('<>', '!=')
            tree = ast.parse(clean_expr, mode='eval')
            return self._eval_node(tree.body)
        except Exception as e:
            raise ValueError(f"Safe evaluation failed for expression '{expr}': {str(e)}")

    def _eval_node(self, node):
        if isinstance(node, ast.Constant):  # < 3.8: ast.Num, ast.Str, ast.Bytes, ast.NameConstant
            return node.value
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            return SAFE_OPERATORS[type(node.op)](operand)
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for operation, right_node in zip(node.ops, node.comparators):
                right = self._eval_node(right_node)
                if not SAFE_OPERATORS[type(operation)](left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            values = [self._eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            elif isinstance(node.op, ast.Or):
                return any(values)
        elif isinstance(node, ast.Name):
            # Recognise SQL/Excel boolean and null constants (case-insensitive)
            upper = node.id.upper()
            if upper == 'TRUE':  return True
            if upper == 'FALSE': return False
            if upper in ('NULL', 'NONE'): return None
            if node.id in self.variables:
                val = self.variables[node.id]
                # Defensively try to cast numeric strings to float for comparison
                if isinstance(val, str) and val.replace('.', '', 1).isdigit():
                    try: return float(val)
                    except: pass
                return val
            return 0
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fn = node.func.id.upper()
                # IF(condition, true_val, false_val) — Excel/SQL-style conditional
                if fn == 'IF' and len(node.args) == 3:
                    cond = self._eval_node(node.args[0])
                    return self._eval_node(node.args[1]) if cond else self._eval_node(node.args[2])
                # Whitelisted math/type functions
                if node.func.id in ['abs', 'round', 'min', 'max', 'int', 'float', 'str']:
                    args = [self._eval_node(arg) for arg in node.args]
                    func = __builtins__.get(node.func.id)
                    if func:
                        return func(*args)
            raise ValueError(f"Unsupported function call: {ast.dump(node)}")
        else:
            raise ValueError(f"Unsupported AST node: {ast.dump(node)}")

def compile_conditions(conditions: List[Dict[str, Any]], columns: List[str]) -> Callable[[Dict[str, Any]], bool]:
    def evaluator(row: Dict[str, Any]) -> bool:
        eval_obj = SafeEvaluator(row)
        import re
        def norm(s): return re.sub(r'\s+', ' ', s).strip()
        
        # Sort columns by length descending to avoid partial matches
        sorted_cols = sorted(columns, key=len, reverse=True)
        
        for cond in conditions:
            # Normalize whitespace in the expression (collapse newlines/multiple spaces)
            clean_expr = norm(cond.get("raw", ""))
            if not clean_expr: continue
            
            for col in sorted_cols:
                n_col = norm(col)
                safe_col = re.sub(r'[^a-zA-Z0-9]', '_', n_col)
                row[safe_col] = row.get(col, 0)

                # Replace @-prefixed version (normalized)
                clean_expr = clean_expr.replace(f"@{n_col}", safe_col)
                # Replace standing alone version (word boundaries, normalized)
                clean_expr = re.sub(rf'\b{re.escape(n_col)}\b', safe_col, clean_expr)

            if not eval_obj.eval(clean_expr):
                return False
        return True
    return evaluator

def compile_value_expr(expr: str, columns: List[str]) -> Callable[[Dict[str, Any]], Any]:
    def evaluator(row: Dict[str, Any]) -> Any:
        eval_obj = SafeEvaluator(row)
        import re
        def norm(s): return re.sub(r'\s+', ' ', s).strip()
        
        sorted_cols = sorted(columns, key=len, reverse=True)
        clean_expr = norm(expr)
        
        for col in sorted_cols:
            n_col = norm(col)
            safe_col = re.sub(r'[^a-zA-Z0-9]', '_', n_col)
            row[safe_col] = row.get(col, 0)

            clean_expr = clean_expr.replace(f"@{n_col}", safe_col)
            clean_expr = re.sub(rf'\b{re.escape(n_col)}\b', safe_col, clean_expr)
            
        return eval_obj.eval(clean_expr)
    return evaluator
