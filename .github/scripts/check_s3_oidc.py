import json
import os
import urllib.parse
import urllib.request

SA_ID = "ajem0r259640ch1i8795"
AUDIENCE = "https://github.com/Yuliya-Kirich"

OBJECT_URL = (
    "https://storage.yandexcloud.net/"
    "mlops-yk-2026/mlops-ecommerce/"
    "ci-artifacts/split_v2/validation.parquet"
)


def get_json(request):
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    print("=== Получаем GitHub OIDC token ===")

    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]

    separator = "&" if "?" in request_url else "?"
    url = request_url + separator + urllib.parse.urlencode({
        "audience": AUDIENCE
    })

    oidc_request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
    )

    oidc_token = get_json(oidc_request)["value"]

    print("GitHub OIDC: OK")

    print("=== Получаем временный IAM token ===")

    payload = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requested_token_type":
            "urn:ietf:params:oauth:token-type:access_token",
        "audience": SA_ID,
        "subject_token": oidc_token,
        "subject_token_type":
            "urn:ietf:params:oauth:token-type:id_token",
    }).encode()

    iam_request = urllib.request.Request(
        "https://auth.yandex.cloud/oauth/token",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    iam_token = get_json(iam_request)["access_token"]

    print("Yandex IAM: OK")

    print("=== Проверяем чтение S3 ===")

    s3_request = urllib.request.Request(
        OBJECT_URL,
        headers={"Authorization": f"Bearer {iam_token}"},
        method="HEAD",
    )

    with urllib.request.urlopen(s3_request, timeout=30) as response:
        print("S3 HTTP:", response.status)
        print("Object size:", response.headers.get("Content-Length"))

    print("SUCCESS: GitHub OIDC -> Yandex IAM -> S3")


if __name__ == "__main__":
    main()
