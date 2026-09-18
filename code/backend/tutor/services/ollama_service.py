import json
import logging
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)
ollama_runtime_lock = threading.Lock()


class OllamaServiceError(Exception):
    """Raised when the local Ollama service cannot generate a response."""


@dataclass
class OllamaGenerateResult:
    text: str
    latency_ms: int
    raw_response: dict


@dataclass
class OllamaStreamChunk:
    text: str
    done: bool
    raw_response: dict


def list_local_models() -> list[str]:
    _ensure_ollama_running()
    available_models = _fetch_available_models()
    return sorted(model_name for model_name in available_models if model_name)


def list_loaded_models() -> list[str]:
    """Return the names of models Ollama currently has resident in memory.

    Used for observability only — a fast best-effort call that swallows all
    errors so it never blocks the chat path.
    """
    ps_url = settings.OLLAMA_API_URL.replace("/api/generate", "/api/ps")
    try:
        with request.urlopen(request.Request(ps_url, method="GET"), timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]


def _tags_url() -> str:
    return settings.OLLAMA_API_URL.replace("/api/generate", "/api/tags")


def _resolve_ollama_command() -> str:
    configured_command = settings.OLLAMA_COMMAND
    resolved_command = shutil.which(configured_command) or configured_command
    if shutil.which(resolved_command) or resolved_command.endswith(".exe"):
        return resolved_command
    raise OllamaServiceError(
        f"Could not find the Ollama executable '{configured_command}' on PATH."
    )


def _is_ollama_api_running() -> bool:
    health_request = request.Request(_tags_url(), method="GET")
    try:
        with request.urlopen(
            health_request,
            timeout=2,
        ) as response:
            return response.status == 200
    except Exception:
        return False


def _wait_for_ollama_api() -> None:
    deadline = time.time() + settings.OLLAMA_STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _is_ollama_api_running():
            return
        time.sleep(0.5)

    raise OllamaServiceError(
        f"Ollama did not become ready within "
        f"{settings.OLLAMA_STARTUP_TIMEOUT_SECONDS} seconds."
    )


def _start_ollama_server() -> None:
    command = [_resolve_ollama_command(), "serve"]
    logger.info("Starting Ollama server with command: %s", command)

    creationflags = 0
    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }

    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

    if creationflags:
        popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True

    try:
        subprocess.Popen(command, **popen_kwargs)
    except Exception as exc:
        logger.exception("Failed to start Ollama server process: %s", exc)
        raise OllamaServiceError("Failed to start the Ollama server process.") from exc


def _ensure_ollama_running() -> None:
    if _is_ollama_api_running():
        return

    with ollama_runtime_lock:
        if _is_ollama_api_running():
            return

        _start_ollama_server()
        _wait_for_ollama_api()


def _fetch_available_models() -> set[str]:
    tags_request = request.Request(_tags_url(), method="GET")
    try:
        with request.urlopen(tags_request, timeout=settings.OLLAMA_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.exception("Failed to fetch Ollama model tags: %s", exc)
        raise OllamaServiceError("Could not fetch available Ollama models.") from exc

    return {model.get("name", "") for model in payload.get("models", [])}


def _model_is_available(model_name: str, available_models: set[str]) -> bool:
    return (
        model_name in available_models
        or f"{model_name}:latest" in available_models
        or any(name.split(":", 1)[0] == model_name for name in available_models)
    )


def _pull_model(model_name: str) -> None:
    command = [_resolve_ollama_command(), "pull", model_name]
    logger.info("Pulling Ollama model with command: %s", command)

    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.OLLAMA_MODEL_PULL_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Ollama model pull failed for %s with stderr: %s",
            model_name,
            exc.stderr,
        )
        raise OllamaServiceError(
            f"Failed to pull Ollama model '{model_name}': {exc.stderr}"
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Ollama model pull error for %s: %s", model_name, exc)
        raise OllamaServiceError(
            f"Unexpected error while pulling Ollama model '{model_name}'."
        ) from exc

    logger.info("Ollama model pull completed for %s: %s", model_name, completed_process.stdout)


def _ensure_model_available(model_name: str) -> None:
    available_models = _fetch_available_models()
    if _model_is_available(model_name, available_models):
        return

    with ollama_runtime_lock:
        available_models = _fetch_available_models()
        if _model_is_available(model_name, available_models):
            return

        _pull_model(model_name)


def generate_text(
    *, system_prompt: str, prompt: str, model_name: str | None = None
) -> OllamaGenerateResult:
    active_model = model_name or settings.OLLAMA_MODEL
    _ensure_ollama_running()
    _ensure_model_available(active_model)

    payload = {
        "model": active_model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }

    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        settings.OLLAMA_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.perf_counter()

    try:
        with request.urlopen(
            http_request,
            timeout=settings.OLLAMA_TIMEOUT_SECONDS,
        ) as response:
            raw_response = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception(
            "Ollama HTTP error from %s with status %s: %s",
            settings.OLLAMA_API_URL,
            exc.code,
            error_body,
        )
        raise OllamaServiceError(
            f"Ollama returned HTTP {exc.code}: {error_body}"
        ) from exc
    except error.URLError as exc:
        logger.exception(
            "Ollama connection error for %s: %s",
            settings.OLLAMA_API_URL,
            exc,
        )
        raise OllamaServiceError(
            f"Could not reach Ollama at {settings.OLLAMA_API_URL}"
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Ollama generation error: %s", exc)
        raise OllamaServiceError("Unexpected Ollama generation error") from exc

    measured_latency_ms = int((time.perf_counter() - start_time) * 1000)
    reported_latency_ms = int(raw_response.get("total_duration", 0) / 1_000_000)
    response_text = re.sub(r"<think>.*?</think>", "", raw_response.get("response", ""), flags=re.DOTALL).strip()

    return OllamaGenerateResult(
        text=response_text,
        latency_ms=reported_latency_ms or measured_latency_ms,
        raw_response=raw_response,
    )


def _iter_response_lines_with_idle_timeout(response, idle_timeout_seconds: float):
    """Yield raw lines from an Ollama streaming response, bounded by idle time.

    urllib's socket timeout is a per-recv timeout, not a per-line one. On a
    quiet-but-alive connection we can still block forever waiting for the next
    full line. This helper reads the response in a background thread and
    enforces a wall-clock gap between successive lines.
    """
    line_queue: "queue.Queue[bytes | BaseException | None]" = queue.Queue()

    def _pump():
        try:
            for raw_line in response:
                line_queue.put(raw_line)
            line_queue.put(None)
        except BaseException as exc:  # noqa: BLE001 — bubble to main thread
            line_queue.put(exc)

    pump_thread = threading.Thread(target=_pump, daemon=True)
    pump_thread.start()

    while True:
        try:
            item = line_queue.get(timeout=idle_timeout_seconds)
        except queue.Empty:
            raise OllamaServiceError(
                f"Ollama stream stalled: no chunk received in "
                f"{idle_timeout_seconds:.0f}s."
            )
        if item is None:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


def generate_text_stream(
    *, system_prompt: str, prompt: str, model_name: str | None = None
):
    active_model = model_name or settings.OLLAMA_MODEL
    _ensure_ollama_running()
    _ensure_model_available(active_model)

    payload = {
        "model": active_model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": True,
        # Keep the model resident in Ollama's memory so subsequent chat sends
        # don't pay the cold-load cost.
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }

    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        settings.OLLAMA_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    idle_timeout = float(settings.OLLAMA_STREAM_IDLE_TIMEOUT_SECONDS)
    total_timeout = float(settings.OLLAMA_STREAM_TOTAL_TIMEOUT_SECONDS)
    deadline = time.monotonic() + total_timeout

    try:
        response = request.urlopen(http_request, timeout=settings.OLLAMA_TIMEOUT_SECONDS)
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception(
            "Ollama HTTP stream error from %s with status %s: %s",
            settings.OLLAMA_API_URL,
            exc.code,
            error_body,
        )
        raise OllamaServiceError(
            f"Ollama returned HTTP {exc.code}: {error_body}"
        ) from exc
    except error.URLError as exc:
        logger.exception(
            "Ollama stream connection error for %s: %s",
            settings.OLLAMA_API_URL,
            exc,
        )
        raise OllamaServiceError(
            f"Could not reach Ollama at {settings.OLLAMA_API_URL}"
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Ollama stream connection error: %s", exc)
        raise OllamaServiceError("Unexpected Ollama stream connection error") from exc

    try:
        for raw_line in _iter_response_lines_with_idle_timeout(response, idle_timeout):
            if time.monotonic() > deadline:
                raise OllamaServiceError(
                    f"Ollama stream exceeded total timeout of {total_timeout:.0f}s."
                )
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            raw_response = json.loads(line)
            yield OllamaStreamChunk(
                text=raw_response.get("response", ""),
                done=bool(raw_response.get("done")),
                raw_response=raw_response,
            )
    except OllamaServiceError:
        raise
    except GeneratorExit:
        # Client disconnected; stop pulling from Ollama so it doesn't keep
        # generating into a closed socket.
        logger.info("Ollama stream consumer exited; closing upstream response.")
        raise
    except Exception as exc:
        logger.exception("Unexpected Ollama stream read error: %s", exc)
        raise OllamaServiceError("Unexpected Ollama stream read error") from exc
    finally:
        try:
            response.close()
        except Exception:
            pass
