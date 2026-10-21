import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Query

from app.consumer import consume_events
from app.database import events_collection, mongodb_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    await mongodb_client.admin.command("ping")

    task = asyncio.create_task(
        consume_events(events_collection)
    )

    try:
        yield
    finally:
        task.cancel()

        try:
            with suppress(asyncio.CancelledError):
                await task
        finally:
            await mongodb_client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/events")
async def get_events(
    limit: int = Query(default=20, ge=1, le=100),
):
    query = (
        events_collection.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )

    return await query.to_list(length=limit)