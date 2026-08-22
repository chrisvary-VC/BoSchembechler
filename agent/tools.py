"""The five tools. Each one speaks a headline AND publishes a render event.

Both outputs come from the same call, which is why the screen and the voice
land together.
"""

from __future__ import annotations

import logging

from livekit.agents import RunContext, function_tool

import aios_data as data
import lifestyle
import operations
import productivity
import render

logger = logging.getLogger("aios.tools")


@function_tool
async def respond_conversationally(context: RunContext, message: str) -> str:
    """Respond to greetings, thanks, farewells, and casual conversation.

    Args:
        message: A short, natural JARVIS-style response to speak.
    """
    await context.session.say(message, allow_interruptions=False)
    return "The conversational response was already spoken. Do not repeat it."


@function_tool
async def get_daily_brief(context: RunContext) -> str:
    """The user's rundown for today: headline, signals, and what needs them.

    Use for 'brief me', 'what's going on', 'catch me up'.
    """
    return await deliver_daily_brief(context.session)


async def deliver_daily_brief(session) -> str:
    """Publish and speak the brief; callable by both routing and the LLM tool."""
    # Put the correct panel on screen before the synchronous Google requests
    # finish, so a live brief never looks like a missed command.
    await render.publish(render.build_event(
        type=render.BRIEF,
        tool="get_daily_brief",
        spoken="Pulling your live brief.",
        title="Daily Brief · updating",
        payload={
            "summary": "Pulling your calendar and recent email…",
            "signals": [],
            "sections": [],
        },
    ))
    d = data.get_brief()
    signals = d.get("signals", [])
    loud = next((s for s in signals if s.get("alert")), None)
    spoken = d.get("spoken") or (
        f"Brief's up. {len(d.get('sections', []))} things want you today"
        + (f", and {loud['label']} is the loud one." if loud else ".")
    )
    result = await render.render(
        type=render.BRIEF,
        tool="get_daily_brief",
        spoken=spoken,
        title=d.get("title", "Daily Brief"),
        payload={
            "summary": d.get("summary", ""),
            "signals": signals,
            "sections": d.get("sections", []),
        },
    )
    await session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def query_metrics(
    context: RunContext, metric: str = "active_users", days: int = 30
) -> str:
    """Trend for a channel or business metric over time.

    Args:
        metric: active_users, users, sessions, views, pageviews, or engagement.
        days: how many days back to chart. Default 30.
    """
    d = data.get_metrics(metric, days)
    direction = "up" if d["delta_pct"] >= 0 else "down"
    spoken = (
        f"{d['metric']} are {direction} {abs(d['delta_pct'])} percent "
        f"over {len(d['points'])} days. Curve's on screen."
    )
    result = await render.render(
        type=render.METRICS,
        tool="query_metrics",
        spoken=spoken,
        title=f"{d['metric']} · last {len(d['points'])} days",
        payload=d,
    )
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def get_pipeline(context: RunContext) -> str:
    """Deal pipeline by stage, including anything at risk.

    Use for 'what's in my pipeline', 'what's at risk', 'how's revenue looking'.
    """
    d = data.get_pipeline()
    deals = d.get("deals", [])
    at_risk = [x for x in deals if x.get("at_risk")]
    total = sum(x.get("value", 0) for x in deals)
    spoken = f"{len(deals)} deals, {total:,} dollars in play." + (
        f" {at_risk[0]['name']} is the one bleeding — it's red on screen."
        if at_risk else " Nothing's on fire."
    )
    result = await render.render(
        type=render.PIPELINE,
        tool="get_pipeline",
        spoken=spoken,
        title=d.get("title", "Pipeline"),
        payload={"stages": d.get("stages", []), "deals": deals},
    )
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def search_intel(context: RunContext, query: str) -> str:
    """What was said about a topic, person, or deal across meetings and messages.

    Args:
        query: the topic, name, or deal to search for.
    """
    d = data.search_intel(query)
    items = d.get("items", [])
    if not items:
        spoken = f"Nothing on {query}. Want me to look somewhere else?"
    else:
        spoken = (
            f"{len(items)} mentions of {query}. "
            f"Most recent was {items[0].get('who', 'someone')}, "
            f"{items[0].get('when', 'recently')}. It's on the timeline."
        )
    result = await render.render(
        type=render.INTEL,
        tool="search_intel",
        spoken=spoken,
        title=f'"{query}" · mentions',
        payload=d,
    )
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def get_recent_emails(
    context: RunContext, hours: int = 3, unread_only: bool = False, topic: str = ""
) -> str:
    """Show email received within an exact recent time window.

    Use for requests such as "my emails from the last three hours", "recent
    email", or "unread mail since this morning".

    Args:
        hours: Rolling number of hours to look back. Use 3 when the user says three hours.
        unread_only: True only when the user explicitly asks for unread email.
        topic: Optional sender, subject, or Gmail search phrase; leave empty for all recent inbox mail.
    """
    d = data.get_recent_emails(hours=hours, unread_only=unread_only, topic=topic)
    items = d.get("items", [])
    qualifier = " unread" if unread_only else ""
    spoken = (
        f"{len(items)}{qualifier} emails in the last {hours} hours. Newest is from "
        f"{items[0].get('who', 'someone')}. They're on screen."
        if items else f"No{qualifier} inbox email in the last {hours} hours."
    )
    result = await render.render(
        type=render.INTEL,
        tool="get_recent_emails",
        spoken=spoken,
        title=f"Email · last {hours} hours",
        payload={"query": topic or f"last {hours} hours", "items": items},
    )
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def plan_my_day(context: RunContext) -> str:
    """A prioritized list of what to work on today.

    Use for 'what should I work on', 'plan my day', 'what's first'.
    """
    d = data.get_actions()
    items = d.get("items", [])
    # Keep the title's own casing: lowercasing it mangles names like Northwind.
    spoken = (
        f"Start with {items[0]['title'].rstrip('.')}. "
        f"{len(items)} things ranked on screen."
        if items else "Nothing queued. Enjoy it."
    )
    result = await render.render(
        type=render.ACTIONS,
        tool="plan_my_day",
        spoken=spoken,
        title=d.get("title", "Today"),
        payload={"items": items},
    )
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def list_my_tasks(context: RunContext) -> str:
    """Show the user's incomplete Google Tasks."""
    tasks = productivity.list_google_tasks()
    items = [{"rank": i + 1, "title": x.get("title", "Untitled task"), "why": x.get("notes", "Google Tasks"), "effort": x.get("due", "")} for i, x in enumerate(tasks)]
    spoken = f"{len(items)} open Google tasks. They're ranked on screen." if items else "No open Google tasks."
    result = await render.render(type=render.ACTIONS, tool="list_my_tasks", spoken=spoken, title="Google Tasks · open", payload={"items": items})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def propose_task(context: RunContext, title: str, notes: str = "", due: str = "") -> str:
    """Prepare a Google Task for approval; this does not create it yet.

    Args:
        title: Clear task title.
        notes: Optional context.
        due: Optional ISO date such as 2026-08-21.
    """
    item = productivity.propose_google_task(title, notes, due)
    pending = productivity.pending_actions()
    rows = [{"rank": i + 1, "title": x["title"], "why": f"Approval ID {x['id']} · {x.get('notes') or 'Google Task'}", "effort": x.get("due", "")} for i, x in enumerate(pending)]
    spoken = f"Task prepared, not created. Say approve {item['id']} when you're ready."
    result = await render.render(type=render.ACTIONS, tool="propose_task", spoken=spoken, title="Approval queue", payload={"items": rows})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def show_approval_queue(context: RunContext) -> str:
    """Show cloud actions waiting for the user's approval."""
    pending = productivity.pending_actions()
    rows = [{"rank": i + 1, "title": x["title"], "why": f"Approval ID {x['id']} · {x.get('notes') or x['kind']}", "effort": x.get("due", "")} for i, x in enumerate(pending)]
    spoken = f"{len(rows)} actions waiting for approval." if rows else "The approval queue is clear."
    result = await render.render(type=render.ACTIONS, tool="show_approval_queue", spoken=spoken, title="Approval queue", payload={"items": rows})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def approve_action(context: RunContext, action_id: str) -> str:
    """Execute one queued action after the user explicitly says to approve its ID.

    Args:
        action_id: The exact approval ID shown on screen.
    """
    item = productivity.approve_action(action_id)
    spoken = f"Approved. {item['title']} is now in Google Tasks."
    result = await render.render(type=render.ACTIONS, tool="approve_action", spoken=spoken, title="Action completed", payload={"items":[{"rank":1,"title":item["title"],"why":"Created in Google Tasks","effort":item.get("due","")} ]})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def remember_note(context: RunContext, title: str, text: str) -> str:
    """Store a user-provided note in private local semantic memory."""
    productivity.remember(f"note:{title.lower()}:{len(text)}", "Personal note", title, text)
    spoken = f"Remembered: {title}. It stays on this Mac."
    await context.session.say(spoken, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def search_private_memory(context: RunContext, query: str) -> str:
    """Semantically search private notes and indexed connected data."""
    hits = productivity.search_memory(query)
    items = [{"when": x["updated_at"], "source": x["source"], "who": x["source"], "quote": f"{x['title']}: {x['text'][:260]}", "tags": ["memory"]} for x in hits]
    spoken = f"{len(items)} relevant memories. Best matches are on screen." if items else "Nothing relevant in private memory yet."
    result = await render.render(type=render.INTEL, tool="search_private_memory", spoken=spoken, title=f'Memory · "{query}"', payload={"query":query,"items":items})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def get_weather(context: RunContext, location: str = "") -> str:
    """Show current conditions and a four-day forecast.

    Args:
        location: City or place. Leave empty for the user's default location.
    """
    d = lifestyle.weather(location)
    spoken = f"{d['location']} is {d['temperature']} degrees and {d['condition'].lower()}. Forecast's on screen."
    signals = [
        {"label": "Now", "value": f"{d['temperature']}°F", "delta": d["condition"]},
        {"label": "Feels like", "value": f"{d['feels_like']}°F"},
        {"label": "Humidity", "value": f"{d['humidity']}%"},
        {"label": "Wind", "value": f"{d['wind']} mph"},
    ]
    lines = [f"{x['day']}: {x['condition']}, {x['high']}° / {x['low']}° · rain {x['rain']}%" for x in d["days"]]
    result = await render.render(type=render.BRIEF, tool="get_weather", spoken=spoken, title=f"Weather · {d['location']}", payload={"summary": spoken, "signals": signals, "sections": [{"heading": "Four-day forecast", "lines": lines}]})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def get_news(context: RunContext, topic: str = "") -> str:
    """Show current news headlines, optionally filtered to a topic.

    Args:
        topic: Optional subject such as technology, Dallas, or artificial intelligence.
    """
    return await deliver_news(context.session, topic)


async def deliver_news(session, topic: str = "") -> str:
    """Publish and speak live news; callable by routing and the LLM tool."""
    stories = lifestyle.news(topic)
    items = [{"when": x["published"], "source": x["source"], "who": x["source"], "quote": x["title"]} for x in stories]
    label = f" on {topic}" if topic else ""
    spoken = f"{len(items)} current headlines{label}. The sources are on screen." if items else f"No current headlines found{label}."
    result = await render.render(type=render.INTEL, tool="get_news", spoken=spoken, title=f"News{f' · {topic}' if topic else ' · top stories'}", payload={"query": topic or "top stories", "items": items})
    await session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def get_computer_health(context: RunContext) -> str:
    """Show this Mac's processor, memory, storage, and battery health."""
    d = lifestyle.computer_health()
    signals = [
        {"label": "CPU", "value": f"{d['cpu']}%", "alert": d["cpu"] >= 90},
        {"label": "Memory", "value": f"{d['memory']}%", "alert": d["memory"] >= 90},
        {"label": "Storage", "value": f"{d['disk']}%", "delta": f"{d['disk_free_gb']} GB free", "alert": d["disk"] >= 90},
    ]
    if d["battery"] is not None:
        signals.append({"label": "Battery", "value": f"{d['battery']}%", "delta": "charging" if d["charging"] else "on battery", "alert": d["battery"] < 15 and not d["charging"]})
    alerts = [x["label"] for x in signals if x.get("alert")]
    spoken = "The Mac looks healthy. Readings are on screen." if not alerts else f"The Mac needs attention: {', '.join(alerts)}. Details are on screen."
    result = await render.render(type=render.BRIEF, tool="get_computer_health", spoken=spoken, title=f"System · {d['computer']}", payload={"summary": spoken, "signals": signals, "sections": []})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def open_web_search(context: RunContext, query: str, destination: str = "web") -> str:
    """Open an explicit user-requested search in the default browser.

    Args:
        query: What the user explicitly asked to search for.
        destination: web, google, youtube, or maps.
    """
    d = lifestyle.open_search(query, destination)
    spoken = f"Opened {d['destination']} results for {d['query']}."
    result = await render.render(type=render.ACTIONS, tool="open_web_search", spoken=spoken, title="Browser search", payload={"items": [{"rank": 1, "title": d["query"], "why": d["url"], "effort": d["destination"]}]})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def run_jarvis_doctor(context: RunContext) -> str:
    """Check every local service and connected account used by Jarvis."""
    checks = operations.doctor()
    failed = [x for x in checks if not x["ok"]]
    rows = [{"rank": i + 1, "title": x["name"], "why": x["detail"], "effort": "ONLINE" if x["ok"] else "FAILED"} for i, x in enumerate(checks)]
    spoken = "All Jarvis systems passed." if not failed else f"{len(failed)} Jarvis systems need attention. They're marked on screen."
    result = await render.render(type=render.ACTIONS, tool="run_jarvis_doctor", spoken=spoken, title="Jarvis Doctor", payload={"items": rows})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def sync_connected_memory(context: RunContext, limit: int = 20) -> str:
    """Privately index recent Google Drive and Dropbox files on this Mac.

    Args:
        limit: Maximum recent files to inspect from each service, from 1 to 50.
    """
    d = operations.sync_memory(limit)
    rows = [{"rank": 1, "title": "Google Drive", "why": "Private local index", "effort": str(d["indexed"]["Google Drive"])}, {"rank": 2, "title": "Dropbox", "why": "Private local index", "effort": str(d["indexed"]["Dropbox"])}, {"rank": 3, "title": "Total memory", "why": "Items searchable on this Mac", "effort": str(d["memory_total"])}]
    spoken = f"Indexed {d['total']} connected files. The private memory now has {d['memory_total']} items."
    result = await render.render(type=render.ACTIONS, tool="sync_connected_memory", spoken=spoken, title="Private memory sync", payload={"items": rows})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def check_monitors(context: RunContext) -> str:
    """Check Gmail and Google Analytics for important changes or anomalies."""
    d = operations.check_monitors()
    return await deliver_monitor_report(context.session, d)


async def deliver_monitor_report(session, d: dict) -> str:
    """Publish monitor results for manual checks and the background loop."""
    alerts = d["alerts"]
    rows = [{"rank": i + 1, "title": x["title"], "why": x["why"], "effort": "ALERT"} for i, x in enumerate(alerts)]
    if not rows:
        rows = [{"rank": 1, "title": "No material changes", "why": f"{d['important_email_count']} important email · analytics {d['analytics_delta']}%", "effort": "CLEAR"}]
    spoken = f"{len(alerts)} monitor alerts." if alerts else "Monitors are clear. Nothing material changed."
    result = await render.render(type=render.ACTIONS, tool="check_monitors", spoken=spoken, title="Continuous monitors", payload={"items": rows})
    await session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def deep_research(context: RunContext, query: str) -> str:
    """Research a topic across multiple web sources and private local memory.

    Args:
        query: The specific topic or question to investigate.
    """
    d = operations.deep_research(query)
    items = [{"when": "Web", "source": x["title"], "who": urllib_host(x["url"]), "quote": x["excerpt"] or x["title"], "url": x["url"]} for x in d["sources"]]
    items += [{"when": x["updated_at"], "source": x["source"], "who": "Private memory", "quote": f"{x['title']}: {x['text'][:500]}"} for x in d["memories"]]
    spoken = f"Research found {len(d['sources'])} web sources and {len(d['memories'])} private-memory matches. Citations are on screen."
    result = await render.render(type=render.INTEL, tool="deep_research", spoken=spoken, title=f'Research · "{query}"', payload={"query": query, "items": items})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


def urllib_host(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.removeprefix("www.")


@function_tool
async def set_operating_mode(context: RunContext, mode: str) -> str:
    """Switch Jarvis's operating emphasis.

    Args:
        mode: executive, research, monitor, creative, private, or operator.
    """
    d = operations.set_mode(mode)
    spoken = f"{d['mode'].title()} mode active. {d['description']}"
    result = await render.render(type=render.ACTIONS, tool="set_operating_mode", spoken=spoken, title="Operating mode", payload={"items": [{"rank": 1, "title": d["mode"].title(), "why": d["description"], "effort": "ACTIVE"}]})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


@function_tool
async def schedule_morning_digest(context: RunContext, hour: int = 8) -> str:
    """Set the local hour when Jarvis should deliver the first daily brief.

    Args:
        hour: Local 24-hour clock hour, such as 8 for 8 AM.
    """
    d = operations.configure_digest(hour)
    spoken = f"Morning digest set for {d['label']} local time. It'll appear on the first active session after that time."
    result = await render.render(type=render.ACTIONS, tool="schedule_morning_digest", spoken=spoken, title="Morning digest", payload={"items": [{"rank": 1, "title": d["label"], "why": "First active Jarvis session each day", "effort": "SCHEDULED"}]})
    await context.session.say(result, allow_interruptions=False)
    return "The prepared answer was already spoken. Do not repeat it."


ALL_TOOLS = [
    respond_conversationally,
    get_daily_brief,
    get_recent_emails,
    list_my_tasks,
    propose_task,
    show_approval_queue,
    approve_action,
    remember_note,
    search_private_memory,
    get_weather,
    get_news,
    get_computer_health,
    open_web_search,
    run_jarvis_doctor,
    sync_connected_memory,
    check_monitors,
    deep_research,
    set_operating_mode,
    schedule_morning_digest,
    query_metrics,
    get_pipeline,
    search_intel,
    plan_my_day,
]
