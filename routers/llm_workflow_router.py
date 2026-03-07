from fastapi import APIRouter, HTTPException, status, Request, Response, Depends
from core.security import token_decoder, create_access_token
from llm_workflow.workflows.base import ChatbotExecutor
from llm_workflow.workflows.flows import AdaptiveChatbot
from pydantic import BaseModel, Field



router = APIRouter(
    prefix="/v1",
    tags=["v1"],
)
class Token(BaseModel):
    token: str


class MessageResponse(BaseModel):
    message: str


class MessageRequest(MessageResponse):
    # id: Union[str, Any] = Field(default="user_test")
    token: str




@router.post("/get-token")
async def get_token(token: Token):
    subject = {"sub":token.token}
    return create_access_token(subject=subject)


@router.post("/send-message", response_model=MessageResponse)
async def send_message(body: MessageRequest):
    try:
        payload = token_decoder(token=body.token)

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        chat_obj = AdaptiveChatbot(
            user_id=user_id,
            input_message=body.message,
        )
        chatbot = ChatbotExecutor(chat_obj)
        response = await chatbot.execute()
        return MessageResponse(message=str(response))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)