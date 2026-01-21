import json
import os
from typing import List, Dict, Optional
from datetime import datetime

class AIContextManager:
    """Управління контекстом діалогу для AI-асистента"""
    
    def __init__(self, context_file: str = 'ai_context.json'):
        self.context_file = context_file
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Створює файл даних, якщо його немає"""
        if not os.path.exists(self.context_file):
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    
    def _read_data(self) -> Dict:
        """Читає дані з файлу"""
        try:
            with open(self.context_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _write_data(self, data: Dict):
        """Записує дані в файл"""
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_context(self, user_id: int, chat_id: int = None) -> List[Dict]:
        """Отримує контекст діалогу для користувача"""
        data = self._read_data()
        key = f"{chat_id}_{user_id}" if chat_id else str(user_id)
        return data.get(key, [])
    
    def add_message(self, user_id: int, role: str, content: str, chat_id: int = None):
        """Додає повідомлення до контексту"""
        data = self._read_data()
        key = f"{chat_id}_{user_id}" if chat_id else str(user_id)
        
        if key not in data:
            data[key] = []
        
        message = {
            'role': role,  # 'user' або 'assistant'
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        data[key].append(message)
        
        # Обмежуємо історію останніми 20 повідомленнями
        if len(data[key]) > 20:
            data[key] = data[key][-20:]
        
        self._write_data(data)
    
    def clear_context(self, user_id: int, chat_id: int = None):
        """Очищає контекст діалогу"""
        data = self._read_data()
        key = f"{chat_id}_{user_id}" if chat_id else str(user_id)
        if key in data:
            data[key] = []
            self._write_data(data)
            return True
        return False
    
    def get_chat_history(self, chat_id: int) -> List[Dict]:
        """Отримує історію группового чату"""
        data = self._read_data()
        history = []
        for key, messages in data.items():
            if key.startswith(f"{chat_id}_"):
                history.extend(messages)
        return sorted(history, key=lambda x: x.get('timestamp', ''))

