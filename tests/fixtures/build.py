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

# Fixture D mimics a real Studio export: Properties.json manifest, `Src\\`
# backslash entry names, a top-level `Screens:` wrapper, and an auxiliary
# _EditorState.pa.yaml.
APP_D_YAML = """Screens:
  HomeScreen:
    Properties:
      Fill: =RGBA(39, 113, 194, 1)
    Children:
      - Icon1:
          Control: Classic/Icon@2.5.0
          Properties:
            Color: =Switch(lblFeedback1.Text,"positive",Color.ForestGreen,Color.Bisque)
            Font: =Font.'Open Sans'
            X: =ColorFade(RGBA(56, 96, 178, 1), -20%) // trailing comment
      - TextInput1:
          Control: Classic/TextInput@2.3.2
          Properties:
            Default: =
            Reset: =gblReset
"""

EDITORSTATE_YAML = """EditorState:
  Container1:
    IsLocked: false
"""

APP_FORM_YAML = """App:
  Control: AppHost
  Properties:
    OnStart: '=Set(savedName, ""); Set(saveError, "")'
"""

SCREEN_FORM_YAML = """FormScreen:
  Control: Screen
  Properties: {}
  Children:
    - Form1:
        Control: Form
        Properties:
          DataSource: =Contacts
          Item: =First(Contacts)
          DefaultMode: =FormMode.Edit
          OnSuccess: =Set(savedName, Form1.LastSubmit.LastName)
          OnFailure: =Set(saveError, Form1.Error)
        Children:
          - FirstNameCard:
              Control: DataCard
              Properties:
                DataField: ="FirstName"
                DisplayName: ="First Name"
                Default: =ThisItem.FirstName
                Required: =false
                Update: =InputFirst.Text
              Children:
                - InputFirst:
                    Control: TextInput
                    Properties:
                      Default: =Parent.Default
          - LastNameCard:
              Control: DataCard
              Properties:
                DataField: ="LastName"
                DisplayName: ="Last Name"
                Default: =ThisItem.LastName
                Required: =true
                Update: =InputLast.Text
              Children:
                - InputLast:
                    Control: TextInput
                    Properties:
                      Default: =Parent.Default
    - ButtonNew:
        Control: Button
        Properties:
          Text: ="New"
          OnSelect: =NewForm(Form1)
    - ButtonResetForm:
        Control: Button
        Properties:
          Text: ="Reset"
          OnSelect: =ResetForm(Form1)
    - ButtonSubmit:
        Control: Button
        Properties:
          Text: ="Save"
          OnSelect: =SubmitForm(Form1)
    - ComboPeople:
        Control: ComboBox
        Properties:
          Items: =Contacts
          DisplayFields: =["FirstName"]
          DefaultSelectedItems: =[First(Contacts)]
          SelectMultiple: =true
"""

CONTACTS_JSON = json.dumps(
    {
        "Name": "Contacts",
        "Type": "StaticDataSourceInfo",
        "Fields": [],
        "SampleData": [{"FirstName": "Ada", "LastName": "Lovelace"}],
    },
    indent=2,
)


def _write_msapp(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files.items():
            # Keep tracked binary fixtures byte-stable across test runs. ZIP's
            # filename-only writestr overload otherwise embeds the wall clock.
            info = zipfile.ZipInfo(arcname, date_time=(2026, 9, 4, 15, 46, 4))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            zf.writestr(info, content)


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
    # Fixture D: real Studio-export shape (Properties.json, Src\, Screens:,
    # _EditorState auxiliary, versioned control types, empty '=' formulas)
    _write_msapp(
        FIXTURE_DIR / "fixtureD.msapp",
        {
            "Header.json": json.dumps({"DocVersion": "1.347"}),
            "Properties.json": json.dumps(
                {"Name": "FixtureD Studio Export", "Id": "d1d0"}
            ),
            "Src\\HomeScreen.pa.yaml": APP_D_YAML,
            "Src\\_EditorState.pa.yaml": EDITORSTATE_YAML,
        },
    )
    # Form fixture: schema inference from DataCards plus edit/new/reset,
    # required validation, create, OnSuccess/OnFailure, and LastSubmit.
    _write_msapp(
        FIXTURE_DIR / "fixtureForm.msapp",
        {
            "CanvasManifest.json": json.dumps(
                {"Name": "FixtureForm", "PublishInfo": {}, "ScreenOrder": ["FormScreen"]}
            ),
            "src/App.pa.yaml": APP_FORM_YAML,
            "src/FormScreen.pa.yaml": SCREEN_FORM_YAML,
            "DataSources/Contacts.json": CONTACTS_JSON,
        },
    )


if __name__ == "__main__":
    build_fixtures()
    for f in sorted(FIXTURE_DIR.glob("*.msapp")):
        print(f.name)
