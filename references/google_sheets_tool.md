# Google Sheets Tool

The Google Sheets tool allows your agents to dynamically read from and write to Google Spreadsheets.

## Registration
The tool is implemented in `src/tools/google_sheet/tool.py` and registers two tools with the `ToolFactory`:
- `google_sheet_read`
- `google_sheet_write`

## Setup & Authentication

To use these tools, you need a Google Cloud Service Account with access to the Google Sheets API:
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Sheets API**.
3. Create a Service Account and download the JSON key file (`credentials.json`).
4. **Share your target Google Sheet** with the Service Account email address.

## Configuration

Configure the tools in your `configs/tools_config.yaml` file:

```yaml
tools:
  read_sheet:
    type: "google_sheet_read"
    config:
      spreadsheet_id: "1BxiMVs0XRX5nZYnPeZPAW_xyz" # Target Spreadsheet ID
      credentials_path: ".env/credentials.json"    # Path to your downloaded JSON key
  
  write_sheet:
    type: "google_sheet_write"
    config:
      spreadsheet_id: "1BxiMVs0XRX5nZYnPeZPAW_xyz"
      credentials_path: ".env/credentials.json"
```

*Note: If `credentials_path` is `null`, the tool will attempt to use Google Application Default Credentials.*

## Write Tool Safety Mechanisms

The `google_sheet_write` tool includes a built-in safety layer to prevent data corruption:
- **Pre-write Validation**: Before any data is modified, the tool reads and stores the original state of the target range.
- **Post-write Validation**: After writing, the tool reads the range again to verify that the dimensions (rows and columns) exactly match the expected dimensions of the newly written data.
- **Automatic Rollback**: If the post-write verification fails, the tool will automatically write the original data back to the sheet and raise a `ValueError`, keeping your data safe.

### Race Condition Limitations
> [!WARNING]
> Google Sheets API does not natively support locking cell ranges during a read-modify-write cycle. The automatic rollback mechanism may fail or cause data loss if another user or script modifies the exact same cell range simultaneously between the pre-write check and the rollback execution. For production use-cases with high concurrency, consider a more robust locking system.
