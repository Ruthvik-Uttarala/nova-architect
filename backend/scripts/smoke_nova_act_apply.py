from __future__ import annotations

import json
import urllib.error
import urllib.request


def main() -> None:
    url = "http://127.0.0.1:8000/apply"
    payload = {
        "actions": [
            "resize_instance",
            "enable_autoscaling",
            "enable_s3_encryption",
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            print(json.dumps(parsed, indent=2))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTPError {exc.code}: {body}")
    except Exception as exc:  # pragma: no cover - manual utility script
        print(f"Smoke test failed: {exc.__class__.__name__}: {exc}")


if __name__ == "__main__":
    main()

