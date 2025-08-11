from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import extraction  # <-- importe tes routes

app = FastAPI()

# --- Configuration CORS ---
origins = [
    "http://localhost:3000",  # pour les tests en local
    "https://implementation-ocr-finances-frontend-1h038er53.vercel.app",  # ton site Vercel
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # uniquement ces domaines
    allow_credentials=True,
    allow_methods=["*"],          # autorise toutes les méthodes (POST, GET, etc.)
    allow_headers=["*"],          # autorise tous les headers
)

# --- Inclusion des routes ---
app.include_router(extraction.router, prefix="/api")
