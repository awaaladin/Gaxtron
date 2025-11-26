from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from app.api.routes import wallet, auth

app = FastAPI()

# Serve static files (HTML, CSS, JS)
static_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(static_dir, '..')

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include wallet and auth API
app.include_router(wallet.router)
app.include_router(auth.router)

@app.get("/")
def read_index():
    return FileResponse(os.path.join(static_dir, "frontend.html"))
