from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import admin, auth, crud, home, scraper, storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
)

# Include routers
app.include_router(home.router)
app.include_router(admin.router)
app.include_router(scraper.router)
app.include_router(crud.router)
app.include_router(auth.router)
app.include_router(storage.router)

origins = [
    "http://localhost:5173",
    "http://localhost:5174",
]
# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
