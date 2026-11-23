from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db


app = FastAPI(
    title="PACTELLE API",
    description="Intelligent Contract and Policy Intelligence Platform",
    version="0.1.0"
)


@app.get("/")
async def root():

    return {
        "message": "Welcome to PACTELLE",
        "status": "running"
    }


@app.get("/api/v1/health")
async def health_check():

    return {
        "status": "healthy",
        "application": "PACTELLE",
        "version": "0.1.0"
    }


@app.get("/api/v1/health/db")
def database_health(db: Session = Depends(get_db)):

    try:

        db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "PostgreSQL",
            "connected": True
        }

    except Exception as exc:

        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        ) from exc