from fastapi import FastAPI

from twstock_api.routers import health, stocks, prices, indices, etl, chips


def create_app() -> FastAPI:
    """建立 FastAPI app 並掛上 routers."""
    app = FastAPI(title="TwStock API", version="0.1.0")
    app.include_router(stocks.router)
    app.include_router(prices.router)
    app.include_router(chips.router)
    app.include_router(indices.router)
    app.include_router(etl.router)
    app.include_router(health.router)
    return app


app = create_app()
