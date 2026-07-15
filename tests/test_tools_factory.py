import pytest

from src.tools.base import BaseTool, ToolFactory

EXPECTED_VALUE = 42


@pytest.fixture(autouse=True)
def clear_registry():
    saved = dict(ToolFactory._registry)
    ToolFactory._registry = {}
    yield
    ToolFactory._registry = saved


def test_tool_registration_and_creation():
    @ToolFactory.register("dummy_tool")
    class DummyTool(BaseTool):
        def __init__(self, value: int):
            self.value = value

        def get_callable(self):
            def execute():
                return self.value

            return execute

    assert "dummy_tool" in ToolFactory._registry

    tool_instance = ToolFactory.create("dummy_tool", {"value": EXPECTED_VALUE})
    assert isinstance(tool_instance, DummyTool)
    assert tool_instance.value == EXPECTED_VALUE

    executable = tool_instance.get_callable()
    assert executable() == EXPECTED_VALUE


def test_create_unregistered_tool():
    with pytest.raises(ValueError, match="Tool type 'unregistered' is not registered"):
        ToolFactory.create("unregistered", {})


def test_load_from_yaml(tmp_path):
    @ToolFactory.register("yaml_tool")
    class YamlTool(BaseTool):
        def __init__(self, msg: str):
            self.msg = msg

        def get_callable(self):
            def execute():
                return self.msg

            return execute

    # Create dummy yaml file
    config_file = tmp_path / "tools.yaml"
    config_file.write_text("""
tools:
  my_tool:
    type: "yaml_tool"
    config:
      msg: "hello yaml"
""")

    registry = ToolFactory.load_from_yaml(str(config_file))

    assert "my_tool" in registry
    assert callable(registry["my_tool"])
    assert registry["my_tool"]() == "hello yaml"
