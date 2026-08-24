from fastapi import APIRouter, HTTPException
from app.models.schemas import PipelineExecutionRequest, PipelineExecutionResult, FinalizeColumnRequest
from app.services.pipeline_engine import execute_pipeline
from app.services.excel_parser import _sanitize_col
import json
import re

router = APIRouter()

@router.post("/preview", response_model=PipelineExecutionResult)
async def preview_pipeline(request: PipelineExecutionRequest):
    try:
        result = execute_pipeline(
            raw_data=request.data,
            base_columns=request.columns,
            base_styles=request.cellStyles,
            pipeline=request.pipeline
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@router.post("/execute", response_model=PipelineExecutionResult)
async def execute_pipeline_route(request: PipelineExecutionRequest):
    # For now, execute and preview are identical as the frontend handles the commit.
    # In a full-blown backend, execute might save to a DB.
    return await preview_pipeline(request)

@router.post("/finalize-new-column", response_model=PipelineExecutionResult)
async def finalize_new_column(request: FinalizeColumnRequest):
    try:
        # 1. Identify the placeholder column name used by the LLM
        # We assume the first 'add_column' operation contains it.
        add_op = next((op for op in request.initialOps if op.type == "add_column"), None)
        if not add_op:
            raise HTTPException(status_code=400, detail="No add_column operation found in initialOps")
        
        placeholder_name = add_op.payload.get("column")
        if not placeholder_name:
             raise HTTPException(status_code=400, detail="add_column operation has no column name")

        # 2. Sanitize the user-provided name
        # To avoid collisions with existing columns, we need a 'seen' map.
        seen = {c: c for c in request.columns}
        sanitized_name = _sanitize_col(request.name, seen)

        # 3. Patch the operations
        # We'll do a string-based replacement for simplicity and speed, 
        # targeting the literal placeholder name and its @ reference.
        ops_json = json.dumps([op.dict() for op in request.initialOps])
        
        # Replace "@placeholder" with "@sanitized" in expressions
        # Also replace "column": "placeholder" or "target": "placeholder"
        patched_json = ops_json.replace(f'@{placeholder_name}', f'@{sanitized_name}')
        patched_json = patched_json.replace(f'"{placeholder_name}"', f'"{sanitized_name}"')
        
        patched_ops_list = json.loads(patched_json)
        
        # 4. Inject the default value into the add_column op
        for op_dict in patched_ops_list:
            if op_dict["type"] == "add_column":
                op_dict["payload"]["value"] = request.defaultValue
                op_dict["payload"]["originalName"] = request.name # Store for mapping

        # 5. Execute
        from app.models.schemas import PipelineOperation
        final_ops = [PipelineOperation(**o) for o in patched_ops_list]
        
        result = execute_pipeline(
            raw_data=request.data,
            base_columns=request.columns,
            base_styles=request.cellStyles,
            pipeline=final_ops
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Finalization failed: {str(e)}")
