from typing import Any

from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ecs.app import dynamodb

app = FastAPI(title="Collision Report API")


class PostItemRequest(BaseModel):
    PK: str = Field(..., description="Partition key")
    collision_id: str


class PostItemResponse(BaseModel):
    PK: str
    collision_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/collisions/{pk}")
def get_item(pk: str) -> dict[str, Any]:
    try:
        item = dynamodb.get_item_by_pk(pk)
    except ClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return item


@app.post("/collisions", response_model=PostItemResponse, status_code=201)
def post_item(body: PostItemRequest) -> PostItemResponse:
    try:
        item = dynamodb.put_item(pk=body.PK, collision_id=body.collision_id)
    except ClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return PostItemResponse(**item)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
