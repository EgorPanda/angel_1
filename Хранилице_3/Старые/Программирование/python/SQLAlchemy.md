файл config.py для получение строки подключения из переменных окружения файла .env


```
from pydantic_settings import BaseSettings, SettingsConfigDict  
  
class Settings(BaseSettings):  
    DB_HOST : str  
    DB_PORT : int  
    DB_USER : str  
    DB_PASS : str  
    DB_NAME : str  
  
    @property  
    def DATEBASE_URL_asyncpg(self):  
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"  
  
    @property  
    def DATEBASE_URL_psycopg(self):  
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"  
  
    model_config = SettingsConfigDict(env_file=".env")  
  
settings = Settings()
```

Создание движка
`engine = create_engine(url=settings.DATEBASE_URL_psycopg)`

Создание простого запроса к бд

```
with engine.connect() as conn:  
    res = conn.execute(text("SELECT VERSION()"))  
    print(res.all())
```
