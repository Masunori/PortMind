from fastapi import FastAPI

app = FastAPI(title="PSA ESG API")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
