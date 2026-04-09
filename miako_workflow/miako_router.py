from typing import Any
from sqlmodel import select
from models.user_model import User
from core.security import (
    get_hash_password,
    verify_hash_password,
    get_current_user_id,
    login_response_tokens,
    get_access_token_by_refresh_token
)
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from databases.database import get_session
from pydantic import BaseModel, Field
from miako_workflow.workflows.flows import AdaptiveChatbot
from miako_workflow.workflows.base import ChatbotExecutor
from miako_workflow.config_files.config import workflow_settings
from core.app_logger import logger


class UserBase(BaseModel):
    password: str = Field(..., description="User password")

class UserCreate(UserBase):
    username: str
    email: str

class UserLogin(UserBase):
    email: str

class RefreshTokenRequest(BaseModel):
   refresh_token: str

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")

router = APIRouter(
    prefix="/v2",
    tags=["chatbot"]
)

class MessageRequest(BaseModel):
    message: str = Field(default="", description="User message")



@router.post("/send-message")
async def send_message(request: MessageRequest, user_id = Depends(get_current_user_id)):
    try:
        chat_obj = AdaptiveChatbot(
            user_id=user_id,
            input_message=request.message
        )
        resp_obj = ChatbotExecutor(chat=chat_obj)
        response = await resp_obj.execute()
        logger.success(f"Send message successful for user: {user_id}")
        return MessageRequest(message=str(response))
    except HTTPException as err1:
        logger.error(f"Send message failed for user: {user_id}. Error message: {err1.detail}")
        raise
    except Exception as err2:
        logger.critical(f"Send message failed for user: {user_id}. Error message: {err2}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")



@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def sign_up_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    try:
        hashed_password = await get_hash_password(payload.password)

        db_user = User(
            email=payload.email,
            user_name=payload.username,
            hashed_password=hashed_password
        )
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        logger.success(f"Sign up successful. Email: {db_user.email}")
        return {"status": status.HTTP_201_CREATED}
    except Exception as err:
        logger.error(f"Sign up failed for user: {payload.email}. Error message: {err}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@router.post("/login", status_code=status.HTTP_200_OK)
async def login_user(payload: UserLogin, session: AsyncSession = Depends(get_session)):
    if not payload.email or not payload.password:
        logger.error("Email and password is required")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad Request")

    statement = select(User).where(User.email == payload.email)
    result = await session.execute(statement=statement)
    user = result.scalar_one_or_none()

    error_401 = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized User")

    if not user:
        logger.error("Invalid email or password")
        raise error_401

    is_valid = await verify_hash_password(user.hashed_password, payload.password)
    if not is_valid:
        logger.error("Invalid password")
        raise error_401

    logger.success(f"Login successful. Email: {payload.email}")
    return login_response_tokens(subject=user.uuid)

@router.post("/refresh", response_model=RefreshTokenResponse)
def me_test(payload: RefreshTokenRequest):
    try:
        new_access_token = get_access_token_by_refresh_token(
            refresh_token=payload.refresh_token
        )
        return RefreshTokenResponse(
            access_token=new_access_token,
            token_type="bearer"
        )
    except HTTPException as err1:
        logger.success(f"Refresh token failed. Error message: {err1.detail}")
        raise
    except Exception as err2:
        logger.critical(f"Refresh token failed. Error message: {err2}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")


@router.get("/hello", status_code=status.HTTP_202_ACCEPTED)
def hello_world():
    _hello = workflow_settings.HELLO_WORLD.upper()
    if _hello:
        logger.success(f"Hello world successful. Message: {_hello}")
        return {"MESSAGE": _hello}
    logger.warning(f"Hello world failed. Message: {_hello}")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)