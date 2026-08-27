from fastapi import APIRouter, HTTPException
from typing import List
from app.models.schemas import PipelineOperation
from app.models.database import get_supabase
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
        sb = get_supabase()
        res = sb.table("stacks").select("id, user_id, name, ops, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        results = []
        for row in res.data:
            row["id"] = str(row["id"])
            row["user_id"] = str(row["user_id"])
            row["created_at"] = str(row["created_at"])
            results.append(_parse_ops(row))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=SavedStackResponse)
async def create_stack(user_id: str, stack: SavedStackBase):
    try:
        ops_data = [op.dict() for op in stack.ops]

        sb = get_supabase()
        res = sb.table("stacks").insert({
            "user_id": user_id,
            "name": stack.name,
            "ops": ops_data
        }).execute()
        
        if not res.data:
            raise HTTPException(status_code=400, detail="Failed to save stack")
            
        new_stack = res.data[0]
        new_stack["id"] = str(new_stack["id"])
        new_stack["user_id"] = str(new_stack["user_id"])
        new_stack["created_at"] = str(new_stack["created_at"])
        
        return _parse_ops(new_stack)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{stack_id}", response_model=SavedStackResponse)
async def update_stack(stack_id: str, stack: SavedStackBase):
    try:
        ops_data = [op.dict() for op in stack.ops]
        
        sb = get_supabase()
        res = sb.table("stacks").update({
            "name": stack.name,
            "ops": ops_data
        }).eq("id", stack_id).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="Stack not found")
            
        updated_stack = res.data[0]
        updated_stack["id"] = str(updated_stack["id"])
        updated_stack["user_id"] = str(updated_stack["user_id"])
        updated_stack["created_at"] = str(updated_stack["created_at"])
        
        return _parse_ops(updated_stack)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{stack_id}")
async def delete_stack(stack_id: str):
    try:
        sb = get_supabase()
        sb.table("stacks").delete().eq("id", stack_id).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
