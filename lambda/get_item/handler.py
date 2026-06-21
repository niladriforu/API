from splunk_otel import init_splunk_otel
init_splunk_otel()

import json
import logging
import os
import time
from decimal import Decimal

import boto3

from opentelemetry import metrics
meter = metrics.get_meter("collisions-dev")
collision_lookup_counter = meter.create_counter(
    name="collisions.lookup.count",
    description="Collision lookups by outcome",
)
dynamodb_duration = meter.create_histogram(
    name="collisions.dynamodb.get_item.duration",
    description="DynamoDB GetItem latency",
    unit="ms",
)

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
tracer = trace.get_tracer(__name__)
TABLE_NAME = os.environ.get("TABLE_NAME", "collision_report_dev")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _debug_otel_config() -> None:
    logger.info(
        "OTEL config | service=%s realm=%s token=%s table=%s",
        os.getenv("OTEL_SERVICE_NAME", "<unset>"),
        os.getenv("SPLUNK_REALM", "<unset>"),
        _mask_secret(os.getenv("SPLUNK_ACCESS_TOKEN")),
        TABLE_NAME,
    )
    logger.info(
        "OTEL providers | meter=%s tracer=%s",
        type(metrics.get_meter_provider()).__name__,
        type(trace.get_tracer_provider()).__name__,
    )


def _record_outcome(outcome: str) -> None:
    collision_lookup_counter.add(1, {"outcome": outcome})
    logger.info("Metric incremented | collisions.lookup.count outcome=%s", outcome)


def _trace_context_for_logs() -> tuple[str, str]:
    span_ctx = trace.get_current_span().get_span_context()
    if not span_ctx or not span_ctx.is_valid:
        return ("<none>", "<none>")
    return (f"{span_ctx.trace_id:032x}", f"{span_ctx.span_id:016x}")


def _to_json_serializable(value):
    """DynamoDB returns numbers as Decimal; JSON needs int/float."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, dict):
        return {k: _to_json_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_serializable(v) for v in value]
    return value


def _response(status_code: int, body: dict) -> dict:
    # API Gateway requires body to be a JSON string, not a dict.
    serializable = _to_json_serializable(body)
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(serializable),
    }


def _parse_id(event: dict) -> int | None:
    path_params = event.get("pathParameters") or {}
    raw_id = path_params.get("id")
    print(f"raw_id: {raw_id}")
    if raw_id is None or str(raw_id).strip() == "":
        return None
    try:
        print(f"Parsing id: {raw_id}")
        return int(raw_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid id") from None


def _flush_otel() -> None:
    """Best-effort flush for Lambda's short execution model."""
    try:
        metrics_flushed = metrics.get_meter_provider().force_flush(1000)
        logger.info("metrics force_flush result=%s", metrics_flushed)
    except Exception as e:
        logger.exception("metrics force_flush failed: %s", e)

    try:
        traces_flushed = trace.get_tracer_provider().force_flush(1000)
        logger.info("traces force_flush result=%s", traces_flushed)
    except Exception as e:
        logger.exception("traces force_flush failed: %s", e)


def lambda_handler(event, context):
    print("Current Event:", event)
    print("current context", context)
    _debug_otel_config()
    response = None
    try:
        with tracer.start_as_current_span("lambda.collision_handler") as root_span:
            root_span.set_attribute("faas.name", os.getenv("AWS_LAMBDA_FUNCTION_NAME", "<unknown>"))
            root_span.set_attribute("faas.invocation_id", getattr(context, "aws_request_id", "<none>"))
            root_span.set_attribute("db.table", TABLE_NAME)
            root_span.set_attribute("http.route", "/collisions/{id}")

            trace_id, span_id = _trace_context_for_logs()
            logger.info("Trace context | trace_id=%s span_id=%s", trace_id, span_id)

            with tracer.start_as_current_span("validation.parse_id"):
                try:
                    record_id = _parse_id(event)
                except ValueError:
                    _record_outcome("invalid_id")
                    root_span.set_attribute("request.outcome", "invalid_id")
                    response = _response(400, {"message": "Invalid id"})
                    return response

            if record_id is None:
                _record_outcome("missing_id")
                root_span.set_attribute("request.outcome", "missing_id")
                response = _response(400, {"message": "Missing id"})
                return response

            root_span.set_attribute("collision.id", record_id)

            with tracer.start_as_current_span("dynamodb.get_item") as span:
                span.set_attribute("collision.id", record_id)
                span.set_attribute("db.system", "dynamodb")
                span.set_attribute("db.operation", "GetItem")
                span.set_attribute("db.table", TABLE_NAME)
                start = time.perf_counter()
                result = table.get_item(Key={"PK": record_id})
                duration_ms = (time.perf_counter() - start) * 1000

            item = result.get("Item")
            db_outcome = "found" if item else "not_found"
            dynamodb_duration.record(duration_ms, {"outcome": db_outcome})
            logger.info(
                "DynamoDB GetItem | duration_ms=%.2f outcome=%s",
                duration_ms,
                db_outcome,
            )

            with tracer.start_as_current_span("response.build"):
                if not item:
                    _record_outcome("not_found")
                    root_span.set_attribute("request.outcome", "not_found")
                    response = _response(404, {"message": "Collision record not found"})
                    return response

                _record_outcome("found")
                root_span.set_attribute("request.outcome", "found")
                response = _response(200, item)
                return response
    except Exception as e:
        current = trace.get_current_span()
        current.record_exception(e)
        current.set_status(Status(StatusCode.ERROR, str(e)))
        logger.exception("Unhandled exception in lambda_handler: %s", e)
        raise
    finally:
        _flush_otel()
