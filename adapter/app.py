import ast
import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
OPEA_URL = os.getenv(
    "OPEA_CHATQNA_URL",
    "http://chatqna-backend-server:8888/v1/chatqna",
)
MODEL = "opea-rag"


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{
            "id": MODEL,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "local",
        }],
    }


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    user_messages = [
        text_content(m.get("content"))
        for m in messages
        if m.get("role") == "user"
    ]
    if not user_messages or not user_messages[-1].strip():
        raise HTTPException(400, "A non-empty user message is required")

    # OPEA ChatQnA accepts a single query string.
    query = user_messages[-1]
    tokens = []

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                OPEA_URL,
                json={"messages": query},
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(
                        "utf-8", errors="replace"
                    )
                    raise HTTPException(502, f"OPEA returned {response.status_code}: {detail}")

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        value = ast.literal_eval(data)
                        token = (
                            value.decode("utf-8", errors="replace")
                            if isinstance(value, bytes)
                            else str(value)
                        )
                    except (ValueError, SyntaxError):
                        token = data
                    tokens.append(token)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Could not reach OPEA ChatQnA: {exc}") from exc

    answer = "".join(tokens)
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())

    if not body.get("stream", False):
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": MODEL,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }],
        }

    async def stream_response():
        def event(data):
            return "data: " + json.dumps(data) + "\n\n"

        yield event({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        })
        if answer:
            yield event({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": MODEL,
                "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}],
            })
        yield event({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")
