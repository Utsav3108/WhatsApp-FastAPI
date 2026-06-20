from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import dotenv

dotenv.load_dotenv()  # Load environment variables from .env file

POSTGRES_USER = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_USER")
POSTGRES_PASSWORD = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_PASSWORD")
POSTGRES_DB = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_DB")
POSTGRES_PORT = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_PORT")

# DATABASE_URL = f"postgresql+asyncpg://:{POSTGRES_PASSWORD}@localhost:{POSTGRES_DB}"
DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{POSTGRES_PORT}/{POSTGRES_DB}"
print("DATABASE_URL:", DATABASE_URL)  # Debugging line to check the constructed URL

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
Base = declarative_base()

async def get_db():
    async with SessionLocal() as db:
        yield db