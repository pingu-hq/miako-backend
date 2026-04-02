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
from llm_workflow.workflows.base import ChatbotExecutor
from llm_workflow.workflows.flows import AdaptiveChatbot
from pydantic import BaseModel, Field
from main import logger


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
            input_message=request.message,
        )
        chatbot = ChatbotExecutor(chat_obj)
        response = await chatbot.execute()
        logger.info(f"User is {user_id}. Chat completion is successful. Message is: {response[20:]}....")
        return MessageRequest(message=str(response))
    except HTTPException as err1:
        logger.debug(f"Error occurred. User is {user_id}. Error message is: {err1.detail}")
        raise HTTPException(status_code=err1.status_code, detail="Bad Request")
    except Exception as err2:
        logger.debug(f"Unexpected Error Exception occurred. User is {user_id}. Error message is: {str(err2)}")
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
        logger.info(f"User created successfully by: {payload.email}.")
        return {"status": status.HTTP_201_CREATED}
    except Exception as err:
        logger.debug(f"Error occurred. User is {payload.email}. Error message is: {str(err)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")


@router.post("/login", status_code=status.HTTP_200_OK)
async def login_user(payload: UserLogin, session: AsyncSession = Depends(get_session)):
    if not payload.email or not payload.password:
        logger.debug("Email and password is required")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad Request")

    statement = select(User).where(User.email == payload.email)
    result = await session.execute(statement=statement)
    user = result.scalar_one_or_none()

    error_401 = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized Request")

    if not user:
        logger.debug("Invalid email or username")
        raise error_401

    is_valid = await verify_hash_password(user.hashed_password, payload.password)
    if not is_valid:
        logger.debug("Invalid password")
        raise error_401

    logger.info(f"User: {payload.email} has successfully logged in")
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
    except HTTPException:
        logger.debug("Unauthorized Request")
        raise
    except Exception as err:
        logger.debug(f"Internal Server Error: {str(err)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")


