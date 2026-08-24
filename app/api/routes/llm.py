from fastapi import APIRouter, HTTPException
from app.models.schemas import CommandRequest, CommandResponse
from app.services.llm_service import run_detect_compute_stage, generate_pipeline_operations
import os
from app.utils.llm_client import LOG_FILE, _log_llm_interaction

router = APIRouter()

@router.post("/command", response_model=CommandResponse)
async def process_llm_command(request: CommandRequest):
    try:
        if os.path.exists(LOG_FILE):
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass

        is_edit = request.editingOp is not None
        scope_ids = set(request.scopeIds) if request.scopeIds else None

        # Stage 1: Detect compute-only or pre-evaluated aggregates
        detect_res = await run_detect_compute_stage(
            input_str=request.input,
            columns=request.columns,
            preview_data=request.previewData,
            scope_ids=scope_ids
        )

        # In edit mode, never exit early — the resolved compute value must flow
        # into Stage 2 as context for the op mutation, not be returned to the user.
        if detect_res.get("exitEarly") and not is_edit:
            return CommandResponse(
                exitEarly=True,
                computeResults=detect_res["computeResults"]
            )

        # Stage 2: Decomposition and Compilation
        # When editing, pass the existing op so the LLM modifies it surgically.
        ops = await generate_pipeline_operations(
            input_str=detect_res["plannerInput"],
            columns=request.columns,
            preview_data=request.previewData,
            scope_ids=scope_ids,
            editing_op=request.editingOp if is_edit else None,
            edit_mode=request.editMode,
        )

        response_payload = CommandResponse(
            exitEarly=False,
            computeResults=detect_res.get("computeResults", []),
            operations=ops,
            plainRewritten=detect_res.get("plainRewritten"),
            plannerInput=detect_res.get("plannerInput")
        )

        # Log the whole flow pipeline operations
        try:
            ops_dict = [op.model_dump() for op in ops] if ops else []
            _log_llm_interaction(
                input_data=request.input,
                response_content=ops_dict,
                agent_name="Pipeline Flow (edit)" if is_edit else "Pipeline Flow"
            )
        except Exception as log_e:
            print(f"Error logging pipeline flow: {log_e}")

        return response_payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM command processing failed: {str(e)}")
