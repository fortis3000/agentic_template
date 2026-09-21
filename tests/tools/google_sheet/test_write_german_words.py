from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.tools.local.google_sheet.write_german_words import (
    GoogleSheetsAddVocabEntryTool,
    GoogleSheetsReadTool,
    GoogleSheetsWriteTool,
)

EXPECTED_CALLS = 2


@patch("src.tools.local.google_sheet.write_german_words.GoogleSheetsClient")
def test_google_sheet_read_tool(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.read_range.return_value = [["A", "B"], ["C", "D"]]

    tool = GoogleSheetsReadTool(spreadsheet_id="test_id")
    read_callable = tool.get_callable()

    result = read_callable("Sheet1!A1:B2")

    assert result == [["A", "B"], ["C", "D"]]
    mock_client.read_range.assert_called_once_with("test_id", "Sheet1!A1:B2")


@patch("src.tools.local.google_sheet.write_german_words.GoogleSheetsClient")
def test_google_sheet_write_tool_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 1st call: pre-check (returns old data)
    # 2nd call: post-check (returns new data with same dimensions)
    mock_client.read_range.side_effect = [
        [["OldA", "OldB"], ["OldC", "OldD"]],
        [["NewA", "NewB"], ["NewC", "NewD"]],
    ]

    mock_client.write_range.return_value = {"updatedCells": 4}

    tool = GoogleSheetsWriteTool(spreadsheet_id="test_id")
    write_callable = tool.get_callable()

    result = write_callable("Sheet1!A1:B2", [["NewA", "NewB"], ["NewC", "NewD"]])

    assert result == {"updatedCells": 4}
    assert mock_client.read_range.call_count == EXPECTED_CALLS
    mock_client.write_range.assert_called_once_with(
        "test_id", "Sheet1!A1:B2", [["NewA", "NewB"], ["NewC", "NewD"]]
    )


@patch("src.tools.local.google_sheet.write_german_words.GoogleSheetsClient")
def test_google_sheet_write_tool_dimension_mismatch(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Pre-check returns 2x2.
    # Post-check returns 1x1 (mismatch from expected 2x2).
    mock_client.read_range.side_effect = [[["OldA", "OldB"], ["OldC", "OldD"]], [["JustA"]]]

    tool = GoogleSheetsWriteTool(spreadsheet_id="test_id")
    write_callable = tool.get_callable()

    with pytest.raises(ValueError, match="Write verification failed"):
        write_callable("Sheet1!A1:B2", [["NewA", "NewB"], ["NewC", "NewD"]])

    # Rollback should be triggered: writing back the original data
    assert mock_client.write_range.call_count == EXPECTED_CALLS
    mock_client.write_range.assert_any_call(
        "test_id", "Sheet1!A1:B2", [["OldA", "OldB"], ["OldC", "OldD"]]
    )


@patch("src.tools.local.google_sheet.write_german_words.GoogleSheetsClient")
def test_google_sheet_add_vocab_entry_tool_success(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    date_suffix = datetime.now().strftime("%y%m%d")
    expected_id = f"vocab_hund_{date_suffix}"

    expected_row = [expected_id, "der Hund", "der", "dog", "[canine]", "", "", "", "", "", ""]

    mock_client.read_range.side_effect = [
        [["w"], ["vocab_hund_260714"]],  # 1st call: read A:A
        [expected_row],  # 2nd call: verification read
    ]
    mock_client.write_range.return_value = {"updatedCells": 11}

    tool = GoogleSheetsAddVocabEntryTool(spreadsheet_id="test_id")
    add_callable = tool.get_callable()

    expected_row_num = 3
    result = add_callable(
        target_german="der Hund",
        gender="der",
        native_translation="dog",
        hint_disambiguation="[canine]",
    )

    assert result["success"] is True
    assert result["row_number"] == expected_row_num
    assert result["written_entry"]["w"] == expected_id
    assert result["written_entry"]["Target_German"] == "der Hund"
    assert result["written_entry"]["Gender"] == "der"
    assert result["written_entry"]["Native_Translation"] == "dog"
    assert result["written_entry"]["Hint_Disambiguation"] == "[canine]"

    # Verify append and read-back calls
    mock_client.read_range.assert_any_call("test_id", "A:A")
    mock_client.read_range.assert_any_call("test_id", "A3:K3")
    mock_client.write_range.assert_called_once_with("test_id", "A3:K3", [expected_row])


@patch("src.tools.local.google_sheet.write_german_words.GoogleSheetsClient")
def test_google_sheet_add_vocab_entry_tool_verification_failure(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    date_suffix = datetime.now().strftime("%y%m%d")
    expected_id = f"vocab_hund_{date_suffix}"
    expected_row = [expected_id, "der Hund", "der", "dog", "[canine]", "", "", "", "", "", ""]

    mock_client.read_range.side_effect = [
        [["w"], ["vocab_hund_260714"]],  # 1st call: read A:A
        [[]],  # 2nd call: verification read (mismatch)
    ]
    mock_client.write_range.return_value = {"updatedCells": 11}

    tool = GoogleSheetsAddVocabEntryTool(spreadsheet_id="test_id")
    add_callable = tool.get_callable()

    with pytest.raises(ValueError, match="Write verification failed"):
        add_callable(
            target_german="der Hund",
            gender="der",
            native_translation="dog",
            hint_disambiguation="[canine]",
        )

    # Rollback should write empty values back to A3:K3
    mock_client.write_range.assert_any_call("test_id", "A3:K3", [[""] * len(expected_row)])
