import json
import logging
import os
import base64
import gzip
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
WEBHOOK_MAP = {
    f"{os.environ.get('PATH_1')}": os.environ.get("HOOK_URL_1"),
    # f"{os.environ.get('PATH_2')}": os.environ.get("HOOK_URL_2"),
}
PROJECT_NAME_MAP = {
    f"{os.environ.get('PATH_1')}": os.environ.get("PROJECT_NAME_1"),
    # f"{os.environ.get('PATH_2')}": os.environ.get("PROJECT_NAME_2"),

}
MAX_LINES = int(os.environ.get("MAX_LINES", "3"))

def build_log_url(region: str, log_group: str, log_stream: str) -> str:
    # CloudWatch Logs コンソールで、対象の logGroup/logStream を開く URL を作成
    encoded_group = urllib.parse.quote(log_group, safe='')
    encoded_stream = urllib.parse.quote(log_stream, safe='')

    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#logsV2:log-groups/log-group/{encoded_group}"
        f"/log-events/{encoded_stream}"
    )

def choose_webhook(log_group: str) -> Optional[str]:
    return WEBHOOK_MAP.get(log_group)

def choose_project_name(log_group: str) -> Optional[str]:
    return PROJECT_NAME_MAP.get(log_group)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    logger.info("Raw event: %s", json.dumps(event))  # まずは生イベントを出力

    # CloudWatch Logs からの data 展開
    try:
        # CloudWatchLogsからのデータはbase64エンコードされているのでデコード
        decoded_data = base64.b64decode(event['awslogs']['data'])
        json_data = json.loads(gzip.decompress(decoded_data))
    except Exception as e:
        logger.error("Failed to decode/decompress CloudWatch Logs event", exc_info=True)
        # ここで終わってしまうと原因が追えないので、event ごと残しておく
        return {"ok": False, "reason": "decode_error"}

    logger.debug("Decoded log payload: %s", json.dumps(json_data))

    log_events = json_data.get('logEvents', [])
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

    HOOK_URL = choose_webhook(log_group)
    if not HOOK_URL:
        logger.warning(
            "No HOOK_URL configured for logGroup=%s. Notification skipped.",
            log_group
        )
        return {"ok": False, "reason": "no_webhook_for_log_group"}
    PROJECT_NAME = choose_project_name(log_group)
    if not PROJECT_NAME:
        logger.warning(
            "No PROJECT_NAME configured for logGroup=%s. Notification skipped.",
            log_group
        )
        return {"ok": False, "reason": "no_project_name_for_log_group"}

    log_url = build_log_url(AWS_REGION, log_group, log_stream)

    raw_messages = [e.get('message', '').strip() for e in log_events if e.get('message')]
    if not raw_messages:
        logger.warning("No message field found in any logEvent")
        return {"ok": False, "reason": "no_messages"}
    # 長くなりすぎる場合は先頭数件に絞る
    error_message = "\n".join(raw_messages[:MAX_LINES])


    logger.info("Message to send: %s", error_message)

    # メッセージ作成
    send_data = {
        "log_url": log_url,
        "project_name": f"{PROJECT_NAME}" ,
        "text": f"{error_message}"
    }
    send_text = json.dumps(send_data)

    # Webhook 送信
    request = urllib.request.Request(
        HOOK_URL,
        data=send_text.encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(request) as response:
            status = response.getcode()
            response_body = response.read().decode('utf-8')
            logger.info("Slack response: status=%s body=%s", status, response_body)

            if status != 200:
                logger.error("Slack returned non-200: status=%s body=%s", status, response_body)
                return {"ok": False, "reason": "slack_status_error"}

            # body を JSON として見に行く
            try:
                resp_json = json.loads(response_body or "{}")
            except json.JSONDecodeError:
                # 古い "ok" 形式用のフォールバック
                if response_body.strip() != "ok":
                    logger.error("Slack returned unexpected body: %s", response_body)
                    return {"ok": False, "reason": "slack_body_error"}
            else:
                if not resp_json.get("ok", False):
                    logger.error("Slack returned ok=false: %s", response_body)
                    return {"ok": False, "reason": "slack_ok_false"}

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(
            "HTTPError when calling Slack: status=%s body=%s",
            e.code, body, exc_info=True
        )
        return {"ok": False, "reason": "http_error"}
        
    except Exception as e: 
        logger.error("Unexpected error when calling Slack", exc_info=True) 
        return {"ok": False, "reason": "unexpected_error"}
        
    logger.info("Slack notification sent successfully")
    return {"ok": True}
