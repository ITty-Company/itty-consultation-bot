import json
import os
from datetime import datetime
from typing import List, Dict, Optional

class BookingDatabase:
    def __init__(self, data_file: str = 'bookings.json'):
        self.data_file = data_file
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Создает файл данных, если его нет"""
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    def _read_data(self) -> List[Dict]:
        """Читает данные из файла"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _write_data(self, data: List[Dict]):
        """Записывает данные в файл"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_booking(self, user_id: int, username: str, name: str, 
                   contact: str, date: str, time: str, topic: str, 
                   consultation_type: str = 'Общая консультация') -> Dict:
        """Добавляет новую запись"""
        data = self._read_data()
        booking_id = max([b.get('id', 0) for b in data], default=0) + 1
        
        booking = {
            'id': booking_id,
            'user_id': user_id,
            'username': username,
            'name': name,
            'contact': contact,
            'date': date,
            'time': time,
            'topic': topic,
            'consultation_type': consultation_type,
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        data.append(booking)
        self._write_data(data)
        return booking
    
    def get_all_bookings(self) -> List[Dict]:
        """Получает все записи"""
        return self._read_data()
    
    def get_user_bookings(self, user_id: int) -> List[Dict]:
        """Получает записи конкретного пользователя"""
        data = self._read_data()
        return [b for b in data if b['user_id'] == user_id]
    
    def get_booking_by_id(self, booking_id: int) -> Optional[Dict]:
        """Получает запись по ID"""
        data = self._read_data()
        for booking in data:
            if booking['id'] == booking_id:
                return booking
        return None
    
    def update_booking_status(self, booking_id: int, status: str):
        """Обновляет статус записи"""
        data = self._read_data()
        for booking in data:
            if booking['id'] == booking_id:
                booking['status'] = status
                self._write_data(data)
                return True
        return False
    
    def delete_booking(self, booking_id: int, user_id: int = None):
        """Удаляет запись (только свою или админ может удалить любую)"""
        data = self._read_data()
        for i, booking in enumerate(data):
            if booking['id'] == booking_id:
                if user_id is None or booking['user_id'] == user_id:
                    data.pop(i)
                    self._write_data(data)
                    return True
        return False
    
    def get_statistics(self):
        """Получает статистику по записям"""
        data = self._read_data()
        total = len(data)
        pending = len([b for b in data if b['status'] == 'pending'])
        confirmed = len([b for b in data if b['status'] == 'confirmed'])
        cancelled = len([b for b in data if b['status'] == 'cancelled'])
        
        return {
            'total': total,
            'pending': pending,
            'confirmed': confirmed,
            'cancelled': cancelled
        }

