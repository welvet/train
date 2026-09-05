from __future__ import annotations

from pathlib import Path

from aiohttp import web


PACKAGED_STATIC_ROOT = Path(__file__).with_name("static")


class StaticFileResolver:
    def __init__(self, root: Path = PACKAGED_STATIC_ROOT) -> None:
        self._root = root.resolve()

    async def handle(self, request: web.Request) -> web.StreamResponse:
        path = request.match_info["path"]
        resolved = self._resolve(path)
        if resolved is not None:
            return web.FileResponse(resolved)

        not_found = self._resolve("404.html")
        if not_found is not None:
            return web.FileResponse(not_found, status=404)
        raise web.HTTPNotFound()

    def _resolve(self, path: str) -> Path | None:
        relative = Path(path or "index.html")
        candidates = [relative]
        if path.endswith("/"):
            candidates.append(relative / "index.html")
        elif relative.suffix == "":
            candidates.extend((relative.with_suffix(".html"), relative / "index.html"))

        for candidate in candidates:
            try:
                resolved = (self._root / candidate).resolve()
            except (OSError, ValueError):
                continue
            if not resolved.is_relative_to(self._root):
                continue
            if resolved.is_file():
                return resolved
        return None
