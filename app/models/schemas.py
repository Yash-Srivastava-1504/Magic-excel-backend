from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Set, Literal
from enum import Enum

# --- Cell Styles ---

class CellFont(BaseModel):
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    strikethrough: Optional[bool] = None
    size: Optional[float] = None
    color: Optional[str] = None  # hex WITHOUT #
    name: Optional[str] = None

class CellFill(BaseModel):
    bgColor: Optional[str] = None  # hex WITHOUT #

class CellAlignment(BaseModel):
    horizontal: Optional[str] = None  # "left", "center", "right"
    vertical: Optional[str] = None    # "top", "middle", "bottom"
    wrapText: Optional[bool] = None

class CellBorder(BaseModel):
    color: Optional[str] = None
    style: Optional[str] = None  # "thin", "medium", "thick", "dashed", "dotted"

class CellBorders(BaseModel):
    top: Optional[CellBorder] = None
    bottom: Optional[CellBorder] = None
    left: Optional[CellBorder] = None
    right: Optional[CellBorder] = None

class CellStyle(BaseModel):
    font: Optional[CellFont] = None
    fill: Optional[CellFill] = None
    alignment: Optional[CellAlignment] = None
    borders: Optional[CellBorders] = None
    numberFormat: Optional[str] = None

# --- Pipeline & Operations ---

class OperationType(str, Enum):
    delete_rows = "delete_rows"
    update_cells = "update_cells"
    update_cells_all = "update_cells_all"
    add_column = "add_column"
    rename_column = "rename_column"
    delete_column = "delete_column"
    highlight = "highlight"
    style = "style"
    remove_duplicates = "remove_duplicates"
    compute = "compute"

class PipelineOperation(BaseModel):
    id: str
    type: OperationType
    label: str
    payload: Dict[str, Any]

class PipelineStep(BaseModel):
    operation: PipelineOperation
    affectedRowIds: List[int]
    summary: str
    status: str  # "success" or "error"
    errorMessage: Optional[str] = None

class ComputeResult(BaseModel):
    label: str
    expression: str
    value: Any
    columnSafe: Optional[str] = None

class PipelineExecutionRequest(BaseModel):
    data: List[Dict[str, Any]]
    columns: List[str]
    cellStyles: Dict[str, CellStyle]  # "rowIndex:colName" -> CellStyle
    pipeline: List[PipelineOperation]
    activeScopeIds: Optional[List[int]] = None

class PipelineExecutionResult(BaseModel):
    transformedData: List[Dict[str, Any]]
    columns: List[str]
    cellStyles: Dict[str, CellStyle]
    steps: List[PipelineStep]
    highlightedRowIds: List[int]
    activeScopeIds: Optional[List[int]] = None
    deletedRowIds: List[int]

# --- LLM Agent Response Models ---

class DetectComputeItem(BaseModel):
    replaceInQuery: Optional[str] = None
    computeExpression: str

class DetectComputeAgentResponse(BaseModel):
    mode: Literal["compute_only", "pipeline"] = "pipeline"
    items: List[DetectComputeItem] = []

class AgentCommandsResponse(BaseModel):
    commands: List[str] = []

# --- LLM Commands ---

class CommandRequest(BaseModel):
    input: str
    columns: List[str]
    previewData: List[Dict[str, Any]]
    scopeIds: Optional[List[int]] = None
    editingOp: Optional["PipelineOperation"] = None  # present when editing an existing stack op
    editMode: Optional[str] = "edit"  # "edit" or "replace"

class CommandResponse(BaseModel):
    exitEarly: bool
    computeResults: List[ComputeResult] = []
    operations: List[PipelineOperation] = []
    plainRewritten: Optional[str] = None
    plannerInput: Optional[str] = None

# --- Auth ---

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: Optional[str] = None

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    id: Optional[str] = None
    username: str
    full_name: Optional[str] = None

class UserInDB(User):
    hashed_password: str

# --- Files ---

class SheetInfo(BaseModel):
    data: List[Dict[str, Any]]
    titleRows: List[Dict[str, Any]]
    columns: List[str]
    styles: Dict[str, CellStyle]
    headerOffset: int
    sheetName: str

class UploadResponse(BaseModel):
    sourceFileId: str
    fileName: str
    sheets: List[SheetInfo]

# --- Specialty Endpoints ---

class FinalizeColumnRequest(BaseModel):
    name: str
    defaultValue: Any
    initialOps: List[PipelineOperation]
    data: List[Dict[str, Any]]
    columns: List[str]
    cellStyles: Dict[str, CellStyle]
