from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.routes import auth, dashboard, jobs, checklist, email

app = FastAPI(
    title="TaxCheck Platform",
    description="Tax Document Anomaly Detection Platform - NexxelDigital",
    version="1.0.0"
)

# Mount static directory for local CSS/JS assets if needed
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(checklist.router)
app.include_router(email.router)

@app.get("/")
def read_root():
    # Redirect root visitors to dashboard (which handles login verification)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
