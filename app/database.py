import ssl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import certifi
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import dotenv

dotenv.load_dotenv()  # Load environment variables from .env file

POSTGRES_USER = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_USER")
POSTGRES_PASSWORD = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_PASSWORD")
POSTGRES_DB = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_DB")
POSTGRES_PORT = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_PORT")

# DATABASE_URL = f"postgresql+asyncpg://:{POSTGRES_PASSWORD}@localhost:{POSTGRES_DB}"
DATABASE_URL = dotenv.get_key(dotenv.find_dotenv(), "POSTGRES_URL")
# print("DATABASE_URL:", DATABASE_URL)  # Debugging line to check the constructed URL


def _sanitize_database_url(url: str) -> str:
    """Neon's dashboard hands out plain 'postgresql://...?sslmode=require'
    connection strings, but this project needs the async asyncpg driver,
    and asyncpg.connect() has no 'sslmode' kwarg — SQLAlchemy forwards any
    query params on the URL straight through to it. Force the '+asyncpg'
    driver onto the scheme and strip 'sslmode' from the query string; SSL
    is configured instead via connect_args below."""
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
    return urlunsplit(parts._replace(scheme=scheme, query=urlencode(query)))


DATABASE_URL = _sanitize_database_url(DATABASE_URL)

# cafile=certifi.where() instead of relying on the system trust store —
# some deployment images (and some local dev machines) don't have one
# configured, which surfaces as CERTIFICATE_VERIFY_FAILED against Neon's
# otherwise-valid cert.
ssl_context = ssl.create_default_context(cafile=certifi.where())

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"ssl": ssl_context},
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