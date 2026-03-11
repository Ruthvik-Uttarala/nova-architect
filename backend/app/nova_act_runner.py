from __future__ import annotations

import hashlib
import importlib
import os
from typing import Any, Dict, List

STARTING_PAGE = "http://127.0.0.1:3000/console"
DEFAULT_ACTIONS = ["resize_instance", "enable_autoscaling", "enable_s3_encryption"]

ACTION_PROMPTS = {
    "resize_instance": (
        "Stay only on localhost mock console. Click [data-testid='nav-ec2'], then "
        "[data-testid='btn-resize'], set [data-testid='select-instance-type'] to t3.medium, "
        "and click [data-testid='btn-save-ec2']."
    ),
    "enable_autoscaling": (
        "Stay only on localhost mock console. Click [data-testid='nav-autoscaling'], ensure "
        "[data-testid='toggle-autoscaling'] is enabled, set [data-testid='input-min']=2 and "
        "[data-testid='input-max']=6, then click [data-testid='btn-save-autoscaling']."
    ),
    "enable_s3_encryption": (
        "Stay only on localhost mock console. Click [data-testid='nav-s3'], ensure "
        "[data-testid='toggle-s3-encryption'] is enabled, then click [data-testid='btn-save-s3']."
    ),
}


def _normalize_actions(actions: List[str]) -> List[str]:
    normalized = []
    for action in actions:
        if isinstance(action, str):
            clean = action.strip()
            if clean:
                normalized.append(clean)
    return normalized


def _effective_actions(actions: List[str]) -> List[str]:
    normalized = _normalize_actions(actions)
    return normalized if normalized else DEFAULT_ACTIONS.copy()


def _run_id(actions: List[str]) -> str:
    digest = hashlib.sha1(",".join(actions).encode("utf-8")).hexdigest()[:10]
    return f"run_{digest}"


def _is_headless() -> bool:
    return os.getenv("NOVA_ACT_HEADLESS", "1").strip() != "0"


def _short_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    short = message[:80].replace(":", "-")
    return short or exc.__class__.__name__


def _load_nova_act_module() -> Any:
    try:
        return importlib.import_module("nova_act")
    except Exception as exc:
        raise RuntimeError(f"nova-act SDK unavailable ({exc.__class__.__name__})") from exc


def _new_client(module: Any, api_key: str, headless: bool) -> Any:
    nova_act_cls = getattr(module, "NovaAct", None)
    if not callable(nova_act_cls):
        raise RuntimeError("nova-act SDK does not expose NovaAct class")

    os.environ.setdefault("NOVA_ACT_API_KEY", api_key)

    init_attempts = [
        {
            "api_key": api_key,
            "model_id": "nova-act-latest",
            "starting_page": STARTING_PAGE,
            "headless": headless,
        },
        {"api_key": api_key, "starting_page": STARTING_PAGE, "headless": headless},
        {"model_id": "nova-act-latest", "starting_page": STARTING_PAGE, "headless": headless},
        {"starting_page": STARTING_PAGE, "headless": headless},
        {"starting_page": STARTING_PAGE},
        {},
    ]
    for kwargs in init_attempts:
        try:
            return nova_act_cls(**kwargs)
        except TypeError:
            continue

    workflow_cls = getattr(module, "Workflow", None)
    if callable(workflow_cls):
        workflow = None
        for wf_kwargs in [{"model_id": "nova-act-latest"}, {}]:
            try:
                workflow = workflow_cls(**wf_kwargs)
                break
            except TypeError:
                continue
            except Exception:
                break

        for kwargs in [
            {"api_key": api_key, "workflow": workflow, "starting_page": STARTING_PAGE, "headless": headless},
            {"workflow": workflow, "starting_page": STARTING_PAGE, "headless": headless},
            {"workflow": workflow},
        ]:
            try:
                return nova_act_cls(**kwargs)
            except TypeError:
                continue

    raise RuntimeError("Unable to initialize NovaAct client with available SDK signatures")


def _send_prompt(client: Any, prompt: str) -> None:
    methods = ["act", "run", "execute", "step", "prompt"]
    for name in methods:
        func = getattr(client, name, None)
        if not callable(func):
            continue

        for kwargs in ({"instruction": prompt}, {"prompt": prompt}, {"task": prompt}):
            try:
                func(**kwargs)
                return
            except TypeError:
                continue

        try:
            func(prompt)
            return
        except TypeError:
            continue
    raise RuntimeError("No supported NovaAct execution method found")


def _close_client(client: Any, context_manager: Any) -> None:
    if context_manager is not None:
        try:
            context_manager.__exit__(None, None, None)
        except Exception:
            pass
        return

    for method_name in ("close", "quit", "shutdown"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                method()
            except Exception:
                pass
            return


def run_apply(actions: List[str]) -> Dict[str, Any]:
    effective_actions = _effective_actions(actions)
    run_id = _run_id(effective_actions)
    steps: List[Dict[str, Any]] = []

    known_actions = [action for action in effective_actions if action in ACTION_PROMPTS]
    unknown_actions = [action for action in effective_actions if action not in ACTION_PROMPTS]

    if not known_actions:
        steps.append({"step": 1, "action": "open_console", "result": "skipped:no_known_actions_requested"})
        for idx, action in enumerate(effective_actions, start=2):
            steps.append({"step": idx, "action": action, "result": "skipped:unknown_action"})
        return {
            "run_id": run_id,
            "status": "failed",
            "steps": steps,
            "notes": "No executable known actions were provided.",
        }

    success_count = 0
    open_ok = False
    client: Any = None
    context_manager: Any = None

    try:
        module = _load_nova_act_module()
        client = _new_client(module, os.getenv("NOVA_ACT_API_KEY", ""), _is_headless())

        if hasattr(client, "__enter__") and hasattr(client, "__exit__"):
            context_manager = client
            client = context_manager.__enter__()

        _send_prompt(
            client,
            "Open the starting page and confirm [data-testid='nav-ec2'] exists. Stay on localhost only.",
        )
        steps.append({"step": 1, "action": "open_console", "result": "ok"})
        open_ok = True

        step_index = 2
        for action in effective_actions:
            if action not in ACTION_PROMPTS:
                steps.append({"step": step_index, "action": action, "result": "skipped:unknown_action"})
                step_index += 1
                continue

            if not open_ok:
                steps.append({"step": step_index, "action": action, "result": "error:console_not_open"})
                step_index += 1
                continue

            try:
                _send_prompt(client, ACTION_PROMPTS[action])
                steps.append({"step": step_index, "action": action, "result": "ok"})
                success_count += 1
            except Exception as exc:
                steps.append({"step": step_index, "action": action, "result": f"error:{_short_error(exc)}"})
            step_index += 1

    except Exception as exc:
        if not steps:
            steps.append({"step": 1, "action": "open_console", "result": f"error:{_short_error(exc)}"})
        else:
            steps[0]["result"] = f"error:{_short_error(exc)}"
    finally:
        if client is not None:
            _close_client(client, context_manager)

    if success_count == len(known_actions) and len(unknown_actions) == 0:
        status = "success"
        notes = "Nova Act automation completed all requested actions on mock console."
    elif success_count > 0:
        status = "partial"
        notes = "Nova Act automation completed some actions; see step results for failures/skips."
    else:
        status = "failed"
        notes = "Nova Act automation did not complete any known actions."

    return {
        "run_id": run_id,
        "status": status,
        "steps": steps,
        "notes": notes,
    }

