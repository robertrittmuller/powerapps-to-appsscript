"""Build synthetic .msapp fixtures (zip of CanvasManifest.json + src/*.pa.yaml).

The .msapp container is a plain ZIP archive whose src/ folder holds pa.yaml
source files (see Microsoft's canvas-app YAML docs). These fixtures mirror
that structure with minimal content for testing.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent

APP_YAML = """App:
  Control: AppHost
  Properties:
    OnStart: =Set(greeting, "Hello"); Set(counter, 1)
"""

SCREEN1_YAML = """Screen1:
  Control: Screen
  Properties:
    OnVisible: =Set(visitedScreen1, true)
  Children:
    - Label1:
        Control: Label
        Properties:
          Text: =greeting
          X: =40
          Y: =40
    - TextInput1:
        Control: TextInput
        Properties:
          Default: ="type here"
          X: =40
          Y: =100
    - Button1:
        Control: Button
        Properties:
          Text: ="Next"
          X: =40
          Y: =160
          OnSelect: =Set(counter, counter + 1); Navigate(Screen2)
"""

SCREEN2_YAML = """Screen2:
  Control: Screen
  Properties: {}
  Children:
    - Label2:
        Control: Label
        Properties:
          Text: ="Screen 2"
          X: =40
          Y: =40
    - ButtonBack:
        Control: Button
        Properties:
          Text: ="Back"
          X: =40
          Y: =100
          OnSelect: =Back()
"""

SCREEN1B_YAML = """Screen1:
  Control: Screen
  Properties: {}
  Children:
    - Gallery1:
        Control: Gallery
        Properties:
          Items: =Filter(Tasks, Amount > 100 && Status = "Open")
          X: =0
          Y: =0
        Children:
          - LabelRow:
              Control: Label
              Properties:
                Text: =ThisItem.Name
          - BtnDelete:
              Control: Button
              Properties:
                Text: ="Delete"
                OnSelect: =Remove(Tasks, ThisItem)
    - TextInputName:
        Control: TextInput
        Properties:
          Default: =""
    - TextInputAmount:
        Control: TextInput
        Properties:
          Default: ="0"
    - ButtonAdd:
        Control: Button
        Properties:
          Text: ="Add"
          OnSelect: '=Patch(Tasks, Defaults(Tasks), {Name: TextInputName.Text, Amount: Value(TextInputAmount.Text), Status: "Open"}); Refresh(Tasks)'
    - LabelCount:
        Control: Label
        Properties:
          Text: =CountRows(Tasks)
"""

APPB_YAML = """App:
  Control: AppHost
  Properties:
    OnStart: =Set(maxAmount, 1000)
"""

TASKS_JSON = json.dumps(
    {
        "Name": "Tasks",
        "Type": "SharePointDataSource",
        "Table": "Tasks",
        "DataSourceInfo": "https://contoso.sharepoint.com/sites/demo",
    },
    indent=2,
)

APP_C_YAML = """App:
  Control: AppHost
  Properties:
    OnStart: '=Collect(LocalCache, {key: "tz", value: TimeZoneOffset()}); Set(mode, If(Hour(Now()) < 12, "am", "pm"))'
"""


def _write_msapp(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)


def build_fixtures() -> None:
    # Fixture A: navigation + globals, all rule-transpilable
    _write_msapp(
        FIXTURE_DIR / "fixtureA.msapp",
        {
            "CanvasManifest.json": json.dumps(
                {"Name": "FixtureA", "PublishInfo": {}, "ScreenOrder": ["Screen1", "Screen2"]}
            ),
            "src/App.pa.yaml": APP_YAML,
            "src/Screen1.pa.yaml": SCREEN1_YAML,
            "src/Screen2.pa.yaml": SCREEN2_YAML,
        },
    )
    # Fixture B: data source, gallery, Patch/Remove/Refresh
    _write_msapp(
        FIXTURE_DIR / "fixtureB.msapp",
        {
            "CanvasManifest.json": json.dumps(
                {"Name": "FixtureB", "PublishInfo": {}, "ScreenOrder": ["Screen1"]}
            ),
            "src/App.pa.yaml": APPB_YAML,
            "src/Screen1.pa.yaml": SCREEN1B_YAML,
            "DataSources/Tasks.json": TASKS_JSON,
        },
    )
    # Fixture C: exotic functions that need the LLM/stub path
    _write_msapp(
        FIXTURE_DIR / "fixtureC.msapp",
        {
            "CanvasManifest.json": json.dumps(
                {"Name": "FixtureC", "PublishInfo": {}, "ScreenOrder": ["Screen1"]}
            ),
            "src/App.pa.yaml": APP_C_YAML,
            "src/Screen1.pa.yaml": SCREEN1_YAML,
        },
    )


if __name__ == "__main__":
    build_fixtures()
    for f in sorted(FIXTURE_DIR.glob("*.msapp")):
        print(f.name)
