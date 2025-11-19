# CodeBuild結果をSlackに投げるLambda
import os
import json
import urllib.request
import boto3
import logging
logger = logging.getLogger()

SSM_PARAM = os.environ.get("SLACK_WEBHOOK_SSM_PARAM_NAME", "")
CHANNEL = os.environ.get("SLACK_CHANNEL", "#general")

ssm = boto3.client("ssm")


def get_webhook_url() -> str:
    resp = ssm.get_parameter(
        Name=SSM_PARAM,
        WithDecryption=True
    )
    return resp["Parameter"]["Value"]


def build_message(event: dict) -> dict:
    detail_type = event.get("detail-type", "")
    detail = event.get("detail", {})

    # CodeBuild専用の整形（まずはこれだけでOK）
    if detail_type == "CodeBuild Build State Change":
        project = detail.get("project-name", "unknown")
        status = detail.get("build-status", "UNKNOWN")
        logs = (
            detail.get("additional-information", {})
            .get("logs", {})
            .get("deep-link", "")
        )

        text = (
            f"[CodeBuild] project: {project}\n"
            f"Status: {status}\n"
        )
        if logs:
            text += f"Logs: {logs}"

    else:
        # それ以外はとりあえず生JSON
        text = f"[{detail_type}] \n```json\n{json.dumps(detail, indent=2)}\n```"

    payload = {
        "text": text,
    }

    if CHANNEL:
        payload["channel"] = CHANNEL

    return payload


def send_slack(webhook_url: str, message: dict) -> None:
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8", errors="ignore")
            logger.info("Slack response status=%s body=%s", res.status, body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        logger.error(
            "Slack HTTPError status=%s body=%s", e.code, error_body
        )
        raise


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    webhook_url = get_webhook_url()
    message = build_message(event)
    send_slack(webhook_url, message)

    return {"status": "ok"}
