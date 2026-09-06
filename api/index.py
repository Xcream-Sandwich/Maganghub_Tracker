from mangum import Mangum
from backend.main import app as fastapi_app

# Expose the FastAPI ASGI app for Vercel (preferred)
app = fastapi_app
# Keep the Mangum wrapper as a fallback (e.g., for Netlify)
handler = Mangum(app)
