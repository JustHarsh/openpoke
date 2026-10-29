from pathlib import Path

from server.paths import DATA_DIR
from server.services.gmail import execute_gmail_tool


def test_data_dir_is_isolated():
    assert "openpoke-test-" in str(DATA_DIR)
    assert DATA_DIR != Path(__file__).resolve().parent.parent / "server" / "data"


def test_gmail_is_mocked():
    result = execute_gmail_tool("GMAIL_FETCH_EMAILS", "mock-user", arguments={"query": "alice"})
    assert result["data"]["messages"]
