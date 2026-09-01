from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth as auth_router
from app.routers import chat as chat_router
from app.routers import documents as documents_router
from app.routers import domains as domains_router
from app.routers import memories as memories_router
from app.routers import models as models_router
from app.routers import optimizer as optimizer_router
from app.routers import repositories as repositories_router
from app.optimizer.jobs import recover_interrupted_runs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recover_interrupted_runs()
    yield


app = FastAPI(title="LLM Framework API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(domains_router.router)
app.include_router(models_router.router)
app.include_router(optimizer_router.router)
app.include_router(documents_router.router)
app.include_router(memories_router.router)
app.include_router(repositories_router.router)
app.include_router(chat_router.router)
