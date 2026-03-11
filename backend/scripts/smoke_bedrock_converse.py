from __future__ import annotations

import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    region = os.getenv("AWS_REGION", "us-east-1")
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
    connect_timeout = int(os.getenv("NOVA_CONNECT_TIMEOUT", "30"))
    read_timeout = int(os.getenv("NOVA_READ_TIMEOUT", "300"))

    config = Config(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )

    client = boto3.client("bedrock-runtime", region_name=region, config=config)

    try:
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Reply in one short sentence: Nova smoke test OK."}],
                }
            ],
            inferenceConfig={"maxTokens": 120, "temperature": 0.1, "topP": 0.9},
        )
        content = response.get("output", {}).get("message", {}).get("content", [])
        text_chunks = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        print("\n".join(text_chunks).strip())
    except Exception as exc:  # pragma: no cover - used for manual smoke run
        print(f"Smoke test failed: {exc.__class__.__name__}: {exc}")


if __name__ == "__main__":
    main()

