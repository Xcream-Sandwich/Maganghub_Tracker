from mangum import Mangum
from backend.main import app as fastapi_app

# Vercel passes a request object; Mangum adapts FastAPI to a Lambda handler
handler = Mangum(fastapi_app)
