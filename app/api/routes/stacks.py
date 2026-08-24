from fastapi import APIRouter, HTTPException
from typing import List
from app.models.schemas import PipelineOperation
from app.models.database import get_db
from pydantic import BaseModel
import json

router = APIRouter()

class SavedStackBase(BaseModel):
    name: str
    ops: List[PipelineOperation]

class SavedStackResponse(SavedStackBase):
    id: str
    user_id: str
    created_at: str

def _parse_ops(row: dict) -> dict:
    if isinstance(row.get("ops"), str):
        row["ops"] = json.loads(row["ops"])
    return row

@router.get("/", response_model=List[SavedStackResponse])
async def list_stacks(user_id: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id::text, user_id::text, name, ops, created_at::text FROM stacks WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,)
                )
                return [_parse_ops(row) for row in cur.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=SavedStackResponse)
async def create_stack(user_id: str, stack: SavedStackBase):
    try:
        ops_json = json.dumps([op.dict() for op in stack.ops])

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stacks (user_id, name, ops)
                    VALUES (%s, %s, %s)
                    RETURNING id::text, user_id::text, name, ops, created_at::text
                    """,
                    (user_id, stack.name, ops_json)
                )
                new_stack = cur.fetchone()
                if not new_stack:
                    raise HTTPException(status_code=400, detail="Failed to save stack")
                return _parse_ops(new_stack)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{stack_id}", response_model=SavedStackResponse)
async def update_stack(stack_id: str, stack: SavedStackBase):
    try:
        ops_json = json.dumps([op.dict() for op in stack.ops])

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE stacks SET name = %s, ops = %s
                    WHERE id = %s
                    RETURNING id::text, user_id::text, name, ops, created_at::text
                    """,
                    (stack.name, ops_json, stack_id)
                )
                updated_stack = cur.fetchone()
                if not updated_stack:
                    raise HTTPException(status_code=404, detail="Stack not found")
                return _parse_ops(updated_stack)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{stack_id}")
async def delete_stack(stack_id: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM stacks WHERE id = %s", (stack_id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
