#!/usr/bin/env python3
"""
Tavily MCP Server — Web search, extract, crawl, map, research via MCP protocol.
API keys managed by KeyPool with round-robin load balancing.
"""
from __future__ import annotations

import json
import time
from typing import Any

from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient

from key_pool import KeyPool, _mask

mcp = FastMCP("Tavily Web Search", instructions="Use this server to search the web, extract content from URLs, crawl websites, map site structures, and conduct AI-powered research.")

pool = KeyPool()

KEY_STRATEGY = "round-robin"  # or "least-used"


def _get_client() -> tuple[TavilyClient, str]:
    if KEY_STRATEGY == "least-used":
        result = pool.next_key_least_used()
    else:
        result = pool.next_key()
    if result is None:
        raise RuntimeError("No active API keys in pool. Add keys via CLI or dashboard.")
    raw, masked = result
    return TavilyClient(raw), masked


def _record(masked: str, endpoint: str, start: float, success: bool,
            credits: int = 0, error_msg: str = ""):
    latency = (time.time() - start) * 1000
    pool.record_request(masked, endpoint, latency, success, credits, error_msg)


# ═══════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def tavily_search(
    query: str,
    search_depth: str = "basic",
    topic: str = "general",
    time_range: str = "",
    start_date: str = "",
    end_date: str = "",
    max_results: int = 5,
    chunks_per_source: int = 3,
    include_images: bool = False,
    include_image_descriptions: bool = False,
    include_answer: bool = False,
    include_raw_content: bool = False,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    country: str = "",
    exact_match: bool = False,
    include_favicon: bool = False,
    include_usage: bool = True,
) -> str:
    """Search the web. Returns LLM-optimized results with content, scores, and URLs.

    Args:
        query: Search query string.
        search_depth: `basic` (1 credit) or `advanced` (2 credits). Advanced gets more relevant sources.
        topic: `general`, `news`, or `finance`.
        time_range: `day`, `week`, `month`, `year` or `d`, `w`, `m`, `y`.
        start_date: YYYY-MM-DD format. Returns results after this date.
        end_date: YYYY-MM-DD format. Returns results before this date.
        max_results: Number of results, 0-20. Default 5.
        chunks_per_source: Max content chunks per source (1-3). Only with advanced depth.
        include_images: Include images in results.
        include_image_descriptions: Include image descriptions with images.
        include_answer: Include LLM-generated answer. `basic` or `advanced`.
        include_raw_content: Include cleaned HTML/markdown content.
        include_domains: List of domains to restrict search to (max 300).
        exclude_domains: List of domains to exclude (max 150).
        country: Prioritize results from this country (only with topic=general).
        exact_match: Only return results with exact quoted phrases.
        include_favicon: Include favicon URLs.
        include_usage: Include credit usage in response (default True for tracking).
    """
    t0 = time.time()
    client, masked = _get_client()
    kwargs: dict[str, Any] = {
        "query": query,
        "search_depth": search_depth,
        "topic": topic,
        "max_results": max_results,
        "chunks_per_source": chunks_per_source,
        "include_images": include_images,
        "include_image_descriptions": include_image_descriptions,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "include_favicon": include_favicon,
        "exact_match": exact_match,
        "include_usage": include_usage,
    }
    if time_range:
        kwargs["time_range"] = time_range
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if country:
        kwargs["country"] = country

    try:
        resp = client.search(**kwargs)
        credits = 0
        if isinstance(resp, dict) and "usage" in resp:
            usage = resp["usage"]
            if isinstance(usage, dict):
                credits = usage.get("credits", 0) or _est_credits(search_depth)
        _record(masked, "search", t0, True, credits)
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        _record(masked, "search", t0, False, 0, str(e))
        return json.dumps({"error": str(e), "key_used": masked})


@mcp.tool()
def tavily_extract(
    urls: list[str],
    extract_depth: str = "basic",
    format: str = "markdown",
    include_images: bool = False,
    include_favicon: bool = False,
    include_usage: bool = True,
    query: str = "",
    chunks_per_source: int = 3,
    timeout: float = 30.0,
) -> str:
    """Extract clean content from one or more URLs. Handles JavaScript-rendered pages.

    Args:
        urls: List of URLs to extract (max 20).
        extract_depth: `basic` (1 credit per 5 URLs) or `advanced` (2 credits per 5 URLs).
        format: `markdown` or `text`.
        include_images: Include extracted images.
        include_favicon: Include favicon URLs.
        include_usage: Include credit usage (default True).
        query: User intent for reranking content chunks.
        chunks_per_source: Max chunks per source, 1-5. Requires query.
        timeout: Max seconds per URL, 1-60.
    """
    t0 = time.time()
    client, masked = _get_client()
    kwargs: dict[str, Any] = {
        "urls": urls,
        "extract_depth": extract_depth,
        "format": format,
        "include_images": include_images,
        "include_favicon": include_favicon,
        "include_usage": include_usage,
    }
    if query:
        kwargs["query"] = query
        kwargs["chunks_per_source"] = chunks_per_source
    if timeout:
        kwargs["timeout"] = timeout

    try:
        resp = client.extract(**kwargs)
        credits = 0
        if isinstance(resp, dict) and "usage" in resp:
            credits = resp["usage"].get("credits", 0) if isinstance(resp["usage"], dict) else 0
        _record(masked, "extract", t0, True, credits)
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        _record(masked, "extract", t0, False, 0, str(e))
        return json.dumps({"error": str(e), "key_used": masked})


@mcp.tool()
def tavily_crawl(
    url: str,
    max_depth: int = 2,
    limit: int = 10,
    instructions: str = "",
    chunks_per_source: int = 3,
    include_images: bool = False,
    include_favicon: bool = False,
    include_usage: bool = True,
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    timeout: float = 150.0,
) -> str:
    """Crawl a website and extract content from multiple pages.

    Starts from a base URL and follows links, extracting content from discovered pages.

    Args:
        url: Starting URL for the crawl.
        max_depth: How many levels of links to follow.
        limit: Maximum number of pages to crawl.
        instructions: Natural language instructions for semantic focus.
        chunks_per_source: Max chunks per source, 1-5. Requires instructions.
        include_images: Include extracted images.
        include_favicon: Include favicon URLs.
        include_usage: Include credit usage.
        select_paths: Regex patterns for paths to include.
        exclude_paths: Regex patterns for paths to exclude.
        timeout: Max seconds for the crawl, 10-150.
    """
    t0 = time.time()
    client, masked = _get_client()
    kwargs: dict[str, Any] = {
        "url": url,
        "max_depth": max_depth,
        "limit": limit,
        "include_images": include_images,
        "include_favicon": include_favicon,
        "include_usage": include_usage,
    }
    if instructions:
        kwargs["instructions"] = instructions
        kwargs["chunks_per_source"] = chunks_per_source
    if select_paths:
        kwargs["select_paths"] = select_paths
    if exclude_paths:
        kwargs["exclude_paths"] = exclude_paths
    if timeout:
        kwargs["timeout"] = timeout

    try:
        resp = client.crawl(**kwargs)
        credits = 0
        if isinstance(resp, dict) and "usage" in resp:
            credits = resp["usage"].get("credits", 0) if isinstance(resp["usage"], dict) else 0
        _record(masked, "crawl", t0, True, credits)
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        _record(masked, "crawl", t0, False, 0, str(e))
        return json.dumps({"error": str(e), "key_used": masked})


@mcp.tool()
def tavily_map(
    url: str,
    max_depth: int = 2,
    limit: int = 100,
    instructions: str = "",
    select_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    include_usage: bool = True,
    timeout: float = 150.0,
) -> str:
    """Discover and list URLs on a website. Faster than crawling.

    Maps a site's structure to find pages before extracting.

    Args:
        url: Starting URL to map.
        max_depth: Link depth to explore.
        limit: Maximum number of URLs to discover.
        instructions: Natural language instructions to filter pages.
        select_paths: Regex patterns for paths to include.
        exclude_paths: Regex patterns for paths to exclude.
        include_usage: Include credit usage.
        timeout: Max seconds, 10-150.
    """
    t0 = time.time()
    client, masked = _get_client()
    kwargs: dict[str, Any] = {
        "url": url,
        "max_depth": max_depth,
        "limit": limit,
        "include_usage": include_usage,
    }
    if instructions:
        kwargs["instructions"] = instructions
    if select_paths:
        kwargs["select_paths"] = select_paths
    if exclude_paths:
        kwargs["exclude_paths"] = exclude_paths
    if timeout:
        kwargs["timeout"] = timeout

    try:
        resp = client.map(**kwargs)
        credits = 0
        if isinstance(resp, dict) and "usage" in resp:
            credits = resp["usage"].get("credits", 0) if isinstance(resp["usage"], dict) else 0
        _record(masked, "map", t0, True, credits)
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        _record(masked, "map", t0, False, 0, str(e))
        return json.dumps({"error": str(e), "key_used": masked})


@mcp.tool()
def tavily_research(
    query: str,
    model: str = "standard",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    output_length: str = "standard",
    include_usage: bool = True,
) -> str:
    """AI-powered deep research producing a cited report. Takes 30-120 seconds.

    Gathers sources, analyzes them, and produces a cited synthesis.

    Args:
        query: Research question or topic.
        model: `standard` or `pro` for more comprehensive analysis.
        include_domains: Soft preference for source domains (max 20).
        exclude_domains: Hard blocklist of domains to exclude (max 20).
        output_length: `short`, `standard`, or `long`.
        include_usage: Include credit usage.
    """
    t0 = time.time()
    client, masked = _get_client()
    # NOTE: newer tavily-python SDK renamed the first positional arg from
    # `query` to `input`; the API itself still accepts model=standard/pro,
    # but the SDK enforces model ∈ {mini, pro, auto} at runtime, so map the
    # API-level "standard" to "auto" (server-side default).
    kwargs: dict[str, Any] = {
        "input": query,
        "model": model if model != "standard" else "auto",
        "output_length": output_length,
        "include_usage": include_usage,
    }
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains

    try:
        task = client.research(**kwargs)
        if not isinstance(task, dict) or "request_id" not in task:
            raise RuntimeError(f"unexpected research response: {task}")
        request_id = task["request_id"]
        # Research is async: poll get_research() until completed (30-120s+).
        # The task is bound to the creating key, so keep polling with the SAME client.
        deadline = time.time() + 570
        resp = task
        while time.time() < deadline:
            if isinstance(resp, dict) and resp.get("status") == "completed":
                break
            time.sleep(5)
            resp = client.get_research(request_id)
        else:
            resp = {
                "status": "timeout",
                "request_id": request_id,
                "message": "research still pending after 570s; use tavily_research_status to fetch it later",
            }
        credits = 0
        if isinstance(resp, dict) and "usage" in resp:
            credits = resp["usage"].get("credits", 0) if isinstance(resp["usage"], dict) else 0
        _record(masked, "research", t0, True, credits)
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as e:
        _record(masked, "research", t0, False, 0, str(e))
        return json.dumps({"error": str(e), "key_used": masked})


@mcp.tool()
def tavily_pool_status() -> str:
    """Get API key pool status — active keys, usage stats, recent activity."""
    stats = pool.get_stats()
    return json.dumps(stats, ensure_ascii=False, indent=2)


@mcp.tool()
def tavily_research_status(request_id: str) -> str:
    """Check an async research task's status/result by request_id (tavily_research may time out; the task keeps running server-side)."""
    for k in pool.list_keys():
        if not k.is_active:
            continue
        try:
            client = TavilyClient(k.key)
            resp = client.get_research(request_id)
            return json.dumps(resp, ensure_ascii=False, indent=2)
        except Exception:
            # 404 etc. — task is bound to its creating key; try the next one
            continue
    return json.dumps({"error": "research task not found for any active key", "request_id": request_id})


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _est_credits(depth: str) -> int:
    return 2 if depth == "advanced" else 1


def main():
    mcp.run()


if __name__ == "__main__":
    main()
