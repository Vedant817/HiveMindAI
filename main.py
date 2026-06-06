from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from orchestrator.swarm_runtime import SwarmRuntime
from shared.config import config_report


def create_app():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from api.routes import router

    app = FastAPI(title="HiveMindAI Agent Swarm", version="0.1.0")
    if router:
        app.include_router(router)
    static_dir = Path(__file__).parent / "api" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def dashboard():
        return FileResponse(static_dir / "index.html")

    return app


async def run_once(goal: str) -> dict:
    return await SwarmRuntime().run_goal(goal)


def main() -> None:
    parser = argparse.ArgumentParser(description="HiveMindAI autonomous agent swarm")
    parser.add_argument("goal", nargs="?", help="Run one local swarm goal")
    parser.add_argument("--serve", action="store_true", help="Start the FastAPI server")
    parser.add_argument("--check-config", action="store_true", help="Check production integration configuration")
    parser.add_argument("--check-local-config", action="store_true", help="Check local fallback configuration")
    parser.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.getenv("APP_PORT", "8000")), type=int)
    args = parser.parse_args()

    if args.check_config:
        report = config_report()
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["production_ready"] else 1)

    if args.check_local_config:
        report = config_report()
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["local_test_ready"] else 1)

    if args.serve:
        import uvicorn

        uvicorn.run("main:create_app", host=args.host, port=args.port, factory=True, reload=False)
        return

    goal = args.goal or os.getenv("SWARM_DEFAULT_GOAL")
    if not goal:
        raise SystemExit("Provide a goal argument or set SWARM_DEFAULT_GOAL.")
    result = asyncio.run(run_once(goal))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
