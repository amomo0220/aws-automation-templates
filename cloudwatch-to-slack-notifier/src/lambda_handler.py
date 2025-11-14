import base64
import gzip
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_REGION = "ap-northeast-1"
MAX_LINES = int(os.environ.get("MAX_LINES", "3"))

def _build_maps() -> tuple[dict[str, str], dict[str, str]]:
    """
    環境変数 PATH_{n}, HOOK_URL_{n}, PROJECT_NAME_{n} から
    logGroup → webhook , project_name のマップを構築する
    """
    webhook_map: dict[str, str] = {}
    project_name_map: dict[str, str] = {}

    for key, value in os.environ.items():
        if not key.startswith("PATH_"):
            continue
        suffix = key.split("_", 1)[1]
        path = value
        if not path:
            continue

        hook_key = f"HOOK_URL_{suffix}"
        proj_key = f"PROJECT_NAME_{suffix}"

        hook = os.environ.get(hook_key)
        proj = os.environ.get(proj_key)

        if hook:
            webhook_map[path] = hook
        if proj:
            project_name_map[path] = proj

    return webhook_map, project_name_map

WEBHOOK_MAP, PROJECT_NAME_MAP = _build_maps()

def build_log_url(region: str, log_group: str, log_stream: str) -> str:
    """
    CloudWatch Logs コンソールで、対象の logGroup/logStream を開く URL を作成
    """
    encoded_group = urllib.parse.quote(log_group, safe="")
    encoded_stream = urllib.parse.quote(log_stream, safe="")

    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#logsV2:log-groups/log-group/{encoded_group}"
        f"/log-events/{encoded_stream}"
    )

def choose_webhook(log_group: str) -> Optional[str]:
    return WEBHOOK_MAP.get(log_group)

def choose_project_name(log_group: str) -> Optional[str]:
    return PROJECT_NAME_MAP.get(log_group)

def get_region(context: Any) -> str:
    try:
        arn = context.invoked_function_arn
        return arn.split(":")[3]
    except Exception:
        return DEFAULT_REGION

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    logger.debug("Raw event: %s", json.dumps(event))
    region = get_region(context)

    # CloudWatch Logs からの data 展開
    try:
        decoded_data = base64.b64decode(event["awslogs"]["data"])
        json_data = json.loads(gzip.decompress(decoded_data))
    except Exception:
        logger.exception("Failed to decode/decompress CloudWatch Logs event")
        return {"ok": False, "reason": "decode_error"}

    logger.debug("Decoded log payload: %s", json.dumps(json_data))

    log_events = json_data.get("logEvents") or []
    if not log_events:
        logger.warning("No logEvents found in payload")
        return {"ok": False, "reason": "no_log_events"}
    log_group = json_data.get("logGroup")
    if not log_group:
        logger.warning("No logGroup found in payload")
        return {"ok": False, "reason": "no_log_group"}
    log_stream = json_data.get("logStream")
    if not log_stream:
        logger.warning("No logStream found in payload")
        return {"ok": False, "reason": "no_log_stream"}

    hook_url = choose_webhook(log_group)
    if not hook_url:
        logger.warning(
            "No HOOK_URL configured for logGroup=%s. Notification skipped.", log_group
        )
        return {"ok": False, "reason": "no_webhook_for_log_group"}

    project_name = choose_project_name(log_group)
    if not project_name:
        logger.warning(
            "No PROJECT_NAME configured for logGroup=%s. Notification skipped.",
            log_group,
        )
        return {"ok": False, "reason": "no_project_name_for_log_group"}

    log_url = build_log_url(region, log_group, log_stream)

    messages = [e.get("message", "").strip() for e in log_events if e.get("message")]
    if not messages:
        logger.warning("No message field found in any logEvent")
        return {"ok": False, "reason": "no_messages"}

    error_message = "\n".join(messages[:MAX_LINES])

    # 本番運用では、個人情報や秘匿情報を含む場合はここでマスクすること
    logger.debug("Message to send (truncated): %s", error_message[:500])

    # メッセージ作成
    payload = {
        "log_url": log_url,
        "project_name": project_name,
        "text": error_message,
    }
    data = json.dumps(payload).encode("utf-8")

    # Webhook 送信
    request = urllib.request.Request(
        hook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="ignore")
            logger.info("Slack response: status=%s body=%s", status, body)

            if not (200 <= status < 300):
                logger.error("Slack returned non-2xx: status=%s body=%s", status, body)
                return {"ok": False, "reason": f"slack_status_{status}"}

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.error(
            "HTTPError when calling Slack: status=%s body=%s", e.code, body, exc_info=True
        )
        return {"ok": False, "reason": f"http_error_{e.code}"}

    except Exception:
        logger.exception("Unexpected error when calling Slack")
        return {"ok": False, "reason": "unexpected_error"}

    logger.info("Slack notification sent successfully")
    return {"ok": True}
