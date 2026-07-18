"""M16: has_custom_data gating logic -- the licensing wall's runtime gate.

The custom-data features must light up only when all three conditions hold:
the table exists, it has rows, and the environment opts in with
MONSTERLAB_LOCAL=1 (the deployed app never sets it, so even an accidentally
committed DB could not enable them there).
"""

import sqlite3

from common import has_custom_data

CREATE = "CREATE TABLE sd_monsters_custom (id INTEGER PRIMARY KEY, name TEXT)"


def test_false_without_env_var_even_with_rows(monkeypatch):
    monkeypatch.delenv("MONSTERLAB_LOCAL", raising=False)
    conn = sqlite3.connect(":memory:")
    conn.execute(CREATE)
    conn.execute("INSERT INTO sd_monsters_custom (name) VALUES ('Gnoll Pirate')")
    assert has_custom_data(conn) is False


def test_false_with_wrong_env_value(monkeypatch):
    monkeypatch.setenv("MONSTERLAB_LOCAL", "true")
    conn = sqlite3.connect(":memory:")
    conn.execute(CREATE)
    conn.execute("INSERT INTO sd_monsters_custom (name) VALUES ('Gnoll Pirate')")
    assert has_custom_data(conn) is False


def test_false_with_env_but_no_table(monkeypatch):
    monkeypatch.setenv("MONSTERLAB_LOCAL", "1")
    conn = sqlite3.connect(":memory:")
    assert has_custom_data(conn) is False


def test_false_with_env_but_empty_table(monkeypatch):
    monkeypatch.setenv("MONSTERLAB_LOCAL", "1")
    conn = sqlite3.connect(":memory:")
    conn.execute(CREATE)
    assert has_custom_data(conn) is False


def test_true_with_env_table_and_rows(monkeypatch):
    monkeypatch.setenv("MONSTERLAB_LOCAL", "1")
    conn = sqlite3.connect(":memory:")
    conn.execute(CREATE)
    conn.execute("INSERT INTO sd_monsters_custom (name) VALUES ('Gnoll Pirate')")
    assert has_custom_data(conn) is True
