import json

from src.utils.logger import get_logger


def test_get_logger_json_format(capsys):
    # Reset logger handlers because they are cached by name
    logger = get_logger("json_logger")
    logger.info("Hello, world!")

    captured = capsys.readouterr()
    log_data = json.loads(captured.out)

    assert log_data["levelname"] == "INFO"
    assert log_data["name"] == "json_logger"
    assert log_data["message"] == "Hello, world!"
    assert "asctime" in log_data
