"""
Модуль для работы с Google Sheets API
Сохраняет заявки из бота в Google Таблицу
"""
import os
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Пытаемся импортировать библиотеки Google
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.warning("Google API libraries not installed. Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

import config

class SheetsManager:
    """Менеджер для работы с Google Sheets"""
    
    def __init__(self):
        self.initialized = False
        self.service = None
        self.sheet_id = config.GOOGLE_SHEET_ID
        self.sheet_name = config.GOOGLE_SHEET_NAME
        self._sheet_gid: Optional[int] = None
        
        if not GOOGLE_AVAILABLE:
            logger.warning("Google API libraries not available. Google Sheets functionality disabled.")
            return
        
        if not config.USE_GOOGLE_SHEETS:
            logger.info("Google Sheets disabled in config (USE_GOOGLE_SHEETS=false)")
            return
        
        if not self.sheet_id:
            logger.warning("GOOGLE_SHEET_ID not set in config")
            return
        
        credentials_file = config.GOOGLE_CREDENTIALS_FILE
        if not credentials_file or not os.path.exists(credentials_file):
            logger.warning(f"Google credentials file not found: {credentials_file}")
            logger.warning("Please download credentials.json from Google Cloud Console")
            return
        
        try:
            # Загружаем credentials
            creds = Credentials.from_service_account_file(
                credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Создаем сервис
            self.service = build('sheets', 'v4', credentials=creds)
            
            # Проверяем доступ к таблице
            try:
                sheet = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
                sheet_title = sheet.get('properties', {}).get('title', 'Unknown')
                
                # Проверяем, существует ли указанный лист
                sheets_list = sheet.get('sheets', [])
                sheet_names = [s.get('properties', {}).get('title', '') for s in sheets_list]
                
                logger.info(f"✅ Google Sheets initialized. Sheet: {sheet_title}")
                logger.info(f"📋 Available sheets: {sheet_names}")
                
                if self.sheet_name not in sheet_names:
                    logger.warning(f"⚠️ Sheet '{self.sheet_name}' not found! Available sheets: {sheet_names}")
                    logger.warning(f"⚠️ Will try to use first sheet: {sheet_names[0] if sheet_names else 'Sheet1'}")
                    if sheet_names:
                        self.sheet_name = sheet_names[0]
                
                # Cache sheet gid for current sheet_name
                self._sheet_gid = self._resolve_sheet_gid(sheet)
                
                self.initialized = True
            except HttpError as e:
                logger.error(f"❌ Error accessing Google Sheet: {e}")
                logger.error("Make sure the service account email has access to the sheet")
                if hasattr(e, 'content'):
                    logger.error(f"Error details: {e.content}")
        
        except Exception as e:
            logger.error(f"❌ Error initializing Google Sheets: {e}", exc_info=True)

    def _resolve_sheet_gid(self, spreadsheet: Optional[Dict] = None) -> Optional[int]:
        """Возвращает sheetId (gid) по названию листа."""
        if not self.initialized and spreadsheet is None:
            return None
        try:
            if spreadsheet is None:
                spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
            for s in spreadsheet.get("sheets", []):
                props = s.get("properties", {})
                if props.get("title") == self.sheet_name:
                    gid = props.get("sheetId")
                    return int(gid) if gid is not None else None
        except Exception as e:
            logger.error(f"Error resolving sheet gid: {e}")
        return None

    def _get_sheet_gid(self) -> Optional[int]:
        """Кэшированный sheetId (gid) для текущего листа."""
        if self._sheet_gid is not None:
            return self._sheet_gid
        self._sheet_gid = self._resolve_sheet_gid()
        return self._sheet_gid

    def _normalize_row_formatting(self, row_number: int) -> None:
        """
        Сбрасывает форматирование строки к "обычному" виду,
        чтобы заявки не наследовали стиль заголовка (синий/жирный).
        """
        gid = self._get_sheet_gid()
        if gid is None:
            logger.warning("Sheet gid not available; cannot normalize row formatting.")
            return

        # Google Sheets API uses 0-based indices and endIndex is exclusive
        start_idx = max(0, row_number - 1)
        end_idx = row_number

        # 1) Reset general formatting for A:O
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": gid,
                        "startRowIndex": start_idx,
                        "endRowIndex": end_idx,
                        "startColumnIndex": 0,   # A
                        "endColumnIndex": 15,    # O (exclusive)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                            "textFormat": {
                                "bold": False,
                                "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                            },
                            "horizontalAlignment": "LEFT",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)",
                }
            }
        ]

        # 2) Force number formats for Date (B) and Time (C)
        # This prevents seeing serial numbers like 46043 / 0.0833...
        requests += [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": gid,
                        "startRowIndex": start_idx,
                        "endRowIndex": end_idx,
                        "startColumnIndex": 1,   # B
                        "endColumnIndex": 2,     # B (exclusive)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": gid,
                        "startRowIndex": start_idx,
                        "endRowIndex": end_idx,
                        "startColumnIndex": 2,   # C
                        "endColumnIndex": 3,     # C (exclusive)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "TIME", "pattern": "hh:mm:ss"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
        ]

        request_body = {"requests": requests}

        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request_body,
            ).execute()
        except Exception as e:
            logger.error(f"Error normalizing row formatting: {e}")
    
    def get_sheet_url(self) -> Optional[str]:
        """Возвращает URL таблицы"""
        if not self.initialized:
            return None
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit"
    
    def get_next_request_number(self) -> int:
        """Получает следующий номер заявки (количество строк - 1, так как первая строка - заголовок)"""
        if not self.initialized:
            return 1
        
        try:
            total_rows = self.get_total_rows()
            return max(1, total_rows)  # Минимум 1
        except Exception as e:
            logger.error(f"Error getting next request number: {e}")
            return 1
    
    def get_total_rows(self) -> int:
        """Получает общее количество строк в таблице"""
        if not self.initialized:
            return 0
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{self.sheet_name}!A:A"
            ).execute()
            
            values = result.get('values', [])
            return len(values)
        except Exception as e:
            logger.error(f"Error getting total rows: {e}")
            return 0
    
    def add_request(self, request_data: Dict) -> bool:
        """
        Добавляет заявку в Google Sheets
        
        Args:
            request_data: Словарь с данными заявки:
                - datetime: дата и время (формат: 'YYYY-MM-DD HH:MM:SS')
                - name: имя пользователя
                - username: username пользователя
                - user_id: ID пользователя
                - language: язык
                - request_type: тип запроса
                - project_for: для кого проект
                - understanding: понимание
                - niche: ниша
                - details: детали/описание
                - project_type: тип проекта
                - has_ready: есть ли готовое
                - goal: цель
                - timeline: сроки
                - important: важное
                - contact_type: тип контакта
                - contact: контакт
                - status: статус
        
        Returns:
            True если успешно, False если ошибка
        """
        if not self.initialized:
            logger.warning("Google Sheets not initialized. Cannot add request.")
            return False
        
        try:
            # Разделяем дату и время
            datetime_str = request_data.get('datetime', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            if ' ' in datetime_str:
                date_part, time_part = datetime_str.split(' ', 1)
            else:
                date_part = datetime_str
                time_part = ''
            
            # Получаем следующий номер заявки
            request_number = self.get_next_request_number()
            
            # Формируем строку для добавления
            row = [
                request_number,  # №
                date_part,  # Дата
                time_part,  # Время
                request_data.get('name', ''),  # Пользователь
                request_data.get('user_id', ''),  # Код пользователя
                request_data.get('request_type', ''),  # Выбранная кнопка
                request_data.get('understanding', ''),  # Понимание
                request_data.get('niche', ''),  # Ниша
                request_data.get('details', ''),  # Детали/Описание
                request_data.get('goal', ''),  # Цель
                request_data.get('timeline', ''),  # Сроки
                request_data.get('has_ready', ''),  # Есть готовое
                request_data.get('contact_type', ''),  # Контакт (тип)
                request_data.get('contact', ''),  # Контакт (значение)
                request_data.get('status', 'Новая')  # Статус
            ]
            
            # Добавляем строку в таблицу
            body = {
                'values': [row]
            }
            
            range_name = f"{self.sheet_name}!A:O"
            logger.info(f"Adding row to Google Sheets. Range: {range_name}, Sheet ID: {self.sheet_id}")
            logger.debug(f"Row data: {row}")
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            updated_range = result.get('updates', {}).get('updatedRange', 'unknown')
            updated_rows = result.get('updates', {}).get('updatedRows', 0)
            logger.info(f"✅ Request added to Google Sheets. Range: {updated_range}, Rows updated: {updated_rows}")

            # If possible, normalize formatting for the inserted row so it looks "ordinary"
            try:
                # updatedRange example: Аркуш1!A7:O7
                import re
                m = re.search(r"![A-Z]+(\d+):[A-Z]+(\d+)$", updated_range)
                if m:
                    row_number = int(m.group(1))
                    self._normalize_row_formatting(row_number=row_number)
                else:
                    # Fallback: estimate by total rows after append
                    total_rows = self.get_total_rows()
                    if total_rows > 1:
                        self._normalize_row_formatting(row_number=total_rows)
            except Exception as e:
                logger.error(f"Error post-processing formatting: {e}")
            return True
        
        except HttpError as e:
            logger.error(f"❌ HTTP Error adding request to Google Sheets: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error adding request to Google Sheets: {e}", exc_info=True)
            return False
    
    def get_row_data(self, row_number: int) -> Optional[Dict]:
        """Получает данные строки по номеру"""
        if not self.initialized:
            return None
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{self.sheet_name}!A{row_number}:O{row_number}"
            ).execute()
            
            values = result.get('values', [])
            if not values or not values[0]:
                return None
            
            row = values[0]
            return {
                'number': row[0] if len(row) > 0 else '',
                'date': row[1] if len(row) > 1 else '',
                'time': row[2] if len(row) > 2 else '',
                'name': row[3] if len(row) > 3 else '',
                'user_id': row[4] if len(row) > 4 else '',
                'request_type': row[5] if len(row) > 5 else '',
                'understanding': row[6] if len(row) > 6 else '',
                'niche': row[7] if len(row) > 7 else '',
                'details': row[8] if len(row) > 8 else '',
                'goal': row[9] if len(row) > 9 else '',
                'timeline': row[10] if len(row) > 10 else '',
                'has_ready': row[11] if len(row) > 11 else '',
                'contact_type': row[12] if len(row) > 12 else '',
                'contact': row[13] if len(row) > 13 else '',
                'status': row[14] if len(row) > 14 else ''
            }
        except Exception as e:
            logger.error(f"Error getting row data: {e}")
            return None
    
    def delete_row(self, row_number: int) -> bool:
        """Удаляет строку по номеру"""
        if not self.initialized:
            return False
        
        try:
            gid = self._get_sheet_gid()
            if gid is None:
                logger.error("Sheet gid not available; cannot delete row.")
                return False
            # Удаляем строку (нужно использовать batchUpdate)
            request_body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': gid,
                            'dimension': 'ROWS',
                            'startIndex': row_number - 1,  # Номер строки - 1 (индекс начинается с 0)
                            'endIndex': row_number
                        }
                    }
                }]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request_body
            ).execute()
            
            logger.info(f"✅ Row {row_number} deleted from Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Error deleting row: {e}")
            return False
    
    def update_row_status(self, row_number: int, new_status: str) -> bool:
        """Обновляет статус строки"""
        if not self.initialized:
            return False
        
        try:
            # Обновляем статус в колонке O (15-я колонка)
            body = {
                'values': [[new_status]]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{self.sheet_name}!O{row_number}",
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            logger.info(f"✅ Row {row_number} status updated to '{new_status}'")
            return True
        except Exception as e:
            logger.error(f"Error updating row status: {e}")
            return False

# Создаем глобальный экземпляр
sheets_manager = SheetsManager()
