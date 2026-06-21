from unittest.mock import MagicMock, patch

import pytest

from src.tools.google_sheets import GoogleSheetsClient


@pytest.fixture
def mock_sheets_client():
    # Patch the google credentials and build methods to avoid real network requests
    with (
        patch("src.tools.google_sheets.google.auth.default") as mock_auth,
        patch("src.tools.google_sheets.build") as mock_build,
    ):
        mock_auth.return_value = (MagicMock(), "project-id")

        # Mock the service structure: service.spreadsheets().values().get().execute()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleSheetsClient()
        yield client, mock_service


def test_read_cell_success(mock_sheets_client):
    client, mock_service = mock_sheets_client

    # Configure the mock response for reading a cell
    mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
    mock_get.execute.return_value = {"values": [["Hello Cell"]]}

    # Act
    value = client.read_cell("spreadsheet-id-123", "Sheet1!A1")

    # Assert
    assert value == "Hello Cell"
    mock_service.spreadsheets.return_value.values.return_value.get.assert_called_once_with(
        spreadsheetId="spreadsheet-id-123",
        range="Sheet1!A1",
        valueRenderOption="FORMATTED_VALUE",
    )


def test_read_cell_empty(mock_sheets_client):
    client, mock_service = mock_sheets_client

    # Configure mock response for empty value
    mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
    mock_get.execute.return_value = {}

    # Act
    value = client.read_cell("spreadsheet-id-123", "Sheet1!B5")

    # Assert
    assert value is None


def test_write_cell_success(mock_sheets_client):
    client, mock_service = mock_sheets_client

    # Configure write mock response
    mock_update = mock_service.spreadsheets.return_value.values.return_value.update.return_value
    mock_update.execute.return_value = {"updatedCells": 1}

    # Act
    result = client.write_cell("spreadsheet-id-123", "Sheet1!B2", "New Value")

    # Assert
    assert result["updatedCells"] == 1
    mock_service.spreadsheets.return_value.values.return_value.update.assert_called_once_with(
        spreadsheetId="spreadsheet-id-123",
        range="Sheet1!B2",
        valueInputOption="USER_ENTERED",
        body={"values": [["New Value"]]},
    )


def test_read_batch(mock_sheets_client):
    client, mock_service = mock_sheets_client

    mock_batch_get = (
        mock_service.spreadsheets.return_value.values.return_value.batchGet.return_value
    )
    mock_batch_get.execute.return_value = {
        "valueRanges": [
            {"range": "Sheet1!A1:B2", "values": [["1", "2"], ["3", "4"]]},
            {"range": "Sheet1!D5", "values": [["100"]]},
        ]
    }

    # Act
    results = client.read_batch("spreadsheet-id-123", ["Sheet1!A1:B2", "Sheet1!D5"])

    # Assert
    assert results["Sheet1!A1:B2"] == [["1", "2"], ["3", "4"]]
    assert results["Sheet1!D5"] == [["100"]]
    mock_service.spreadsheets.return_value.values.return_value.batchGet.assert_called_once_with(
        spreadsheetId="spreadsheet-id-123",
        ranges=["Sheet1!A1:B2", "Sheet1!D5"],
        valueRenderOption="FORMATTED_VALUE",
    )


def test_write_batch(mock_sheets_client):
    client, mock_service = mock_sheets_client

    mock_batch_update = (
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value
    )
    expected_updated_cells = 5
    mock_batch_update.execute.return_value = {"totalUpdatedCells": expected_updated_cells}

    write_data = {"Sheet1!A1": [["NewItem"]], "Sheet1!B5:C6": [[1, 2], [3, 4]]}

    # Act
    result = client.write_batch("spreadsheet-id-123", write_data)

    # Assert
    assert result["totalUpdatedCells"] == expected_updated_cells
    mock_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="spreadsheet-id-123",
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": "Sheet1!A1", "values": [["NewItem"]]},
                {"range": "Sheet1!B5:C6", "values": [[1, 2], [3, 4]]},
            ],
        },
    )
