from contextlib import asynccontextmanager

from fastapi import FastAPI

from db.connect import create_pool
from db.schema import ensure_schema
from routes.agent_applications import router as agent_applications_router
from routes.interview import router as interview_router
from routes.recommendations import router as recommendations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = create_pool()
    try:
        pool.open()
        pool.wait()

        with pool.connection() as conn:
            ensure_schema(conn)

        app.state.pool = pool
        yield
    finally:
        pool.close()


app = FastAPI(lifespan=lifespan)
app.include_router(recommendations_router)
app.include_router(interview_router)
app.include_router(agent_applications_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
