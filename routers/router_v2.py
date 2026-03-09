from fastapi import APIRouter, status, HTTPException, Response, Request, Depends
from pydantic import BaseModel
from functools import lru_cache
from core.security import (
    get_hash_password,
    verify_hash_password,
    login_with_access_and_refresh_token
)
import asyncio




router = APIRouter(
    prefix="/v2",
    tags=["v2"]
)

@lru_cache(maxsize=100)
def cache_for_lock(user_id: str) -> asyncio.Lock:
    return asyncio.Lock()

@lru_cache(maxsize=100)
def cache_user_info(user_id: str) -> dict:
    return {}




class Message(BaseModel):
    content: str

class Login(BaseModel):
    username: str
    password: str


class UserForm(Login):
    email: str




@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def sign_up_by_user(user_form: UserForm):
    async with cache_for_lock(user_id=user_form.email):

        user_info = cache_user_info(user_form.email)

        email = user_info.get("email")
        if email == user_form.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")


        hashed_password = await get_hash_password(user_form.password)

        user_info.update({
            "username": user_form.username,
            "email": user_form.email,
            "password": hashed_password,
        })
        return {"message": "User created successfully"}







@router.post("/login", status_code=status.HTTP_200_OK)
async def login_by_user(user_form: UserForm, response: Response):
    user_info = cache_user_info(user_form.username)
    hashed_password = user_info.get("password")
    is_valid = await verify_hash_password(hashed_password, user_form.password)
    if is_valid:
        login_with_access_and_refresh_token(
            subject=user_form.username,
            response=response
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials")



# @router.post("/send-message")
# async def send_message_to_chatbot(body: Message):
#     pass