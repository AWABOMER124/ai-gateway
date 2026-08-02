"""
config.py — إعدادات التطبيق من environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# تحميل .env من جذر المشروع
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path)


class Settings:
    database_url:     str  = os.getenv('DATABASE_URL', '')
    openai_api_key:   str  = os.getenv('OPENAI_API_KEY', '')
    embedding_model:  str  = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    chat_model:       str  = os.getenv('CHAT_MODEL', 'gpt-4.1-mini')
    default_top_k:    int  = int(os.getenv('DEFAULT_TOP_K', '6'))

    def validate(self):
        errors = []
        if not self.database_url:
            errors.append('DATABASE_URL غير موجود في .env')
        if not self.openai_api_key:
            errors.append('OPENAI_API_KEY غير موجود في .env')
        if errors:
            raise EnvironmentError('\n'.join(errors))


settings = Settings()
