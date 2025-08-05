import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from ticketing_app.models import Base
from ticketing_app.database import get_db
from ticketing_app.main import app
import httpx
from httpx import ASGITransport
import pytest
from ticketing_app.routes.ticket_routes import limiter
import os
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter before each test to avoid shared state."""
    limiter.reset()


@pytest_asyncio.fixture(scope="function")
async def setup_db():
    test_engine = create_async_engine(
        os.getenv("TEST_DATABASE_URL"),
        echo=False,
        future=True
    )
    TestingSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield TestingSessionLocal

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_db):
    async with setup_db() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()
