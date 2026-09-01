from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routers import auth as auth_router
from app.routers import chat as chat_router
from app.routers import documents as documents_router
from app.routers import domains as domains_router
from app.routers import memories as memories_router
from app.routers import models as models_router
from app.routers import optimizer as optimizer_router
from app.routers import openai_compat as openai_compat_router
from app.routers import remote_access as remote_access_router
from app.routers import repositories as repositories_router
from app.optimizer.jobs import recover_interrupted_runs


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recover_interrupted_runs()
    yield


app = FastAPI(title="LLM Framework API", lifespan=lifespan)


def _openai_error(message: str, error_type: str = "invalid_request_error") -> dict:
    return {"error": {"message": message, "type": error_type, "param": None, "code": None}}


@app.exception_handler(StarletteHTTPException)
async def framework_http_exception(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/v1/"):
        error_type = "authentication_error" if exc.status_code == 401 else "rate_limit_error" if exc.status_code == 429 else "invalid_request_error" if exc.status_code < 500 else "server_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_openai_error(str(exc.detail), error_type),
            headers=exc.headers,
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def framework_validation_exception(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=422,
            content=_openai_error("The request body is invalid", "invalid_request_error"),
        )
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def limit_remote_request_body(request: Request, call_next):
    if request.url.path == "/v1/chat/completions":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > settings.remote_api_max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content=_openai_error("The request body is too large", "invalid_request_error"),
                )
    return await call_next(request)

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
app.include_router(remote_access_router.router)
app.include_router(openai_compat_router.router)
