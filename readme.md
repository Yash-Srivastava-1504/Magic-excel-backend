# DataSage Backend

FastAPI backend for the DataSage spreadsheet automation platform.

## Setup Instructions

### 1. Virtual Environment
The project uses a Python virtual environment. It has already been initialized in the `.venv` folder.

To activate it:
- **Windows**: `.\.venv\Scripts\activate`
- **macOS/Linux**: `source .venv/bin/activate`

### 2. Environment Variables
Create a `.env` file in the root directory (`data-sage-backend/`) with the following required variables:

```env
# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Security
SECRET_KEY=your_random_secret_key_for_jwt
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# LLM Configuration (Optional)
HF_TOKEN=your_huggingface_token
OPENAI_API_KEY=your_openai_api_key
