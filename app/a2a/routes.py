"""A2A v0.3 JSON-RPC + discovery routes for FastAPI.

Mounts:
  - ``POST /`` — JSON-RPC 2.0 (message/send, message/stream, tasks/get,
    tasks/cancel, tasks/resubscribe)
  - ``GET /.well-known/agent-card.json`` — A2A standard discovery path

The AgentCard is served as the proto-compatible JSON form (the same shape
A2ACardResolver parses).
"""

from __future__ import annotations

from typing import Any

from a2a.server.request_handlers.default_request_handler_v2 import (
    DefaultRequestHandlerV2,
)
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.a2a.executor import OldmanAgentExecutor


def build_a2a_routes(
    executor: OldmanAgentExecutor,
    agent_card_proto: Any,
    agent_card_dict: dict[str, Any],
) -> list[Route]:
    """Construct Starlette routes for JSON-RPC + ``/.well-known/agent-card.json``.

    Args:
        executor: OldmanAgentExecutor instance.
        agent_card_proto: proto AgentCard (``a2a.types.a2a_pb2.AgentCard``)
            passed to the SDK request handler.
        agent_card_dict: the JSON-serializable dict served at well-known path.
    """
    handler = DefaultRequestHandlerV2(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card_proto,
    )
    # enable_v0_3_compat=True registers JSON-RPC method names per A2A v0.3
    # spec: message/send, message/stream, tasks/get, tasks/cancel, tasks/resubscribe
    jsonrpc_routes = create_jsonrpc_routes(
        handler, rpc_url="/", enable_v0_3_compat=True
    )

    async def well_known(request: Request) -> JSONResponse:
        return JSONResponse(agent_card_dict)

    well_known_route = Route(
        "/.well-known/agent-card.json",
        endpoint=well_known,
        methods=["GET"],
    )
    return [*jsonrpc_routes, well_known_route]
