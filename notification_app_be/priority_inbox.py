import sys
sys.path.insert(0, ".")
import requests
import heapq
from datetime import datetime
from flask import Flask, jsonify
from logging_middleware.logger import Log, set_token

app = Flask(__name__)

BASE_URL = "http://20.207.122.201/evaluation-service"
TOKEN = {
    "token_type": "Bearer",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJNYXBDbGFpbXMiOnsiYXVkIjoiaHR0cDovLzIwLjI0NC41Ni4xNDQvZXZhbHVhdGlvbi1zZXJ2aWNlIiwiZW1haWwiOiJjYi5zYy51NGNzZTIzMjU2QGNiLnN0dWRlbnRzLmFtcml0YS5lZHUiLCJleHAiOjE3NzgwNjIwNjMsImlhdCI6MTc3ODA2MTE2MywiaXNzIjoiQWZmb3JkIE1lZGljYWwgVGVjaG5vbG9naWVzIFByaXZhdGUgTGltaXRlZCIsImp0aSI6IjQxMDQ5NmU3LWJlYzMtNGI2NS1iMmViLTJkNDA1ODY1YTIyMSIsImxvY2FsZSI6ImVuLUlOIiwibmFtZSI6InNhdGh5YSByb29wYW4gbSIsInN1YiI6IjRhZGY2OGM5LTdlYzItNDUzOC05MWIyLWQwNmFiMGVmMDBlYiJ9LCJlbWFpbCI6ImNiLnNjLnU0Y3NlMjMyNTZAY2Iuc3R1ZGVudHMuYW1yaXRhLmVkdSIsIm5hbWUiOiJzYXRoeWEgcm9vcGFuIG0iLCJyb2xsTm8iOiJjYi5zYy51NGNzZTIzMjU2IiwiYWNjZXNzQ29kZSI6IlBUQk1tUSIsImNsaWVudElEIjoiNGFkZjY4YzktN2VjMi00NTM4LTkxYjItZDA2YWIwZWYwMGViIiwiY2xpZW50U2VjcmV0IjoiQVFoZld3em15RnlLZ1hERiJ9.GhShfd4Eybz6i8Mrv_BjlnsSfi3Z8r3C7gL0daawGtU",
    "expires_in": 1778062063
}

TYPE_WEIGHT = {"Placement": 3, "Result": 2, "Event": 1}


def get_token():
    return TOKEN["access_token"] if isinstance(TOKEN, dict) else TOKEN


def get_top_n(notifications, n=10):
    heap = []
    for notif in notifications:
        weight = TYPE_WEIGHT.get(notif["Type"], 0)
        recency = datetime.strptime(notif["Timestamp"], "%Y-%m-%d %H:%M:%S").timestamp()
        score = (weight, recency)
        entry = (score, notif["ID"], notif)

        if len(heap) < n:
            heapq.heappush(heap, entry)
        elif score > heap[0][0]:
            heapq.heapreplace(heap, entry)

    result = []
    while heap:
        score, _, notif = heapq.heappop(heap)
        result.append(notif)
    return result[::-1]


@app.route("/priority-inbox")
def priority_inbox():
    token = get_token()
    set_token(token)
    headers = {"Authorization": f"Bearer {token}"}
    Log("backend", "info", "service", "Priority Inbox endpoint called")

    notifications = requests.get(f"{BASE_URL}/notifications", headers=headers).json()["notifications"]
    Log("backend", "info", "service", f"Fetched {len(notifications)} notifications")

    top = get_top_n(notifications, n=10)
    Log("backend", "info", "handler", f"Computed top {len(top)} priority notifications")

    return jsonify({"top_notifications": top, "count": len(top)})


if __name__ == "__main__":
    app.run(port=5001, debug=True)
