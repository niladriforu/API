# API

Monorepo for collision report APIs backed by DynamoDB.

## Layout

```
lambda/authorizer/handler.py   # API Gateway Lambda authorizer
lambda/get_item/handler.py     # GetItem Lambda
lambda/post_item/handler.py    # PostItem Lambda
ecs/app/app.py                 # FastAPI app (ALB / ECS)
```

## Environment variables

| Variable | Default | Used by |
|----------|---------|---------|
| `DYNAMODB_TABLE_NAME` | `collision_report_dev` | ECS FastAPI |
| `AWS_REGION` | `us-west-2` | ECS FastAPI |

Lambda functions use env vars configured in AWS. Paste your scripts into the `lambda/` handlers.

## ECS FastAPI (local)

```bash
uv sync
uv run python -m ecs.app.app
```

Or with auto-reload during development:

```bash
uv run uvicorn ecs.app.app:app --reload --host 0.0.0.0 --port 8000
```

Routes:

- `GET /health`
- `GET /items/{pk}` — GetItem by partition key (`PK`)
- `POST /items` — body: `{"PK": "...", "collision_id": "..."}`

## Docker

```bash
docker build -f ecs/Dockerfile -t api-fastapi .
docker run -p 8000:8000 -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY api-fastapi
```

## GitHub Actions → ECR

On push to `main`, the workflow builds and pushes `api-fastapi:latest` to ECR in `us-west-2`.

Required GitHub secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Ensure the ECR repository `api-fastapi` exists in `us-west-2` before the first run.
