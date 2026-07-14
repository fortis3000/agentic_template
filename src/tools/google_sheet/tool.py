import logging
from typing import Any, Callable, Dict, List

from src.tools.base import BaseTool, ToolFactory
from src.tools.google_sheet.google_sheets import GoogleSheetsClient

logger = logging.getLogger(__name__)


@ToolFactory.register("google_sheet_read")
class GoogleSheetsReadTool(BaseTool):
    """Tool for reading data from a Google Sheet."""

    def __init__(self, spreadsheet_id: str, credentials_path: str | None = None):
        self.client = GoogleSheetsClient(credentials_path=credentials_path)
        self.spreadsheet_id = spreadsheet_id

    def get_callable(self) -> Callable:
        def read_google_sheet(range_name: str) -> List[List[Any]]:
            """Reads a range from the configured Google Sheet.

            Args:
                range_name: A1 notation of the range (e.g., 'Sheet1!A1:B10').

            Returns:
                A 2D list of values representing the rows and columns.
            """
            return self.client.read_range(self.spreadsheet_id, range_name)

        return read_google_sheet


@ToolFactory.register("google_sheet_write")
class GoogleSheetsWriteTool(BaseTool):
    """Tool for writing data to a Google Sheet with validation and rollback."""

    def __init__(self, spreadsheet_id: str, credentials_path: str | None = None):
        self.client = GoogleSheetsClient(credentials_path=credentials_path)
        self.spreadsheet_id = spreadsheet_id

    def get_callable(self) -> Callable:
        def write_google_sheet(range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
            """Writes a contiguous block of values to the configured Google Sheet.

            Performs a pre-write check to store original values and a post-write check
            to ensure dimensions match expectations. If validation fails, original data
            is restored automatically.

            Args:
                range_name: A1 notation of the range (e.g., 'Sheet1!A1:B2').
                values: A 2D list of values to write.

            Returns:
                The API response dictionary.

            Raises:
                ValueError: If the post-write verification fails.
            """
            # 1. Pre-check: read original data for rollback
            try:
                original_values = self.client.read_range(self.spreadsheet_id, range_name)
            except Exception as e:
                logger.error(f"Failed to read original data before write: {e}")
                raise ValueError(f"Pre-write validation failed: {e}")

            expected_rows = len(values)
            expected_cols = max(len(row) for row in values) if values else 0

            # 2. Perform write
            try:
                result = self.client.write_range(self.spreadsheet_id, range_name, values)
            except Exception as e:
                logger.error(f"Failed to write data: {e}")
                raise ValueError(f"Write operation failed: {e}")

            # 3. Post-check: Verify new dimensions
            try:
                new_values = self.client.read_range(self.spreadsheet_id, range_name)
            except Exception as e:
                logger.error(f"Failed to read data for post-write verification: {e}")
                raise ValueError(f"Post-write verification read failed: {e}")

            actual_rows = len(new_values)
            actual_cols = max(len(row) for row in new_values) if new_values else 0

            if actual_rows != expected_rows or actual_cols != expected_cols:
                # Mismatch found, trigger rollback
                logger.warning(
                    f"Dimension mismatch! Expected {expected_rows}x{expected_cols}, "
                    f"got {actual_rows}x{actual_cols}. Triggering rollback..."
                )
                try:
                    self.client.write_range(self.spreadsheet_id, range_name, original_values)
                    logger.info("Rollback successful.")
                except Exception as rollback_err:
                    logger.critical(
                        f"Rollback failed! Sheet may be in corrupted state. Error: {rollback_err}"
                    )
                    raise ValueError(f"Rollback failed: {rollback_err}")

                raise ValueError(
                    f"Write verification failed. Dimensions mismatch. "
                    f"Expected {expected_rows}x{expected_cols}, got {actual_rows}x{actual_cols}. "
                    "Original data has been restored."
                )

            return result

        return write_google_sheet


@ToolFactory.register("google_sheet_add_vocab_entry")
class GoogleSheetsAddVocabEntryTool(BaseTool):
    """Tool for adding a new vocabulary entry to the Google Sheet."""

    def __init__(self, spreadsheet_id: str, credentials_path: str | None = None):
        self.client = GoogleSheetsClient(credentials_path=credentials_path)
        self.spreadsheet_id = spreadsheet_id

    def get_callable(self) -> Callable:
        def add_vocab_entry(
            target_german: str,
            gender: str,
            native_translation: str,
            hint_disambiguation: str = "",
        ) -> Dict[str, Any]:
            """Adds a new vocabulary entry to the configured Google Sheet.

            Generates a unique ID (e.g. vocab_word_01) and appends the entry
            to the end of the table automatically.

            Args:
                target_german: The German word or phrase (e.g. 'die Katze').
                gender: The grammatical gender (e.g. 'die', 'der', 'das', or empty).
                native_translation: The English translation (e.g. 'cat').
                hint_disambiguation: Optional usage hint or disambiguation.

            Returns:
                A dictionary indicating success and details of the written row.
            """
            # 1. Read existing rows to determine the next empty row
            try:
                existing_rows = self.client.read_range(self.spreadsheet_id, "A1:E500")
            except Exception as e:
                logger.error(f"Failed to read sheet before appending: {e}")
                raise ValueError(f"Failed to read existing rows: {e}")

            last_row_num = len(existing_rows)
            next_row_num = last_row_num + 1

            # 2. Format unique ID
            # Strip gender prefixes if present to get clean word for ID
            clean_word = target_german.lower()
            for prefix in ["der ", "die ", "das ", "den ", "dem ", "des "]:
                if clean_word.startswith(prefix):
                    clean_word = clean_word[len(prefix) :]
                    break
            # Replace spaces and special characters
            clean_id_suffix = "".join(c if c.isalnum() else "_" for c in clean_word).strip("_")
            vocab_id = f"vocab_{clean_id_suffix}_01"

            new_row = [vocab_id, target_german, gender, native_translation, hint_disambiguation]

            # 3. Write row
            write_range = f"A{next_row_num}:E{next_row_num}"
            try:
                result = self.client.write_range(self.spreadsheet_id, write_range, [new_row])
            except Exception as e:
                logger.error(f"Failed to write new entry: {e}")
                raise ValueError(f"Failed to write new entry: {e}")

            # 4. Verify post-write
            try:
                verification_row = self.client.read_range(self.spreadsheet_id, write_range)
            except Exception as e:
                logger.error(f"Failed to read back for verification: {e}")
                raise ValueError(f"Post-write verification read failed: {e}")

            if not verification_row or verification_row[0] != new_row:
                # Attempt rollback by writing empty cells or old data
                logger.warning(
                    "Verification failed. Row did not match expected contents. Attempting rollback..."
                )
                try:
                    self.client.write_range(
                        self.spreadsheet_id, write_range, [["", "", "", "", ""]]
                    )
                except Exception as rollback_err:
                    logger.critical(f"Rollback failed: {rollback_err}")
                raise ValueError(
                    "Write verification failed: read-back row did not match written row."
                )

            return {
                "success": True,
                "row_number": next_row_num,
                "written_entry": {
                    "w": vocab_id,
                    "Target_German": target_german,
                    "Gender": gender,
                    "Native_Translation": native_translation,
                    "Hint_Disambiguation": hint_disambiguation,
                },
                "api_response": result,
            }

        return add_vocab_entry
