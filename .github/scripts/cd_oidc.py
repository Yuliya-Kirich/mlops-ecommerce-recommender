import base64
import json
import os
import urllib.parse
import urllib.request

SA_ID = "ajenn401m64ev7mb36h0"
AUDIENCE = "https://github.com/Yuliya-Kirich"

EXPECTED_SUBJECTS = {
    "repo:Yuliya-Kirich@40795656/mlops-ecommerce-recommender@1459316444:ref:refs/heads/main",
}


def get_json(request):
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    print("=== Получаем GitHub OIDC token ===")

    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]

    separator = "&" if "?" in request_url else "?"
    url = request_url + separator + urllib.parse.urlencode({"audience": AUDIENCE})

    oidc_request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
    )

    oidc_token = get_json(oidc_request)["value"]

    payload = oidc_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)

    claims = json.loads(base64.urlsafe_b64decode(payload))

    if claims.get("aud") != AUDIENCE:
        raise RuntimeError("Unexpected OIDC audience")

    if claims.get("sub") not in EXPECTED_SUBJECTS:
        raise RuntimeError("Unexpected OIDC subject")

    print("SUCCESS: GitHub OIDC claims verified")

    print("=== Получаем Yandex IAM token ===")

    body = urllib.parse.urlencode(
        {
            "grant_type": ("urn:ietf:params:oauth:grant-type:token-exchange"),
            "requested_token_type": ("urn:ietf:params:oauth:token-type:access_token"),
            "audience": SA_ID,
            "subject_token": oidc_token,
            "subject_token_type": ("urn:ietf:params:oauth:token-type:id_token"),
        }
    ).encode()

    request = urllib.request.Request(
        "https://auth.yandex.cloud/oauth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    iam_token = get_json(request)["access_token"]

    # Маскируем токен в логах GitHub Actions.
    print(f"::add-mask::{iam_token}")

    github_env = os.environ.get("GITHUB_ENV")

    if not github_env:
        raise RuntimeError("GITHUB_ENV is not available")

    with open(github_env, "a", encoding="utf-8") as env_file:
        env_file.write(f"YC_IAM_TOKEN={iam_token}\n")

    print("SUCCESS: временный IAM-токен получен")


if __name__ == "__main__":
    main()
