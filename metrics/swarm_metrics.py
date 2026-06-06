from __future__ import annotations


def project_health(tasks: list[dict]) -> dict:
    total = len(tasks)
    done = sum(1 for task in tasks if task.get("status") == "done")
    failed = sum(1 for task in tasks if task.get("status") == "failed")
    running = sum(1 for task in tasks if task.get("status") == "running")
    health = round((done / total * 100) if total else 0)
    return {
        "total": total,
        "done": done,
        "failed": failed,
        "running": running,
        "health": health,
    }

