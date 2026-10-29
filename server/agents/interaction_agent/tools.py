"""Tool definitions for interaction agent."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

from ...config import get_settings
from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import get_agent_roster, get_execution_agent_logs
from ...services.tasks.llm_retrieval import find_tasks_llm
from ...services.tasks.store import get_task_store
from ...services.tasks.transitions import KINDS
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

# Tool schemas for OpenRouter
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to a specific execution agent. Creates a new agent if the name doesn't exist in the roster, or reuses an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Human-readable agent name describing its purpose (e.g., 'Vercel Job Offer', 'Email to Sharanjeet'). This name will be used to identify and potentially reuse the agent."
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_name", "instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

# Only exposed under the redesign variant, where the roster is replaced by stored tasks
FIND_TASKS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_tasks",
        "description": "Search stored tasks (email threads, lookups) relevant to the user's message. Call this before starting new work, and for follow-ups like 'did Priya reply?'. Results are ranked; if several top results share a score but name different people, ask the user which one they mean.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Names and topics from the user's message."},
                "kind": {"type": "string", "enum": ["email_thread", "email_lookup", "other"], "description": "Optional filter."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

# Redesign variant: work is tracked as stored tasks instead of named, long-lived agents
SEND_TO_TASK_WORKER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_message_to_agent",
        "description": "Start a short-lived worker on a task. Pass task_id to continue an existing task (from find_tasks); otherwise a new task is created from kind and title.",
        "parameters": {
            "type": "object",
            "properties": {
                "instructions": {"type": "string", "description": "What the worker should do. Say what, not how."},
                "task_id": {"type": "integer", "description": "Continue this existing task."},
                "kind": {"type": "string", "enum": list(KINDS), "description": "New tasks only. email_thread: writing to, replying to or forwarding to a person. email_lookup: searching, summarizing or filtering emails. other: anything else."},
                "title": {"type": "string", "description": "New tasks only. One short line describing the task."},
            },
            "required": ["instructions"],
            "additionalProperties": False,
        },
    },
}

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()


# Create or continue a stored task and run an ephemeral worker on it (redesign variant)
def _send_to_task_worker(
    instructions: str, task_id: Optional[int] = None, kind: Optional[str] = None, title: Optional[str] = None
) -> ToolResult:
    store = get_task_store()
    if task_id is not None:
        task = store.get(task_id)
        if task is None:
            return ToolResult(success=False, payload={"error": f"No task with id {task_id}"})
        is_new = False
    else:
        if kind not in KINDS:
            return ToolResult(success=False, payload={"error": f"kind is required for a new task and must be one of {list(KINDS)}"})
        task = store.create(kind, summary=(title or instructions)[:200])
        is_new = True

    worker = f"task-{task.id}"  # label only; nothing persists on the worker
    logger.info(f"{'Created' if is_new else 'Continued'} task {task.id} ({task.kind})")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(worker, instructions, task_id=task.id)
            logger.info(f"Worker '{worker}' completed: {'SUCCESS' if result.success else 'FAILED'}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Worker '{worker}' failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return ToolResult(success=False, payload={"error": "No event loop available"})
    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={"status": "submitted", "agent_name": worker, "task_id": task.id, "new_task_created": is_new},
    )


# Create or reuse execution agent and dispatch instructions asynchronously
def send_message_to_agent(
    agent_name: Optional[str] = None,
    instructions: str = "",
    task_id: Optional[int] = None,
    kind: Optional[str] = None,
    title: Optional[str] = None,
) -> ToolResult:
    """Send instructions to an execution agent (or, under redesign, to a worker on a stored task)."""
    if get_settings().variant == "redesign":
        return _send_to_task_worker(instructions, task_id, kind, title)
    if not agent_name:
        return ToolResult(success=False, payload={"error": "agent_name is required"})
    roster = get_agent_roster()
    roster.load()
    existing_agents = set(roster.get_agents())
    is_new = agent_name not in existing_agents

    if is_new:
        roster.add_agent(agent_name)

    get_execution_agent_logs().record_request(agent_name, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_name, instructions)
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Agent '{agent_name}' completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{agent_name}' failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "agent_name": agent_name,
            "new_agent_created": is_new,
        },
    )


# Send immediate message to user and record in conversation history
def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log."""
    log = get_conversation_log()
    log.record_reply(message)

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
def send_draft(
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    message = f"To: {to}\nSubject: {subject}\n\n{body}"

    log.record_reply(message)
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
        },
        recorded_reply=True,
    )


# Look up stored tasks relevant to a message; flags ambiguity so the agent can ask the user
async def find_tasks_tool(query: str, kind: Optional[str] = None) -> ToolResult:
    """Return the best-matching stored tasks, best first (chosen by one cheap LLM call)."""
    results, ambiguous = await find_tasks_llm(get_task_store(), query, kind=kind, limit=5)
    if ambiguous is None:  # lexical fallback: ambiguous when the top results tie across different people
        top = results[0][1] if results else 0.0
        tied = [task for task, score in results if score == top] if top > 0 else []
        ambiguous = len(tied) > 1 and len({tuple(t.entities) for t in tied}) > 1
    return ToolResult(
        success=True,
        payload={
            "tasks": [
                {
                    "id": task.id, "kind": task.kind, "status": task.status, "entities": task.entities,
                    "summary": task.summary, "thread_id": task.thread_id, "updated_at": task.updated_at,
                    "score": round(score, 2),
                }
                for task, score in results
            ],
            "ambiguous": ambiguous,
        },
    )


# Record silent wait state to avoid duplicate responses
def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()
    
    # Record a dedicated wait entry so the UI knows to ignore it
    log.record_wait(reason)
    

    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas():
    """Return OpenAI-compatible tool schemas."""
    if get_settings().variant == "redesign":
        swapped = [SEND_TO_TASK_WORKER_SCHEMA if t["function"]["name"] == "send_message_to_agent" else t for t in TOOL_SCHEMAS]
        return [*swapped, FIND_TASKS_SCHEMA]
    return TOOL_SCHEMAS


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name == "send_message_to_agent":
            return send_message_to_agent(**args)
        if name == "send_message_to_user":
            return send_message_to_user(**args)
        if name == "send_draft":
            return send_draft(**args)
        if name == "wait":
            return wait(**args)
        if name == "find_tasks":
            return find_tasks_tool(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})
