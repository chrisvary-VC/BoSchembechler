"""Live everyday-assistant services with no paid API keys required."""

from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil


USER_AGENT = "JarvisAIOS/1.0"


def _get(url: str, timeout: int = 10) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def weather(location: str = "") -> dict:
    place = location.strip() or os.getenv("JARVIS_DEFAULT_LOCATION", "Dallas, Texas")
    query = urllib.parse.urlencode({"name": place, "count": 1, "language": "en", "format": "json"})
    geo = __import__("json").loads(_get(f"https://geocoding-api.open-meteo.com/v1/search?{query}"))
    matches = geo.get("results") or []
    if not matches:
        raise ValueError(f"I couldn't locate {place}.")
    match = matches[0]
    params = urllib.parse.urlencode({
        "latitude": match["latitude"],
        "longitude": match["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 4,
    })
    forecast = __import__("json").loads(_get(f"https://api.open-meteo.com/v1/forecast?{params}"))
    current = forecast["current"]
    daily = forecast["daily"]
    labels = {
        0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle",
        55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
        81: "Rain showers", 82: "Heavy showers", 95: "Thunderstorms",
        96: "Thunderstorms with hail", 99: "Thunderstorms with hail",
    }
    days = []
    for i, date in enumerate(daily["time"]):
        name = "Today" if i == 0 else dt.date.fromisoformat(date).strftime("%A")
        days.append({
            "day": name,
            "condition": labels.get(daily["weather_code"][i], "Mixed conditions"),
            "high": round(daily["temperature_2m_max"][i]),
            "low": round(daily["temperature_2m_min"][i]),
            "rain": daily["precipitation_probability_max"][i],
        })
    return {
        "location": ", ".join(x for x in (match.get("name"), match.get("admin1")) if x),
        "condition": labels.get(current["weather_code"], "Mixed conditions"),
        "temperature": round(current["temperature_2m"]),
        "feels_like": round(current["apparent_temperature"]),
        "humidity": current["relative_humidity_2m"],
        "wind": round(current["wind_speed_10m"]),
        "precipitation": current["precipitation"],
        "days": days,
    }


def news(topic: str = "", limit: int = 6) -> list[dict]:
    if topic.strip():
        params = urllib.parse.urlencode({"q": topic.strip(), "hl": "en-US", "gl": "US", "ceid": "US:en"})
        url = f"https://news.google.com/rss/search?{params}"
    else:
        url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    root = ET.fromstring(_get(url))
    results = []
    for item in root.findall("./channel/item")[: max(1, min(limit, 10))]:
        title = (item.findtext("title") or "Untitled").strip()
        source = item.findtext("source") or (title.rsplit(" - ", 1)[-1] if " - " in title else "Google News")
        if title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        results.append({
            "title": title,
            "source": source,
            "published": item.findtext("pubDate") or "",
            "url": item.findtext("link") or "",
        })
    return results


def computer_health() -> dict:
    root_disk = shutil.disk_usage("/")
    workspace_path = Path(__file__).resolve().parent.parent
    workspace_disk = shutil.disk_usage(workspace_path)
    memory = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    return {
        "computer": platform.node() or "This Mac",
        "cpu": round(psutil.cpu_percent(interval=0.25)),
        "memory": round(memory.percent),
        "disk": round((workspace_disk.used / workspace_disk.total) * 100),
        "disk_free_gb": round(workspace_disk.free / (1024 ** 3)),
        "disk_label": workspace_path.anchor.rstrip("/") or "Workspace",
        "root_disk": round((root_disk.used / root_disk.total) * 100),
        "root_disk_free_gb": round(root_disk.free / (1024 ** 3)),
        "battery": round(battery.percent) if battery else None,
        "charging": bool(battery.power_plugged) if battery else None,
    }


def open_search(query: str, destination: str = "web") -> dict:
    clean = query.strip()
    if not clean:
        raise ValueError("A search needs a topic.")
    destination = destination.strip().lower()
    bases = {
        "web": "https://www.google.com/search?q=",
        "google": "https://www.google.com/search?q=",
        "youtube": "https://www.youtube.com/results?search_query=",
        "maps": "https://www.google.com/maps/search/",
    }
    if destination not in bases:
        destination = "web"
    url = bases[destination] + urllib.parse.quote_plus(clean)
    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"query": clean, "destination": destination, "url": url}
