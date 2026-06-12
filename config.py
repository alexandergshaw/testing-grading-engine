"""Environment-driven configuration, shared by the web shell and the API."""
import os

ON_VERCEL = os.environ.get("VERCEL") == "1"

# Never execute student code on shared serverless infrastructure - the env
# flag only takes effect for local runs.
ALLOW_CODE_EXECUTION = (not ON_VERCEL) and os.environ.get("GRADING_ALLOW_EXEC") == "1"

# Vercel serverless rejects request bodies over ~4.5 MB.
MAX_UPLOAD_MB = 4 if ON_VERCEL else 50

# When set, API requests (except /health) must send X-API-Key with this value.
API_KEY = os.environ.get("GRADING_API_KEY", "")

# Comma-separated origins allowed to call the API cross-origin ("*" for any).
CORS_ORIGINS = [o.strip() for o in os.environ.get("GRADING_CORS_ORIGINS", "").split(",") if o.strip()]
