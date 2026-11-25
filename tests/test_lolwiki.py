"""
Tests for the League of Legends Wiki summoner spell ingester.

No network: the Lua data module is read from a trimmed fixture copied from
https://wiki.leagueoflegends.com/en-us/Module:SpellDataWR/data.
"""

import importlib.util
import io
import sys
from pathlib import Path

import pytest
import yaml

from lolwiki.lua_table import LuaParseError, parse_lua_table
from lolwiki.summoner_spells import (
    parse_summoner_spells,
    wiki_url,
    write_summoner_spell,
)
from lolwiki.wikitext import to_plain_text

FIXTURE = Path(__file__).parent / "fixtures" / "spelldatawr_sample.lua"


def _load_cli():
    path = Path(__file__).parent.parent / "ingest-lolwiki.py"
    spec = importlib.util.spec_from_file_location("ingest_lolwiki", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParseLuaTable:
    def test_return_table_with_bracketed_keys(self):
        text = 'return { ["a"] = "x", ["b"] = true, ["c"] = false, }'
        assert parse_lua_table(text) == {"a": "x", "b": True, "c": False}

    def test_nested_tables_and_comments(self):
        text = """-- <pre>
        return {
            ["Flash"] = { ["maps"] = { ["wr"] = true, }, }, -- trailing
        }
        -- </pre>
        """
        assert parse_lua_table(text) == {"Flash": {"maps": {"wr": True}}}

    def test_string_escapes_and_dashes_inside_strings(self):
        text = r'return { ["s"] = "say \"hi\" -- not a comment" }'
        assert parse_lua_table(text) == {"s": 'say "hi" -- not a comment'}

    def test_bare_keys_numbers_and_arrays(self):
        text = "return { a = 1, b = 2.5, { 'x', 'y' } }"
        assert parse_lua_table(text) == {"a": 1, "b": 2.5, 1: ["x", "y"]}

    def test_rejects_garbage(self):
        with pytest.raises(LuaParseError):
            parse_lua_table("return { [ }")


class TestToPlainText:
    def test_tip_uses_display_text(self):
        assert to_plain_text("{{WRtip|slow|slowing}} them") == "slowing them"
        assert to_plain_text("{{WRtip|Blink}} away") == "Blink away"

    def test_icon_only_tip_is_dropped(self):
        assert to_plain_text("{{WRtip|er|icononly = true}} 500") == "500"

    def test_level_scaling(self):
        assert (
            to_plain_text("for {{pp|120 to 560 for 15}}")
            == "for 120 - 560 (based on level)"
        )

    def test_scaling_with_key_and_type(self):
        text = "{{pp|15 to 0 for 16|2:00;2:12|key=%|type= game time|label1= time}}"
        assert to_plain_text(text) == "15% - 0% (based on game time)"

    def test_nested_templates(self):
        text = "{{as|{{fd|{{pp|11 to 25 for 15}}}} '''bonus''' Attack Damage}}"
        assert to_plain_text(text) == "11 - 25 (based on level) bonus Attack Damage"

    def test_misc_templates(self):
        assert to_plain_text("{{sti|ah|reduces}}") == "reduces"
        assert to_plain_text("{{sti|heal}}") == "heal"
        assert to_plain_text("{{sbc|Active:}} Go") == "Active: Go"
        assert to_plain_text("{{ccib|Summoner spell icon.png|WR:Spell|spell}}") == (
            "spell"
        )
        assert to_plain_text("{{WRs|Mark}}") == "Mark"
        assert to_plain_text("gain {{g|1|wr=true}} per stack") == (
            "gain 1 gold per stack"
        )
        assert to_plain_text("{{tt|40|Starts after Dash}}") == "40"

    def test_unknown_template_is_dropped(self):
        assert to_plain_text("{{WR Rune data Hexflash|pst2|cooldown}}") == ""

    def test_markup_and_lists(self):
        text = "''Mark'' is '''off'''.<br/>Then:<ul><li>one</li><li>two</li></ul>"
        assert to_plain_text(text) == "Mark is off.\nThen:\n- one\n- two"

    def test_wiki_links(self):
        assert to_plain_text("[[WR:Flash|Flash]] and [[Ghost]]") == "Flash and Ghost"


class TestParseSummonerSpells:
    @pytest.fixture(scope="class")
    def spells(self):
        return {s["name"]: s for s in parse_summoner_spells(FIXTURE.read_text())}

    def test_keeps_only_current_wild_rift_summoner_spells(self, spells):
        # Challenging Smite is removed, Clarity is ARAM-only, Recall is not a
        # summoner spell slot, Hexflash's text lives in a rune template.
        assert sorted(spells) == ["Barrier", "Flash", "Ghost", "Smite"]

    def test_flash(self, spells):
        flash = spells["Flash"]
        assert flash["cooldown"] == 150
        assert flash["range"] == "400"
        assert flash["maps"] == ["Summoner's Rift", "Howling Abyss"]
        assert flash["source_url"] == "https://wiki.leagueoflegends.com/en-us/WR:Flash"
        assert flash["description"] == (
            "Blink your champion a short distance forward or towards the target"
            " direction.\n\nFlash is disabled while you are unable to cast abilities."
        )

    def test_ghost_and_barrier_cooldowns(self, spells):
        assert spells["Ghost"]["cooldown"] == 90
        assert spells["Barrier"]["cooldown"] == 100

    def test_charges(self, spells):
        smite = spells["Smite"]
        assert smite["charges"] == 2
        assert smite["recharge"] == 90
        assert smite["maps"] == ["Summoner's Rift"]

    def test_wiki_url_keeps_anchor(self):
        assert (
            wiki_url("WR:Smite#Chilling_")
            == "https://wiki.leagueoflegends.com/en-us/WR:Smite#Chilling_"
        )
        assert (
            wiki_url("WR:Empowered Recall")
            == "https://wiki.leagueoflegends.com/en-us/WR:Empowered_Recall"
        )


class TestWriteSummonerSpell:
    def test_frontmatter_and_body(self):
        spells = {s["name"]: s for s in parse_summoner_spells(FIXTURE.read_text())}
        buf = io.StringIO()
        write_summoner_spell(spells["Smite"], buf)
        text = buf.getvalue()

        _, front, body = text.split("---\n", 2)
        meta = yaml.safe_load(front)
        assert meta["name"] == "Smite"
        assert meta["cooldown"] == 10
        assert meta["charges"] == 2
        assert meta["source_url"].endswith("/WR:Smite")
        assert body.startswith("\n# Smite\n")
        assert "**Cooldown:** 10 seconds" in body
        assert "**Charges:** 2 (90 second recharge)" in body
        assert "**Range:** 500" in body
        assert "## Description" in body
        assert "- Attacking monsters restores 40 health over 5 seconds." in body
        # The wiki's <br/> becomes a paragraph break so Markdown keeps it.
        assert "(10% maximum health).\n\nTransforms into Chilling Smite" in body


class TestCli:
    def test_writes_pages_and_removes_stale_files(self, tmp_path, monkeypatch):
        cli = _load_cli()
        kb = tmp_path / "kb"
        stale = kb / "summoner-spells" / "clarity.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("old")

        monkeypatch.setattr(
            sys,
            "argv",
            ["ingest-lolwiki.py", "--kb", str(kb), "--module-file", str(FIXTURE)],
        )
        cli.main()

        pages = sorted(p.name for p in (kb / "summoner-spells").glob("*.md"))
        assert pages == ["barrier.md", "flash.md", "ghost.md", "smite.md"]

    def test_single_spell_leaves_others(self, tmp_path, monkeypatch):
        cli = _load_cli()
        kb = tmp_path / "kb"
        other = kb / "summoner-spells" / "heal.md"
        other.parent.mkdir(parents=True)
        other.write_text("keep")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "ingest-lolwiki.py",
                "--kb",
                str(kb),
                "--module-file",
                str(FIXTURE),
                "--spell",
                "flash",
            ],
        )
        cli.main()

        pages = sorted(p.name for p in (kb / "summoner-spells").glob("*.md"))
        assert pages == ["flash.md", "heal.md"]
