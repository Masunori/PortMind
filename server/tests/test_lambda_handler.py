"""Lambda Function URL adapter tests."""

import json

from app.main import handler


def test_function_url_event_reaches_fastapi_health() -> None:
    """Mangum translates an AWS HTTP API v2/Function URL event without lifespan."""

    event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "example.lambda-url.test", "x-forwarded-proto": "https"},
        "requestContext": {
            "accountId": "anonymous",
            "apiId": "function-url",
            "domainName": "example.lambda-url.test",
            "domainPrefix": "example",
            "http": {
                "method": "GET",
                "path": "/health",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "request-1",
            "routeKey": "$default",
            "stage": "$default",
            "time": "03/Sep/2026:00:00:00 +0000",
            "timeEpoch": 1788393600000,
        },
        "isBase64Encoded": False,
    }
    response = handler(event, object())
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}
