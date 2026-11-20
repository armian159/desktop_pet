"""Conversation state and the background request to Ollama."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, Signal

from .config import Config

MSG_OFFLINE = "Ollama가 꺼져 있는 것 같아요. 먼저 실행해 주세요."
MSG_NO_MODEL = "'{model}' 모델을 찾을 수 없어요."
MSG_BROKEN = "답을 받다가 연결이 끊겼어요. 다시 말해 주세요."
MSG_SERVER = "Ollama가 오류를 돌려줬어요: {detail}"
TIMEOUT = 180  # s; the first reply waits for the model to load into memory


class ChatError(Exception):
    """str(error) is Korean text meant to be shown to the user as is."""


def parse_stream_line(line: bytes) -> tuple[str, bool]:
    """One NDJSON line from /api/chat -> (text to append, whether it is the last)."""
    if not line.strip():
        return "", False
    try:
        data = json.loads(line)
    except ValueError as error:
        raise ChatError(MSG_BROKEN) from error
    if not isinstance(data, dict):
        raise ChatError(MSG_BROKEN)
    if "error" in data:
        raise ChatError(MSG_SERVER.format(detail=data["error"]))
    message = data.get("message") or {}
    return str(message.get("content") or ""), bool(data.get("done"))


class ChatSession:
    """History plus the one in-flight turn. A turn is recorded only if it succeeds."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self.history: list[dict] = []
        self._pending: str | None = None
        self._monologue: dict | None = None

    @property
    def busy(self) -> bool:
        return self._pending is not None

    def begin(self, user_text: str) -> dict | None:
        text = user_text.strip()
        if self.busy or not text:
            return None
        self._pending = text
        return self.payload([{"role": "user", "content": text}])

    def payload(self, tail: list[dict]) -> dict:
        recent = self.history[-2 * self._cfg.history_turns :]
        return {
            "model": self._cfg.model,
            "messages": recent + tail,
            "stream": True,
            "think": False,
            "keep_alive": self._cfg.keep_alive,
        }

    def succeed(self, reply: str) -> None:
        pending, self._pending = self._pending, None
        if pending is None or not reply.strip():
            return
        self.history.append({"role": "user", "content": pending})
        self.history.append({"role": "assistant", "content": reply})

    def fail(self) -> None:
        self._pending = None

    def add_monologue(self, text: str) -> None:
        """Record something the pet said unprompted; only the latest one is kept."""
        if not text.strip():
            return
        if self._monologue is not None:
            self.history[:] = [m for m in self.history if m is not self._monologue]
        self._monologue = {"role": "assistant", "content": text}
        self.history.append(self._monologue)

    def reset(self) -> None:
        self.history.clear()
        self._pending = None
        self._monologue = None


class ChatWorker(QThread):
    """Streams one reply. Emits exactly one of `done` / `failed`, once."""

    delta = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, payload: dict, model: str) -> None:
        super().__init__()
        self._url = url.rstrip("/") + "/api/chat"
        self._payload = payload
        self._model = model

    def run(self) -> None:
        try:
            reply = self._stream()
        except ChatError as error:
            self.failed.emit(str(error))
        except Exception:  # anything else is still "the reply did not arrive"
            self.failed.emit(MSG_BROKEN)
        else:
            self.done.emit(reply)

    def _stream(self) -> str:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(self._payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        # Ollama is local; never route it through a system proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise ChatError(MSG_NO_MODEL.format(model=self._model)) from error
            raise ChatError(MSG_SERVER.format(detail=error.code)) from error
        except (urllib.error.URLError, OSError) as error:
            raise ChatError(MSG_OFFLINE) from error
        parts: list[str] = []
        with response:
            for line in response:
                if self.isInterruptionRequested():
                    raise ChatError(MSG_BROKEN)
                text, finished = parse_stream_line(line)
                if text:
                    parts.append(text)
                    self.delta.emit(text)
                if finished:
                    return "".join(parts)
        raise ChatError(MSG_BROKEN)
