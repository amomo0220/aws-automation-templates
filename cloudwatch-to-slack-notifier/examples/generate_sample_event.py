import json
import gzip
import base64
from pathlib import Path

# CloudWatch Logs が Lambda に渡す「展開後の JSON ペイロード」
payload = {
    "messageType": "DATA_MESSAGE",
    "owner": "123456789012",
    "logGroup": "/aws/lambda/sample-log-group",
    "logStream": "2025/01/01/[$LATEST]abcdef1234567890",
    "subscriptionFilters": ["MySubscriptionFilter"],
    "logEvents": [
        {
            "id": "1234567890",
            "timestamp": 1735689600000,
            "message": "ERROR: {'statusCode': 500, 'body': '{\"error\": \"Something failed\", \"message\": \"Application error\"}'}"
        },
        {
            "id": "0987654321",
            "timestamp": 1735689601000,
            "message": "INFO: 正常系のログ（この行はMAX_LINESによっては切り捨てられる）"
        }
    ]
}

def main() -> None:
    # 1. JSON にシリアライズ
    payload_bytes = json.dumps(payload).encode("utf-8")

    # 2. gzip 圧縮
    gz_bytes = gzip.compress(payload_bytes)

    # 3. base64 エンコード
    b64_str = base64.b64encode(gz_bytes).decode("ascii")

    event = {
        "awslogs": {
            "data": b64_str
        }
    }

    out_path = Path("sample_event.json")
    out_path.write_text(json.dumps(event), encoding="utf-8")
    print(f"written: {out_path.resolve()}")
    print("you can now load this JSON as the Lambda event for local testing.")

if __name__ == "__main__":
    main()
