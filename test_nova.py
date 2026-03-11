import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

response = client.converse(
    modelId="amazon.nova-2-lite-v1:0",
    messages=[
        {
            "role": "user",
            "content": [{"text": "Explain in one sentence what cloud cost optimization means."}]
        }
    ]
)

print(response["output"]["message"]["content"][0]["text"])
