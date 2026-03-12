import os
import sys

# back/ 와 프로젝트 루트 모두 sys.path에 추가
_back = os.path.dirname(os.path.abspath(__file__))      # .../back/
_root = os.path.dirname(_back)                           # .../Steam_Game_Recommend_Agent/

for _p in (_back, _root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.router import api_router

app = FastAPI(title="Steam Game Recommend Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "Welcome to Steam Game Recommend Backend"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[_back])
