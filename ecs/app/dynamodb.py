from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ecs.app.config import settings


def get_dynamodb_table():
    resource = boto3.resource("dynamodb", region_name=settings.aws_region)
    return resource.Table(settings.dynamodb_table_name)


def _pk_value(pk: str) -> Decimal:
    return Decimal(pk)


def get_item_by_pk(pk: str) -> dict[str, Any] | None:
    table = get_dynamodb_table()
    response = table.get_item(Key={"PK": _pk_value(pk)})
    return response.get("Item")


def put_item(pk: str, collision_id: str) -> dict[str, Any]:
    table = get_dynamodb_table()
    item = {"PK": _pk_value(pk), "collision_id": collision_id}
    table.put_item(Item=item)
    return item
