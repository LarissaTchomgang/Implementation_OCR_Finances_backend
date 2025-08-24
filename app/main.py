import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import extraction  # <-- tes routes

app = FastAPI()

# --- Configuration CORS ---
origins = [
    "http://localhost:3000",  # tests en local
    "https://implementation-ocr-finances-fronten.vercel.app",  # site Vercel
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Inclusion des routes ---
app.include_router(extraction.router, prefix="/api")


# --- Point d’entrée ---
if __name__ == "__main__":
    import uvicorn

    # Render injecte PORT=10000 → on le lit
    #port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=1000, reload=False)
