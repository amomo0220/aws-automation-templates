import json
import os
import logging
import urllib.request
import urllib.error
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")


def get_webhook_url() -> str:
    """
    SSM から Webhook URL を取得
    """
    param_name = os.environ.get("SLACK_WEBHOOK_SSM_PARAM_NAME")

    if not param_name:
        logger.error("Environment variable SLACK_WEBHOOK_SSM_PARAM_NAME is not set")
        raise RuntimeError("SLACK_WEBHOOK_SSM_PARAM_NAME is not set")

    try:
        res = ssm.get_parameter(
            Name=param_name,
            WithDecryption=True,
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        message = e.response.get("Error", {}).get("Message", "")
        region = ssm.meta.region_name

        logger.error(
            "Failed to get SSM parameter: name=%s region=%s code=%s message=%s",
            param_name,
            region,
            code,
            message,
        )
        # Lambda は失敗させる（成功にはしない）
        raise

    webhook = res.get("Parameter", {}).get("Value", "").strip()

    if not webhook:
        logger.error(
            "SSM parameter is empty: name=%s region=%s",
            param_name,
            ssm.meta.region_name,
        )
        raise RuntimeError("Webhook URL from SSM is empty")

    return webhook


def send_slack(webhook_url: str, message: str) -> None:
    payload = {"text": message}
    data = json.dumps(payload).encode("utf-8")

    # URL 全体はログに出さない。末尾だけログ用にマスク
    masked_tail = webhook_url[-12:] if len(webhook_url) > 12 else webhook_url

    req = urllib.request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8", errors="ignore")
            logger.info(
                "Slack response success: status=%s body=%s url_tail=%s",
                res.status,
                body,
                masked_tail,
            )
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        logger.error(
            "Slack HTTPError: status=%s body=%s url_tail=%s",
            e.code,
            error_body,
            masked_tail,
        )
        # 4xx/5xx は必ず Lambda エラーとして表面化させる
        raise
    except urllib.error.URLError as e:
        logger.error(
            "Slack URLError: reason=%s url_tail=%s",
            getattr(e, "reason", None),
            masked_tail,
        )
        raise


def build_message(event: dict) -> str:
    """
    メッセージ整形。
    CodeBuild のイベントを想定。
    想定外の形式なら unknown として扱いつつ warning を出す。
    """
    detail = event.get("detail") or {}

    project = detail.get("project-name")
    status = detail.get("build-status")

    if not project or not status:
        # 想定外のイベント形式。event 全体をログに吐くと大変なので一部だけ
        logger.warning(
            "Unexpected event format: project=%s status=%s event_snippet=%s",
            project,
            status,
            json.dumps(event, default=str)[:500],  # 先頭 500 文字だけ
        )
        project = project or "unknown"
        status = status or "UNKNOWN"

    # ステータスに応じて絵文字を出し分け
    upper_status = status.upper()
    if upper_status == "SUCCEEDED":
        emoji = ":white_check_mark:"
    elif upper_status in ("FAILED", "FAULT", "TIMED_OUT", "STOPPED"):
        emoji = ":fire:"
    else:
        emoji = ":information_source:"

    message = f"{emoji} [CodeBuild] Project: {project} / Status: {upper_status}"
    return message


def lambda_handler(event, context):
    """
    エントリーポイント
    """
    logger.info("Received event: %s", json.dumps(event, default=str)[:500])

    webhook_url = get_webhook_url()
    message = build_message(event)

    send_slack(webhook_url, message)

    return {
        "ok": True,
        "message": message,
    }
