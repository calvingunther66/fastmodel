"""Run the server: python -m server  (honours HOST/PORT env vars)."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server.app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("RELOAD")),
    )
