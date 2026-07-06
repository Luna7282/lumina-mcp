from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown


app = FastAPI(title="Lumina API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lumina"}


# Stub endpoints — implement after scaffold
@app.post("/api/analyze")
async def analyze_codebase():
    """Accept files, build graph, store in DB, return codebase_id."""
    return {"status": "not_implemented"}


@app.post("/api/explain")
async def explain_codebase():
    """Generate video explanation for a codebase."""
    return {"status": "not_implemented"}


@app.post("/api/docs")
async def generate_docs():
    """Generate markdown documentation for a codebase."""
    return {"status": "not_implemented"}


@app.get("/api/codebase/{codebase_id}")
async def get_codebase():
    """Get codebase graph and metadata."""
    return {"status": "not_implemented"}
