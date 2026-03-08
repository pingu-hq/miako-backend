from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.llm_workflow_router import router as llm_router


app = FastAPI()

# --- CORS Configuration ---
# U-um... This allows requests from any domain...
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --------------------------

app.include_router(llm_router)

# if __name__ == "__main__":
#     import uvicorn
#     print("RUNNING UVICORN")
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=False
#     )