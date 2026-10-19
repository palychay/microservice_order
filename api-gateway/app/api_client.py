from typing import Any

import httpx
from fastapi import HTTPException, status


def _upstream_error(response: httpx.Response) -> HTTPException:
    try:
        detail = response.json()
    except ValueError:
        detail = response.text or response.reason_phrase

    return HTTPException(
        status_code=response.status_code,
        detail=detail,
    )


async def request_service(
    method: str,
    url: str,
    json_body: Any | None = None,
    headers: dict | None = None,
):
    async with httpx.AsyncClient(
        timeout=20.0,
        trust_env=False,
    ) as client:
        try:
            response = await client.request(
                method,
                url,
                json=json_body,
                headers=headers,
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Не удалось получить ответ внутреннего сервиса",
            )

    if response.status_code >= 400:
        raise _upstream_error(response)

    return response.json()