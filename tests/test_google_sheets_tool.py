from unittest.mock import MagicMock, patch

import pytest

from src.tools.google_sheet.tool import GoogleSheetsReadTool, GoogleSheetsWriteTool

EXPECTED_CALLS = 2


@patch("src.tools.google_sheet.tool.GoogleSheetsClient")
def test_google_sheet_read_tool(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.read_range.return_value = [["A", "B"], ["C", "D"]]

    tool = GoogleSheetsReadTool(spreadsheet_id="test_id")
    read_callable = tool.get_callable()

    result = read_callable("Sheet1!A1:B2")

    assert result == [["A", "B"], ["C", "D"]]
    mock_client.read_range.assert_called_once_with("test_id", "Sheet1!A1:B2")


@patch("src.tools.google_sheet.tool.GoogleSheetsClient")
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
    # Expected calls: read old, write new, read new
    assert mock_client.read_range.call_count == EXPECTED_CALLS
    mock_client.write_range.assert_called_once_with(
        "test_id", "Sheet1!A1:B2", [["NewA", "NewB"], ["NewC", "NewD"]]
    )


@patch("src.tools.google_sheet.tool.GoogleSheetsClient")
def test_google_sheet_write_tool_dimension_mismatch(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # Pre-check returns 2x2.
    # Post-check returns 1x1 (mismatch from expected 2x2).
    mock_client.read_range.side_effect = [[["OldA", "OldB"], ["OldC", "OldD"]], [["JustA"]]]

    tool = GoogleSheetsWriteTool(spreadsheet_id="test_id")
    write_callable = tool.get_callable()

    with pytest.raises(ValueError, match="Dimensions mismatch"):
        write_callable("Sheet1!A1:B2", [["NewA", "NewB"], ["NewC", "NewD"]])

    # Rollback should be triggered: writing back the original data
    assert mock_client.write_range.call_count == EXPECTED_CALLS
    mock_client.write_range.assert_any_call(
        "test_id", "Sheet1!A1:B2", [["OldA", "OldB"], ["OldC", "OldD"]]
    )
