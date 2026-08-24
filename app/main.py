from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import files, pipeline, llm, auth, stacks

app = FastAPI(title=settings.APP_NAME)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["pipeline"])
app.include_router(llm.router, prefix="/api/v1/llm", tags=["llm"])
app.include_router(stacks.router, prefix="/api/v1/stacks", tags=["stacks"])

@app.get("/")
async def root():
    return {"message": "Welcome to DataSage API", "status": "running"}
