from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import bcrypt
import os

from app.database import get_db_session
from app.models.user import User

router = APIRouter(tags=["Authentication"])

# Setup Jinja2 templates (relative to tax_ai_app/)
templates = Jinja2Templates(directory="templates")

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def seed_default_user_if_needed(db: Session):
    # Check if any user exists
    exists = db.query(User).first()
    if not exists:
        default_user = User(
            name="Demo Preparer",
            email="preparer@taxcheck.com",
            password_hash=hash_password("password123"),
            role="preparer"
        )
        db.add(default_user)
        db.commit()
        db.refresh(default_user)
        print("Seeded default user: preparer@taxcheck.com / password123")

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db_session)) -> User | None:
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    # For Phase 1 simple session, session_token holds user's email
    return db.query(User).filter(User.email == session_token).first()

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None, db: Session = Depends(get_db_session)):
    seed_default_user_if_needed(db)
    
    # If already logged in, redirect to dashboard
    current_user = get_current_user_from_cookie(request, db)
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        
    return templates.TemplateResponse(request=request, name="login.html", context={"error": error})

@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    seed_default_user_if_needed(db)
    
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        # Redirect back to login with error query param
        return RedirectResponse(
            url="/login?error=Invalid+email+or+password",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Successful login: set simple cookie-based session
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    # Set session cookie (HttpOnly for security)
    response.set_cookie(
        key="session_token",
        value=user.email,
        httponly=True,
        max_age=86400, # 1 day
        samesite="lax"
    )
    return response

@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response
