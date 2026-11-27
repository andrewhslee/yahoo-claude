"""Calls the tools through a real MCP client, with Yahoo replaced by saved fixtures."""

import asyncio
import json

from mcp import Client

from yahoo_fantasy_mcp.server import mcp


def call(name: str, args: dict | None = None):
    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(name, args or {})

    result = asyncio.run(run())
    payload = result.structured_content or json.loads(result.content[0].text) if not result.is_error else None
    return result, payload


def test_list_my_teams_sets_default(fake_yahoo):
    result, data = call("list_my_teams")
    assert not result.is_error
    assert data["teams"][0]["league_name"] == "Office League"
    assert data["default_team_key"] == "466.l.12345.t.3"


def test_team_stats_with_chosen_stats(fake_yahoo):
    _, data = call("get_team_stats", {"stats": ["PTS", "AST", "bogus"]})
    hali = next(p for p in data["players"] if p["name"] == "Tyrese Haliburton")
    assert hali["stats"] == {"PTS": 110, "AST": 48}
    assert hali["selected_position"] == "PG"
    assert data["unknown_stats"] == ["bogus"]
    assert any("player_keys=466.p.6001,466.p.6002" in p for p in fake_yahoo.paths)


def test_saved_stat_preferences_are_used(fake_yahoo):
    _, saved = call("set_stat_preferences", {"stats": ["reb", "points"]})
    assert saved["favorite_stats"] == ["REB", "PTS"]
    _, data = call("get_team_stats")
    jokic = next(p for p in data["players"] if p["name"] == "Nikola Jokić")
    assert list(jokic["stats"]) == ["REB", "PTS"]


def test_matchup_summary(fake_yahoo):
    _, data = call("get_matchup")
    assert data["my_category_record"] == {"won": 1, "lost": 1, "tied": 1}
    assert data["category_leader"] == {"PTS": "Splash Zone", "REB": "Rivals", "AST": "tied"}


def test_plan_lineup_change_links_yahoo_page(fake_yahoo):
    _, data = call("plan_lineup_change", {"changes": [{"player": "Brunson", "position": "G"}], "date": "2026-10-29"})
    assert data["ok"]
    assert data["yahoo_page"] == "https://basketball.fantasysports.yahoo.com/nba/12345/3?date=2026-10-29"
    assert "roster;date=2026-10-29" in " ".join(fake_yahoo.paths)


def test_plan_add_drop(fake_yahoo):
    _, data = call("plan_add_drop", {"add": "Walker Kessler", "drop": "Poole"})
    assert data["type"] == "waiver_claim_with_drop"
    assert data["yahoo_page"].endswith("/nba/12345/addplayer?apid=7001")


def test_errors_reach_claude_as_text(fake_yahoo):
    result, _ = call("plan_add_drop", {})
    assert result.is_error
    assert "Give a player to add" in result.content[0].text


def test_check_connection_reports_unapproved_app(fake_yahoo, monkeypatch, tmp_path):
    from yahoo_fantasy_mcp import auth, server
    from yahoo_fantasy_mcp.client import YahooAccessNotApproved

    def refuse(path):
        raise YahooAccessNotApproved("Yahoo hasn't approved this app for the Fantasy API yet.")

    tokens = tmp_path / "tokens.json"
    tokens.write_text("{}")
    monkeypatch.setattr(server, "TOKENS_PATH", tokens)
    monkeypatch.setattr(server, "client_credentials", lambda: ("id", "secret", "uri"))
    monkeypatch.setattr(auth, "access_token", lambda force_refresh=False: "token")
    monkeypatch.setattr(fake_yahoo, "get", refuse)
    result, data = call("check_connection")
    assert not result.is_error
    assert data["signed_in"] and not data["api_access"] and not data["ok"]
    assert "approved" in data["problem"]
