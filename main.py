from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from routers.llm_workflow_router import router as chatbot_router_v1
# from routers.router_v2 import router as chatbot_router_v2
from core.config import settings
from miako_workflow.miako_router import router as miako_router_v1
from core.app_logger import logger


app = FastAPI(
    docs_url="/api-docs",
    redoc_url="/api-redoc",
    openapi_url="/api-openapi.json",
    title="Miako Hackathon Project",
)


# domain = [settings.DOMAIN]
origins = settings.ORIGINS.get_secret_value()
allow_origins = [
    origin.strip()
    for origin in origins.split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# app.include_router(chatbot_router_v1)
# app.include_router(chatbot_router_v2)
app.include_router(miako_router_v1)


@app.get("/health-check")
def health_check():
    logger.info("Health check endpoint accessed")
    return {"status": "ok"}

# if __name__ == "__main__":
#     import uvicorn
#     print("RUNNING UVICORN")
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=False
#     )