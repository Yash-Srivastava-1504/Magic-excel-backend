import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.excel_parser import parse_excel
from app.models.schemas import UploadResponse, SheetInfo
import time
import uuid
from app.utils.llm_client import LOG_FILE

router = APIRouter()

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Invalid file type. Only Excel and CSV are supported.")
    
    if os.path.exists(LOG_FILE):
        try:
            os.remove(LOG_FILE)
        except Exception:
            pass

    try:
        content = await file.read()
        sheets = parse_excel(content)
        
        source_file_id = f"src_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        
        return UploadResponse(
            sourceFileId=source_file_id,
            fileName=file.filename,
            sheets=sheets
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")
