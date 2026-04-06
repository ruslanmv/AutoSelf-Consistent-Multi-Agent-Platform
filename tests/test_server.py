#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import json
import sys
import traceback

from pydantic import BaseModel, Field

# Optional: load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# BeeAI imports
from beeai_framework.adapters.watsonx import WatsonxChatModel
from beeai_framework.backend import ChatModel, UserMessage
from beeai_framework.errors import AbortError, FrameworkError
from beeai_framework.utils import AbortSignal


def _env(var: str) -> str:
    """Read env var; return empty string if missing."""
    return os.getenv(var, "").strip()


def _mask(v: str, keep: int = 4) -> str:
    if not v:
        return ""
    return "*" * max(0, len(v) - keep) + v[-keep:]


def _credentials_from_env() -> dict:
    """Return dict with required credentials if available; empty if any missing."""
    api_key = _env("WATSONX_API_KEY")
    project_id = _env("PROJECT_ID")
    api_base = _env("WATSONX_URL")
    if api_key and project_id and api_base:
        return {
            "api_key": api_key,
            "project_id": project_id,
            "api_base": api_base,
        }
    return {}


async def _close_model(m):
    """Close a model client safely, regardless of whether it exposes aclose() or close()."""
    if m is None:
        return
    try:
        if hasattr(m, "aclose") and callable(getattr(m, "aclose")):
            await m.aclose()  # async close (aiohttp session)
        elif hasattr(m, "close") and callable(getattr(m, "close")):
            m.close()  # sync close
    except Exception:
        # Avoid raising during shutdown
        pass


# ========== LLM initialization ==========
# If env creds exist, build WatsonxChatModel with explicit settings.
# Otherwise, set llm=None; functions that need llm will gracefully skip/notify.
_creds = _credentials_from_env()
if _creds:
    print(
        "Initializing WatsonxChatModel with env credentials:\n"
        f"  WATSONX_API_KEY: {_mask(_creds['api_key'])}\n"
        f"  PROJECT_ID     : {_creds['project_id']}\n"
        f"  WATSONX_URL    : {_creds['api_base']}\n"
    )
    llm = WatsonxChatModel(
        model_id="ibm/granite-3-8b-instruct",
        settings={
            **_creds,
            "temperature": float(os.getenv("WATSONX_TEMPERATURE", "0.1")),
            "top_p": float(os.getenv("WATSONX_TOP_P", "0.9")),
        },
    )
else:
    print(
        "Watsonx credentials not found in environment (.env or OS env).\n"
        "  Required: WATSONX_API_KEY, PROJECT_ID, WATSONX_URL\n"
        "  Some demos that use ChatModel.from_name may still work if your environment is globally configured.\n"
    )
    llm = None


async def watsonx_from_name() -> None:
    """
    Uses the name-based factory (relies on environment/pre-configured provider).
    This path does NOT require explicit settings here.
    """
    watsonx_llm = ChatModel.from_name("watsonx:ibm/granite-3-8b-instruct")
    try:
        user_message = UserMessage("what states are part of New England?")
        response = await watsonx_llm.create(messages=[user_message])
        print(response.get_text_content())
    finally:
        await _close_model(watsonx_llm)


async def watsonx_sync() -> None:
    if llm is None:
        print("[watsonx_sync] Skipped: no env credentials; llm is not initialized.")
        return
    user_message = UserMessage("what is the capital of Massachusetts?")
    response = await llm.create(messages=[user_message])
    print(response.get_text_content())


async def watsonx_stream() -> None:
    if llm is None:
        print("[watsonx_stream] Skipped: no env credentials; llm is not initialized.")
        return
    user_message = UserMessage("How many islands make up the country of Cape Verde?")
    response = await llm.create(messages=[user_message], stream=True)
    print(response.get_text_content())


async def watsonx_images() -> None:
    # Image model via name-based factory (env/global config)
    image_llm = ChatModel.from_name("watsonx:meta-llama/llama-3-2-11b-vision-instruct")
    try:
        response = await image_llm.create(
            messages=[
                UserMessage("What is the dominant color in the picture?"),
                UserMessage.from_image(
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAHUlEQVR4nGI5Y6bFQApgIkn1qIZRDUNKAyAAAP//0ncBT3KcmKoAAAAASUVORK5CYII="
                ),
            ],
        )
        print(response.get_text_content())
    finally:
        await _close_model(image_llm)


async def watsonx_stream_abort() -> None:
    if llm is None:
        print("[watsonx_stream_abort] Skipped: no env credentials; llm is not initialized.")
        return
    user_message = UserMessage("What is the smallest of the Cape Verde islands?")
    try:
        response = await llm.create(
            messages=[user_message], stream=True, abort_signal=AbortSignal.timeout(0.5)
        )
        if response is not None:
            print(response.get_text_content())
        else:
            print("No response returned.")
    except AbortError as err:
        print(f"Aborted: {err}")


async def watson_structure() -> None:
    if llm is None:
        print("[watson_structure] Skipped: no env credentials; llm is not initialized.")
        return

    class TestSchema(BaseModel):
        answer: str = Field(description="your final answer")

    user_message = UserMessage("How many islands make up the country of Cape Verde?")
    response = await llm.create_structure(schema=TestSchema, messages=[user_message])
    print(response.object)


async def watsonx_debug() -> None:
    if llm is None:
        print("[watsonx_debug] Skipped: no env credentials; llm is not initialized.")
        return
    # Log every request (emitter callbacks)
    llm.emitter.match(
        "*",
        lambda data, event: print(
            f"Time: {event.created_at.time().isoformat()}",
            f"Event: {event.name}",
            f"Data: {str(data)[:90]}...",
        ),
    )
    response = await llm.create(messages=[UserMessage("Hello world!")])
    # Depending on framework version, accessing message text may differ:
    try:
        print(response.messages[0].to_plain())
    except Exception:
        print(json.dumps(response.messages[0].to_dict(), indent=2))


async def main() -> None:
    try:
        print("*" * 10, "watsonx_from_name")
        await watsonx_from_name()

        print("*" * 10, "watsonx_images")
        await watsonx_images()

        print("*" * 10, "watsonx_sync")
        await watsonx_sync()

        print("*" * 10, "watsonx_stream")
        await watsonx_stream()

        print("*" * 10, "watsonx_stream_abort")
        await watsonx_stream_abort()

        print("*" * 10, "watson_structure")
        await watson_structure()

        print("*" * 10, "watsonx_debug")
        await watsonx_debug()
    finally:
        # IMPORTANT: close the global model to release its aiohttp session/connector
        await _close_model(llm)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except FrameworkError as e:
        traceback.print_exc()
        sys.exit(e.explain())
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(130)
