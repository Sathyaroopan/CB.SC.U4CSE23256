import requests

LOG_URL = "http://20.207.122.201/evaluation-service/logs"
_token = None


def set_token(token):
    global _token
    _token = token


def Log(stack, level, package, message):
    payload = {
        "stack": stack,
        "level": level,
        "package": package,
        "message": message,
    }

    print(f"[{level.upper():5}] [{package}] {message}")

    if not _token:
        return None

    try:
        res = requests.post(
            LOG_URL,
            json=payload,
            headers={"Authorization": f"Bearer {_token}"},
            timeout=5,
        )
        return res.json() if res.ok else None
    except Exception:
        return None
