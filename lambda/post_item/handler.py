import base64
import json
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("TABLE_NAME", "collision_report_dev")

REQUIRED_FIELDS = ("PK", "crash_date", "crash_time", "collision_id")

INTEGER_FIELDS = {
    "PK",
    "zip_code",
    "number_of_persons_injured",
    "number_of_persons_killed",
    "number_of_pedestrians_injured",
    "number_of_pedestrians_killed",
    "number_of_cyclist_injured",
    "number_of_cyclist_killed",
    "number_of_motorist_injured",
    "number_of_motorist_killed",
    "collision_id",
}
print('hello')
FLOAT_FIELDS = {"latitude", "longitude"}

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _to_json_serializable(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {k: _to_json_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_serializable(v) for v in value]
    return value


def _response(status_code: int, body: dict) -> dict:
    serializable = _to_json_serializable(body)
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(serializable),
    }


def _parse_body(event: dict) -> dict:
    raw_body = event.get("body")
    if raw_body is None or (isinstance(raw_body, str) and raw_body.strip() == ""):
        raise ValueError("Missing request body")

    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    if isinstance(raw_body, str):
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body") from exc
    elif isinstance(raw_body, dict):
        payload = raw_body
    else:
        raise ValueError("Invalid request body")

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    return payload


def _coerce_field(name: str, value):
    if value is None:
        return None
    if name in INTEGER_FIELDS:
        return int(value)
    if name in FLOAT_FIELDS:
        return Decimal(str(value))
    return value


def _build_item(payload: dict,event: dict) -> dict:
    missing = [
        field
        for field in REQUIRED_FIELDS
        if field not in payload or payload[field] is None or payload[field] == ""
    ]
    if missing:
        raise ValueError(
            "PK, crash_date, crash_time, and collision_id are required"
        )

    try:
        pk = int(payload["PK"])
    except (TypeError, ValueError) as exc:
        raise ValueError("PK must be an integer") from exc

    item = {"PK": pk}
    for key, value in payload.items():
        if key == "PK":
            continue
        item[key] = _coerce_field(key, value)

    for field in REQUIRED_FIELDS:
        if field != "PK":
            item[field] = _coerce_field(field, payload[field])
    
    print(f'just before getting the email : {event}')
    item["email_address"] = (
        event.get("requestContext", {})
            .get("authorizer", {})
            .get("email")
    )
    item["request_timestamp"] = (
        event.get("requestContext", {})
            .get("requestTime", {})
    )

    return item


def lambda_handler(event, context):
    print(f"event: {json.dumps(event)}")
    try:
        payload = _parse_body(event)
        item = _build_item(payload,event)
    except ValueError as exc:
        return _response(400, {"message": str(exc)})

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(409, {"message": "A record with this PK already exists"})
        raise

    return _response(201, item)
