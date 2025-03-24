import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import home

# Create FastAPI app
app = FastAPI(
    title="Batelec API",
    description="API for Batelec power interruption data",
    version="1.0.0",
)

# Include routers
app.include_router(home.router)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
