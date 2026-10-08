#!/usr/bin/env python3
"""Driver cho Derma core (FastAPI + agent worker) — chỉ dùng stdlib.

  driver.py health
  driver.py models
  driver.py chat "<câu hỏi>" [--model ID] [--user user-1] [--timeout 120]
  driver.py send <conversationId> "<tin nhắn>" [--timeout 120]
  driver.py answer <conversationId> <questionId> <optionId> "<label>"
  driver.py messages <conversationId>

Đọc BASE_URL (mặc định http://localhost:3050) và APP_ACCESS_TOKEN (env, hoặc `.env` ở cwd).
`chat`/`send` mở SSE `GET /conversations/{id}/stream` — bước này mới đẩy turn cho worker —
rồi in từng event; message.delta được gộp lại thành 1 dòng cuối. Thoát 0 nếu turn kết thúc
bằng message.done + [DONE], 2 nếu lỗi/timeout, 3 nếu agent dừng hỏi lại (message.question).
"""
import json, os, sys, time, uuid, urllib.request, urllib.error

BASE = os.environ.get("BASE_URL", "http://localhost:3050").rstrip("/") + "/api/v1"


def _token() -> str:
    t = os.environ.get("APP_ACCESS_TOKEN")
    if t is not None:
        return t
    try:
        for line in open(".env"):
            if line.startswith("APP_ACCESS_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def _req(method, path, body=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if _token():
        headers["Authorization"] = f"Bearer {_token()}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        return urllib.request.urlopen(r, timeout=timeout)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {method} {path}: {e.read().decode()[:500]}")


def _json(method, path, body=None):
    with _req(method, path, body) as resp:
        return json.load(resp)


def stream(conv_id, timeout):
    deadline = time.time() + timeout
    deltas, code = [], 2
    with _req("GET", f"/conversations/{conv_id}/stream", timeout=timeout) as resp:
        for raw in resp:
            if time.time() > deadline:
                print("!! timeout"); break
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                print("[DONE]"); break
            ev = json.loads(data)
            t = ev.get("type")
            if t == "message.delta":
                deltas.append(ev.get("delta", "")); continue
            print(json.dumps(ev, ensure_ascii=False)[:300])
            if t in ("message.done", "message.completed"): code = 0
            if t == "message.question": code = 3
            if t in ("message.error", "error"): code = 2
    if deltas:
        print("ANSWER:", "".join(deltas))
    return code


def main(a):
    if not a:
        sys.exit(__doc__)
    cmd, rest = a[0], a[1:]
    opt = {}
    while "--model" in rest or "--user" in rest or "--timeout" in rest:
        for k in ("--model", "--user", "--timeout"):
            if k in rest:
                i = rest.index(k); opt[k] = rest[i + 1]; del rest[i:i + 2]
    tmo = int(opt.get("--timeout", 120))
    if cmd == "health":
        with urllib.request.urlopen(BASE + "/health/ready", timeout=10) as r:
            print(r.read().decode())
    elif cmd == "models":
        print(json.dumps(_json("GET", "/models"), ensure_ascii=False))
    elif cmd == "chat":
        body = {"userId": opt.get("--user", "user-1"), "initMessage": rest[0]}
        if "--model" in opt: body["model"] = opt["--model"]
        conv = _json("POST", "/conversations", body)["data"]
        print("conversationId:", conv["id"], "model:", conv["model"])
        sys.exit(stream(conv["id"], tmo))
    elif cmd == "send":
        res = _json("POST", f"/conversations/{rest[0]}/messages",
                    {"clientMessageId": str(uuid.uuid4()), "content": rest[1]})["data"]
        print("assistantMessageId:", res["assistantMessage"]["id"])
        sys.exit(stream(rest[0], tmo))
    elif cmd == "answer":
        cid, qid, oid, label = rest[:4]
        _json("POST", f"/conversations/{cid}/questions/{qid}/answer",
              {"questionId": qid, "optionId": oid, "label": label})
        sys.exit(stream(cid, tmo))
    elif cmd == "messages":
        for m in _json("GET", f"/conversations/{rest[0]}/messages")["data"]:
            print(m["role"], m.get("status"), (m.get("content") or "")[:200].replace("\n", " "))
    else:
        sys.exit(__doc__)


main(sys.argv[1:])
