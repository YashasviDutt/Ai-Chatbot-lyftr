import uuid


def sid():
    return "s-" + uuid.uuid4().hex[:8]


def post(client, session_id, message, headers=None, **extra):
    return client.post("/chat", json={"session_id": session_id, "message": message, **extra}, headers=headers or {})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_chat_live_then_cache_in_new_session(client):
    msg = "unique question " + uuid.uuid4().hex
    a = post(client, sid(), msg).json()
    b = post(client, sid(), msg).json()
    assert a["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert a["metadata"]["key_id"] == "key_1"
    assert b["metadata"]["resolution_source"] == "LLM_CACHE"
    assert b["metadata"]["key_id"] is None
    assert b["metadata"]["fallback_attempts"] == 0
    assert a["reply"] == b["reply"]
    assert a["metadata"]["input_tokens"] == b["metadata"]["input_tokens"]
    assert isinstance(a["metadata"]["latency_ms"], int)


def test_different_message_not_cached(client):
    post(client, sid(), "hello " + uuid.uuid4().hex)
    r = post(client, sid(), "another " + uuid.uuid4().hex).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_multi_turn_history_and_isolation(client):
    s1, s2 = sid(), sid()
    post(client, s1, "first " + uuid.uuid4().hex)
    r2 = post(client, s1, "second " + uuid.uuid4().hex).json()
    h = client.get(f"/sessions/{s1}/messages").json()
    assert [m["role"] for m in h["messages"]] == ["user", "assistant", "user", "assistant"]
    assert "metadata" in h["messages"][1] and "metadata" not in h["messages"][0]
    assert h["messages"][3]["content"] == r2["reply"]
    post(client, s2, "other " + uuid.uuid4().hex)
    assert len(client.get(f"/sessions/{s2}/messages").json()["messages"]) == 2


def test_failover_key1_429_and_500(client):
    for h in ("key_1=429", "key_1=500"):
        r = post(client, sid(), "f " + uuid.uuid4().hex, {"X-Simulate-Failure": h})
        assert r.status_code == 200
        assert r.json()["metadata"]["key_id"] == "key_2"
        assert r.json()["metadata"]["fallback_attempts"] == 1


def test_all_keys_fail_503_and_not_stored(client):
    s = sid()
    r = post(client, s, "x " + uuid.uuid4().hex, {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert client.get(f"/sessions/{s}/messages").status_code == 404


def test_validation_errors(client):
    assert post(client, sid(), "   ").status_code == 422
    assert post(client, sid(), "a" * 4001).status_code == 422
    assert post(client, "", "hi").status_code == 422
    assert client.post("/chat", content="{bad json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/chat", json={"session_id": "x"}).status_code == 422


def test_unknown_session_404(client):
    r = client.get("/sessions/nope-" + uuid.uuid4().hex + "/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


def test_system_prompt_accepted(client):
    r = post(client, sid(), "sp " + uuid.uuid4().hex, system_prompt="Talk like a pirate")
    assert r.status_code == 200
