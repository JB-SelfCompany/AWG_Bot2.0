from typing import Callable, Dict, Any, Awaitable, List
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


class AuthMiddleware(BaseMiddleware):
    """Мидлварь для проверки авторизации администраторов"""
    
    def __init__(self, admin_ids: List[int]):
        self.admin_ids = admin_ids
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка доступа пользователя"""
        
        user_id = event.from_user.id
        
        if not self.admin_ids or user_id not in self.admin_ids:
            if isinstance(event, Message):
                await event.answer("❌ У вас нет доступа к этому боту")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ У вас нет доступа к этому боту", show_alert=True)
            return
        
        return await handler(event, data)