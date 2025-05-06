from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


engine = create_async_engine("sqlite+aiosqlite:///./ecommerce.db")
async def get_db():
    async with AsyncSession(engine) as session:
        yield session

