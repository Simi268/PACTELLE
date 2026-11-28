from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

from app.api.v1.documents import router as documents_router
from app.api.v1.extractions import router as extraction_router
from app.api.v1.clauses import router as clauses_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.contracts import router as contracts_router
from app.api.v1.document_processing import router as document_processing_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.portfolio_intelligence import router as portfolio_intelligence_router
from app.api.v1.portfolio_actions import router as portfolio_actions_router
from app.api.v1.portfolio_obligations import router as portfolio_obligations_router
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(
    title="PACTELLE API",
    description="Intelligent Contract and Policy Intelligence Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router, prefix="/api/v1")
app.include_router(extraction_router, prefix="/api/v1")
app.include_router(clauses_router, prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(document_processing_router, prefix="/api/v1")
app.include_router(intelligence_router, prefix="/api/v1")
app.include_router(portfolio_intelligence_router, prefix="/api/v1")
app.include_router(portfolio_actions_router, prefix="/api/v1")
app.include_router(portfolio_obligations_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Welcome to PACTELLE", "status": "running"}


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "application": "PACTELLE", "version": "0.1.0"}


@app.get("/api/v1/health/db")
def database_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "PostgreSQL", "connected": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database connection failed") from exc
