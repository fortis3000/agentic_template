import logging
from typing import Any, Dict, List, Optional

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VocabEntry(BaseModel):
    """Pydantic model representing a vocabulary entry in the Google Sheet."""

    w: str = Field(description="Unique ID based on the word and date (YYMMDD)")
    Target_German: str = Field(description="The German word or phrase")
    Gender: str = Field(description="Grammatical gender (der/die/das or empty)")
    Native_Translation: str = Field(description="The translation in English")
    Hint_Disambiguation: str = Field(default="")
    Theme_Context: str = Field(default="")
    Example_Sentence: str = Field(default="")
    Collocations: str = Field(default="")
    Antonym: str = Field(default="")
    Media: str = Field(default="")
    Tags: str = Field(default="")

    def to_row(self) -> List[str]:
        """Converts entry fields to list of strings matching column order."""
        return [
            self.w,
            self.Target_German,
            self.Gender,
            self.Native_Translation,
            self.Hint_Disambiguation,
            self.Theme_Context,
            self.Example_Sentence,
            self.Collocations,
            self.Antonym,
            self.Media,
            self.Tags,
        ]


class SheetDisplayer:
    """Structure to format and display Google Sheet contents."""

    @staticmethod
    def display_vocab_entries(raw_rows: List[List[Any]]) -> str:
        """Parses raw sheet rows, validates using VocabEntry, and formats as a Markdown table."""
        if not raw_rows:
            return "No data found."

        headers = [
            "w",
            "Target_German",
            "Gender",
            "Native_Translation",
            "Hint_Disambiguation",
            "Theme_Context",
            "Example_Sentence",
            "Collocations",
            "Antonym",
            "Media",
            "Tags",
        ]

        start_idx = 0
        if raw_rows and raw_rows[0] and raw_rows[0][0] == "w":
            start_idx = 1

        entries = []
        for row in raw_rows[start_idx:]:
            # Pad row to match 11 columns
            padded_row = row + [""] * (len(headers) - len(row))
            try:
                # Validate with Pydantic
                entry = VocabEntry(
                    w=padded_row[0],
                    Target_German=padded_row[1],
                    Gender=padded_row[2],
                    Native_Translation=padded_row[3],
                    Hint_Disambiguation=padded_row[4],
                    Theme_Context=padded_row[5],
                    Example_Sentence=padded_row[6],
                    Collocations=padded_row[7],
                    Antonym=padded_row[8],
                    Media=padded_row[9],
                    Tags=padded_row[10],
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Skipped invalid row {row}: {e}")

        # Construct Markdown Table
        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for entry in entries:
            row_vals = [getattr(entry, h) for h in headers]
            lines.append("| " + " | ".join(str(val) for val in row_vals) + " |")

        return "\n".join(lines)


class GoogleSheetsClient:
    """A highly reusable, optimal client wrapper for the Google Sheets API v4.

    Handles authentication, connection caching, and optimal batch operations to minimize API calls.
    """

    def __init__(self, credentials_path: Optional[str] = None, scopes: Optional[List[str]] = None):
        """Initializes the client with credentials.

        Args:
            credentials_path: Path to the service account JSON file. If None,
              falls back to Application Default Credentials.
            scopes: List of OAuth scopes. Defaults to
              ['https://www.googleapis.com/auth/spreadsheets'].
        """
        self.scopes = scopes or ["https://www.googleapis.com/auth/spreadsheets"]
        self.credentials_path = credentials_path
        self._creds = None
        self._service = None

    @property
    def credentials(self) -> Any:
        """Lazy-loads and caches authentication credentials."""
        if self._creds is None:
            if self.credentials_path:
                self._creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path, scopes=self.scopes
                )
            else:
                self._creds, _ = google.auth.default(scopes=self.scopes)

        # Refresh credentials if expired
        if self._creds and getattr(self._creds, "expired", False):
            if hasattr(self._creds, "refresh"):
                self._creds.refresh(Request())

        return self._creds

    @property
    def service(self) -> Any:
        """Lazy-loads and caches the Sheets API service client."""
        if self._service is None:
            self._service = build("sheets", "v4", credentials=self.credentials)
        return self._service

    def read_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        value_render_option: str = "FORMATTED_VALUE",
    ) -> List[List[Any]]:
        """Reads a contiguous range of cells.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range_name: A1 notation of the range (e.g. 'Sheet1!A1:B10').
            value_render_option: How values should be represented in the response.

        Returns:
            A 2D list of values representing the rows.
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueRenderOption=value_render_option,
                )
                .execute()
            )
            return result.get("values", [])
        except HttpError as error:
            logger.error(
                f"Failed to read range '{range_name}' from spreadsheet '{spreadsheet_id}': {error}"
            )
            raise

    def read_cell(
        self,
        spreadsheet_id: str,
        cell_address: str,
        value_render_option: str = "FORMATTED_VALUE",
    ) -> Optional[Any]:
        """Reads a single cell.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            cell_address: A1 notation of the cell (e.g. 'Sheet1!B5').

        Returns:
            The cell value, or None if empty.
        """
        values = self.read_range(spreadsheet_id, cell_address, value_render_option)
        if values and len(values) > 0 and len(values[0]) > 0:
            return values[0][0]
        return None

    def read_batch(
        self,
        spreadsheet_id: str,
        ranges: List[str],
        value_render_option: str = "FORMATTED_VALUE",
    ) -> Dict[str, List[List[Any]]]:
        """Reads multiple non-contiguous ranges in a single API call (optimal).

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            ranges: A list of A1 notations (e.g. ['Sheet1!A1:B2', 'Sheet1!D5']).
            value_render_option: How values should be represented in the response.

        Returns:
            A dictionary mapping range strings to their 2D list of values.
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .batchGet(
                    spreadsheetId=spreadsheet_id,
                    ranges=ranges,
                    valueRenderOption=value_render_option,
                )
                .execute()
            )
            value_ranges = result.get("valueRanges", [])
            return {vr.get("range"): vr.get("values", []) for vr in value_ranges}
        except HttpError as error:
            logger.error(f"Failed batch read for ranges {ranges}: {error}")
            raise

    def write_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> Dict[str, Any]:
        """Writes a contiguous block of values.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range_name: A1 notation of the range (e.g., 'Sheet1!B2').
            values: A 2D list of values to write.
            value_input_option: 'USER_ENTERED' (parses values) or 'RAW'.
        """
        try:
            body = {"values": values}
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body=body,
                )
                .execute()
            )
            return result
        except HttpError as error:
            logger.error(
                f"Failed to write range '{range_name}' to spreadsheet '{spreadsheet_id}': {error}"
            )
            raise

    def write_cell(
        self,
        spreadsheet_id: str,
        cell_address: str,
        value: Any,
        value_input_option: str = "USER_ENTERED",
    ) -> Dict[str, Any]:
        """Writes a single cell.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            cell_address: A1 notation of the cell (e.g., 'Sheet1!B2').
            value: The value to write.
            value_input_option: 'USER_ENTERED' (parses values) or 'RAW'.
        """
        return self.write_range(spreadsheet_id, cell_address, [[value]], value_input_option)

    def write_batch(
        self,
        spreadsheet_id: str,
        data: Dict[str, List[List[Any]]],
        value_input_option: str = "USER_ENTERED",
    ) -> Dict[str, Any]:
        """Writes multiple non-contiguous ranges in a single API call (optimal).

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            data: A dict mapping range strings to 2D lists of values. e.g., {'Sheet1!A1':
              [['NewItem']], 'Sheet1!B5:C6': [[1, 2], [3, 4]]}
            value_input_option: 'USER_ENTERED' (parses values) or 'RAW'.
        """
        try:
            body = {
                "valueInputOption": value_input_option,
                "data": [
                    {"range": range_name, "values": values} for range_name, values in data.items()
                ],
            }
            result = (
                self.service.spreadsheets()
                .values()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                .execute()
            )
            return result
        except HttpError as error:
            logger.error(f"Failed batch write to spreadsheet '{spreadsheet_id}': {error}")
            raise

    def append_row(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> Dict[str, Any]:
        """Appends a row to the sheet, automatically finding the next empty row.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range_name: A1 notation of the table/range to append to (e.g., 'A:K' or 'Sheet1!A:K').
            values: A 2D list containing the row(s) to write.
            value_input_option: 'USER_ENTERED' (parses values) or 'RAW'.
        """
        try:
            body = {"values": values}
            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body=body,
                )
                .execute()
            )
            return result
        except HttpError as error:
            logger.error(
                f"Failed to append row to range '{range_name}' in spreadsheet '{spreadsheet_id}': {error}"
            )
            raise
