import sys
sys.path.insert(0, ".")
import requests
from flask import Flask, jsonify
from logging_middleware.logger import Log, set_token

app = Flask(__name__)

BASE_URL = "http://20.207.122.201/evaluation-service"
TOKEN = {
    "token_type": "Bearer",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJNYXBDbGFpbXMiOnsiYXVkIjoiaHR0cDovLzIwLjI0NC41Ni4xNDQvZXZhbHVhdGlvbi1zZXJ2aWNlIiwiZW1haWwiOiJjYi5zYy51NGNzZTIzMjU2QGNiLnN0dWRlbnRzLmFtcml0YS5lZHUiLCJleHAiOjE3NzgwNjIwNjMsImlhdCI6MTc3ODA2MTE2MywiaXNzIjoiQWZmb3JkIE1lZGljYWwgVGVjaG5vbG9naWVzIFByaXZhdGUgTGltaXRlZCIsImp0aSI6IjQxMDQ5NmU3LWJlYzMtNGI2NS1iMmViLTJkNDA1ODY1YTIyMSIsImxvY2FsZSI6ImVuLUlOIiwibmFtZSI6InNhdGh5YSByb29wYW4gbSIsInN1YiI6IjRhZGY2OGM5LTdlYzItNDUzOC05MWIyLWQwNmFiMGVmMDBlYiJ9LCJlbWFpbCI6ImNiLnNjLnU0Y3NlMjMyNTZAY2Iuc3R1ZGVudHMuYW1yaXRhLmVkdSIsIm5hbWUiOiJzYXRoeWEgcm9vcGFuIG0iLCJyb2xsTm8iOiJjYi5zYy51NGNzZTIzMjU2IiwiYWNjZXNzQ29kZSI6IlBUQk1tUSIsImNsaWVudElEIjoiNGFkZjY4YzktN2VjMi00NTM4LTkxYjItZDA2YWIwZWYwMGViIiwiY2xpZW50U2VjcmV0IjoiQVFoZld3em15RnlLZ1hERiJ9.GhShfd4Eybz6i8Mrv_BjlnsSfi3Z8r3C7gL0daawGtU",
    "expires_in": 1778062063
}


def get_token():
    return TOKEN["access_token"] if isinstance(TOKEN, dict) else TOKEN


def knapsack(tasks, capacity):
    n = len(tasks)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        w, v = tasks[i - 1]["Duration"], tasks[i - 1]["Impact"]
        for c in range(capacity + 1):
            dp[i][c] = dp[i - 1][c]
            if w <= c:
                dp[i][c] = max(dp[i][c], dp[i - 1][c - w] + v)

    selected, c = [], capacity
    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:
            selected.append(tasks[i - 1])
            c -= tasks[i - 1]["Duration"]

    return selected[::-1], dp[n][capacity]


@app.route("/schedule")
def schedule():
    token = get_token()
    set_token(token)
    headers = {"Authorization": f"Bearer {token}"}
    Log("backend", "info", "service", "Schedule endpoint called")

    depots = requests.get(f"{BASE_URL}/depots", headers=headers).json()["depots"]
    vehicles = requests.get(f"{BASE_URL}/vehicles", headers=headers).json()["vehicles"]
    Log("backend", "info", "service", f"Fetched {len(depots)} depots, {len(vehicles)} tasks")

    results = []
    for depot in depots:
        cap = depot["MechanicHours"]
        selected, impact = knapsack(vehicles, cap)
        used = sum(t["Duration"] for t in selected)
        Log("backend", "info", "handler", f"Depot {depot['ID']}: {len(selected)} tasks, impact={impact}, used={used}/{cap}h")

        results.append({
            "depot_id": depot["ID"],
            "budget_hours": cap,
            "used_hours": used,
            "total_impact": impact,
            "tasks_selected": len(selected),
            "selected_tasks": selected
        })

    return jsonify({"depots": results})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
