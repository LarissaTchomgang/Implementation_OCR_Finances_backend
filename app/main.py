from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.extraction import router as extraction_router
from fastapi.staticfiles import StaticFiles


app = FastAPI()

# Middleware CORS (utile pour le frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/exports", StaticFiles(directory="exports"), name="exports")
# Inclusion des routes
app.include_router(extraction_router, prefix="/api")

