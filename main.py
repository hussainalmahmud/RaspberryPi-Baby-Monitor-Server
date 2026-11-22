from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

APP_DIRECTORY = Path(__file__).resolve().parent
MEDIAMTX_WEBRTC_BASE = "http://127.0.0.1:8889"
MEDIAMTX_API_BASE = "http://127.0.0.1:9997"
WHEP_UPSTREAM_PREFIX = "/baby/whep"
WHEP_PUBLIC_PREFIX = "/live/whep"

FORWARD_REQUEST_HEADERS = {
    "authorization",
    "content-type",
    "if-match",
}

FORWARD_RESPONSE_HEADERS = {
    "accept-patch",
    "access-control-allow-headers",
    "access-control-allow-methods",
    "access-control-allow-origin",
    "access-control-expose-headers",
    "content-type",
    "etag",
    "id",
    "link",
    "location",
}


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as http_client:
        application.state.http_client = http_client
        yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIRECTORY / "static")), name="static")


def rewrite_whep_location(location_value: str) -> str:
    parsed_path = location_value
    if "://" in location_value:
        scheme_separator = location_value.find("://")
        path_start = location_value.find("/", scheme_separator + 3)
        if path_start == -1:
            return location_value.replace(WHEP_UPSTREAM_PREFIX, WHEP_PUBLIC_PREFIX, 1)
        parsed_path = location_value[path_start:]
    return parsed_path.replace(WHEP_UPSTREAM_PREFIX, WHEP_PUBLIC_PREFIX, 1)


async def proxy_whep(request: Request, session_id: str | None = None) -> Response:
    upstream_path = WHEP_UPSTREAM_PREFIX
    if session_id:
        upstream_path = f"{WHEP_UPSTREAM_PREFIX}/{session_id}"

    request_headers = {}
    for header_name, header_value in request.headers.items():
        if header_name.lower() in FORWARD_REQUEST_HEADERS:
            request_headers[header_name] = header_value

    request_body = await request.body()
    http_client: httpx.AsyncClient = request.app.state.http_client
    upstream_response = await http_client.request(
        request.method,
        f"{MEDIAMTX_WEBRTC_BASE}{upstream_path}",
        headers=request_headers,
        content=request_body if request_body else None,
    )

    response_headers = {}
    for header_name, header_value in upstream_response.headers.items():
        if header_name.lower() not in FORWARD_RESPONSE_HEADERS:
            continue
        if header_name.lower() == "location":
            response_headers["Location"] = rewrite_whep_location(header_value)
        else:
            response_headers[header_name] = header_value

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse(APP_DIRECTORY / "static" / "index.html")


@app.api_route("/live/whep", methods=["OPTIONS", "POST"])
async def whep_endpoint(request: Request):
    return await proxy_whep(request)


@app.api_route("/live/whep/{session_id}", methods=["PATCH", "DELETE"])
async def whep_session(request: Request, session_id: str):
    return await proxy_whep(request, session_id=session_id)


async def path_is_ready(http_client: httpx.AsyncClient, path_name: str) -> bool:
    try:
        path_response = await http_client.get(
            f"{MEDIAMTX_API_BASE}/v3/paths/get/{path_name}",
            timeout=2.0,
        )
    except httpx.HTTPError:
        return False
    if path_response.status_code != 200:
        return False
    try:
        path_info = path_response.json()
    except ValueError:
        return False
    return bool(path_info.get("ready"))


@app.get("/health")
async def health(request: Request):
    http_client: httpx.AsyncClient = request.app.state.http_client
    camera_ready = await path_is_ready(http_client, "cam")
    baby_stream_ready = await path_is_ready(http_client, "baby")
    mediamtx_reachable = camera_ready or baby_stream_ready
    if not mediamtx_reachable:
        try:
            api_response = await http_client.get(
                f"{MEDIAMTX_API_BASE}/v3/config/global/get",
                timeout=2.0,
            )
            mediamtx_reachable = api_response.status_code == 200
        except httpx.HTTPError:
            mediamtx_reachable = False

    return JSONResponse(
        {
            "ok": camera_ready and baby_stream_ready,
            "mediamtx": mediamtx_reachable,
            "camera": camera_ready,
            "stream": baby_stream_ready,
        }
    )
