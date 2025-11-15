import json
import os
import sys
from pathlib import Path
from typing import Dict, Any
import urllib.request  # DRY RUN で monkey patch する

ENV_FILE = Path(__file__).with_name("local.env")
SAMPLE_EVENT = Path(__file__).parent.parent / "examples" / "sample_event.json"

class DummyContext:
    """
    Lambdaの context を最低限だけ偽装。
    リージョンは ARN から抜くので、ここを変えれば動作確認もできる。
    """
    invoked_function_arn = (
        "arn:aws:lambda:ap-northeast-1:123456789012:function:local-test"
    )

def load_local_env(env_path: Path) -> None:
    """
    KEY=VALUE 形式の簡易 env ファイルを読み込んで os.environ に反映する。
    # や空行は無視。
    """
    if not env_path.exists():
        raise FileNotFoundError(f"env file not found: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()

def mask_webhook(url: str) -> str:
    """
    Slack Webhook を丸出しにしたくないので、一部だけ見せる。
    """
    if not url:
        return ""
    if "hooks.slack.com" not in url:
        return "(non-slack url)"
    # 最後のパスの先頭だけ残してマスク
    parts = url.split("/")
    tail = parts[-1]
    return f".../{tail[:4]}***"

def print_env_summary() -> None:
    print("=== Local ENV summary ===")
    keys = sorted(k for k in os.environ.keys() if any(k.startswith(p) for p in ("HOOK_URL_", "PATH_", "PROJECT_NAME_")))
    for key in keys:
        val = os.environ.get(key, "")
        if key.startswith("HOOK_URL_"):
            val = mask_webhook(val)
        print(f"{key} = {val}")
    max_lines = os.environ.get("MAX_LINES", "(not set)")
    print(f"MAX_LINES = {max_lines}")
    print("=========================\n")

def load_sample_event(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"sample_event.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def enable_dry_run() -> None:
    """
    実際に Slack に投げたくないとき用。
    urllib.request.urlopen をモックする。
    """
    def fake_urlopen(request, *args, **kwargs):  # type: ignore[override]
        print("=== DRY RUN: urlopen called ===")
        print(f"URL: {request.full_url}")
        body = request.data.decode("utf-8") if request.data else ""
        print(f"BODY:\n{body}")
        print("=== /DRY RUN ===")

        class FakeResponse:
            def getcode(self) -> int:
                return 200

            def read(self) -> bytes:
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        return FakeResponse()

    urllib.request.urlopen = fake_urlopen  # type: ignore[assignment]

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # 1. env 読み込み
    load_local_env(ENV_FILE)

    # 2. (環境変数を読み込んでから)lambda_handler インポート
    from lambda_handler import lambda_handler

    if dry_run:
        enable_dry_run()

    # 3. 環境変数サマリ表示
    print_env_summary()

    # 4. sample_event.json 読み込み
    event = load_sample_event(SAMPLE_EVENT)

    # 5. Lambda 実行
    print("=== Invoke lambda_handler ===")
    result = lambda_handler(event, DummyContext())
    print("=== Result ===")
    print(result)

if __name__ == "__main__":
    main()
