from fastapi import FastAPI

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