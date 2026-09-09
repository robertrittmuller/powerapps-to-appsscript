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
  Properties:
    Width: =900
    Height: =600
  Children:
    - Form1:
        Control: Form
        Properties:
          X: =20
          Y: =20
          Width: =400
          Height: =220
          DataSource: =Contacts
          Item: =First(Contacts)
          DefaultMode: =FormMode.Edit
          OnSuccess: =Set(savedName, Form1.LastSubmit.LastName)
          OnFailure: =Set(saveError, Form1.Error)
        Children:
          - FirstNameCard:
              Control: DataCard
              Properties:
                X: =0
                Y: =0
                Width: =360
                Height: =80
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
                      Width: =320
                      Height: =40
          - LastNameCard:
              Control: DataCard
              Properties:
                X: =0
                Y: =100
                Width: =360
                Height: =80
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
                      Width: =320
                      Height: =40
    - ButtonNew:
        Control: Button
        Properties:
          Text: ="New"
          X: =20
          Y: =260
          Width: =100
          Height: =40
          OnSelect: =NewForm(Form1)
    - ButtonResetForm:
        Control: Button
        Properties:
          Text: ="Reset"
          X: =140
          Y: =260
          Width: =100
          Height: =40
          OnSelect: =ResetForm(Form1)
    - ButtonSubmit:
        Control: Button
        Properties:
          Text: ="Save"
          X: =260
          Y: =260
          Width: =100
          Height: =40
          OnSelect: =SubmitForm(Form1)
    - ComboPeople:
        Control: ComboBox
        Properties:
          Items: =Contacts
          X: =460
          Y: =20
          Width: =220
          Height: =120
          DisplayFields: =["FirstName"]
          DefaultSelectedItems: =[First(Contacts)]
          SelectMultiple: =true
    - ButtonDeleteLast:
        Control: Button
        Properties:
          X: =460
          Y: =160
          Width: =180
          Height: =40
          Text: ="Delete last contact"
          OnSelect: =Remove(Contacts, Last(Contacts))
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

APP_CHARTS_YAML = '''App:
  Control: AppHost
  Properties:
    OnStart: '=ClearCollect(Metrics, {Category: "Gain", Amount: 5}, {Category: "Loss", Amount: -5}, {Category: "Zero", Amount: 0}); Set(showChartLabels, false); Set(chartWidth, 320)'
'''

SCREEN_CHARTS_YAML = '''Charts:
  Control: Screen
  Children:
    - BusinessChart:
        Control: ColumnChart
        Properties:
          X: =20
          Y: =20
          Width: =chartWidth
          Height: =240
          Items: =Metrics
          ItemsLabels: ="Category"
          ItemsValues: ="Amount"
          ItemColorSet: =[RGBA(49,130,93,1),RGBA(212,96,104,1),RGBA(118,154,204,1)]
          ShowLabels: =showChartLabels
    - BusinessPie:
        Control: PieChart
        Properties:
          X: =20
          Y: =290
          Width: =320
          Height: =200
          Items: =Metrics
          ItemColorSet: =BusinessChart.ItemColorSet
          ShowLabels: =If(true, false, true)
    - BusinessLegend:
        Control: Legend
        Properties:
          X: =20
          Y: =510
          Width: =400
          Height: =40
          Items: =BusinessChart.SeriesLabels
    - ToggleChart:
        Control: Button
        Properties:
          X: =650
          Y: =20
          Width: =160
          Height: =40
          Text: ="Labels / size"
          OnSelect: =Set(showChartLabels, true); Set(chartWidth, 600)
    - ClearChart:
        Control: Button
        Properties:
          X: =650
          Y: =80
          Width: =160
          Height: =40
          Text: ="Clear"
          OnSelect: =Clear(Metrics)
'''


def scope_fixture_files() -> dict[str, str]:
    """Real formula shapes from Inspection/Employee Ideas, with local data.

    This is a focused regression fixture, not a substitute acceptance app.
    JSON is valid YAML and keeps quoted Power Fx identifiers unambiguous.
    """
    blue = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32'%3E%3Crect width='32' height='32' fill='blue'/%3E%3C/svg%3E"
    red = blue.replace("blue", "red")
    on_start = (
        'Set(tax, 5); Set(cutoff, 3); Set(limit, 9); '
        'ClearCollect(\'Scope Rows\', {Amount: 2}, {Amount: 5}, {Amount: 8}); '
        f'Set(gblSelectedLocation, {{\'Primary Image\': {{Full: "{blue}"}}}}); '
        f'Set(areaInspectionDefaultImage, "{red}"); Set(afterSave, "ready")'
    )
    children = []

    def add(name, kind, props, nested=None):
        control = {"Control": kind, "Properties": {key: "=" + str(value) for key, value in props.items()}}
        if nested:
            control["Children"] = nested
        children.append({name: control})

    add("ScopeTotal", "Label", {"X": 20, "Y": 20, "Width": 300, "Height": 40,
        "Text": 'With({rate: 2, info: {Value: 4}}, With({rate: 3}, Text(rate + info.Value + tax)))'})
    add("ScopeGallery", "Gallery", {"X": 20, "Y": 80, "Width": 300, "Height": 180,
        "TemplateSize": 60, "Items": "Filter('Scope Rows', Amount > cutoff, Amount < limit)"}, [{
            "ScopeRow": {"Control": "Label", "Properties": {"Width": "=200", "Height": "=40",
                "Text": '=With({Value: 3}, Text(Sum(Table({Value: 2}), ThisRecord.Value + ThisItem.Amount)))'}}}])
    add("ScopeImage", "Image", {"X": 350, "Y": 20, "Width": 64, "Height": 64,
        "Image": "If(IsBlank(gblSelectedLocation.'Primary Image'.Full), areaInspectionDefaultImage, gblSelectedLocation.'Primary Image'.Full)"})
    add("ClearScopeImage", "Button", {"X": 350, "Y": 100, "Width": 200, "Height": 40,
        "Text": '"Clear image"', "OnSelect": "Set(gblSelectedLocation, Blank())"})
    add("ScopeSave", "Button", {"X": 350, "Y": 160, "Width": 200, "Height": 40,
        "Text": '"Save contact"', "OnSelect": 'With({fallback: "failed"}, Set(saveResult, IfError(With({saved: Patch(Contacts, First(Contacts), {FirstName: "Updated"})}, saved.FirstName), fallback))); Set(afterSave, saveResult)'})
    add("ScopeSaveStatus", "Label", {"X": 350, "Y": 220, "Width": 200, "Height": 40, "Text": "afterSave"})
    add("LaunchValue", "Label", {"X": 20, "Y": 290, "Width": 800, "Height": 80, "Text": 'Param("recordId")'})
    add("LaunchCase", "Label", {"X": 20, "Y": 390, "Width": 200, "Height": 40,
        "Text": 'If(IsBlank(Param("RecordId")), "case-sensitive", "incorrect")'})
    add("LaunchLanguage", "Label", {"X": 350, "Y": 390, "Width": 200, "Height": 40, "Text": "Language()"})
    add("GroupedScopeTotal", "Label", {"X": 20, "Y": 490, "Width": 300, "Height": 40,
        "Text": 'Concat(AddColumns(GroupBy(AddColumns(\'Scope Rows\' As source, Band, If(source.Amount < 0, "negative", source.Amount > 3, "high", "low")), Band, Entries) As group, Total, Sum(group.Entries As entry, entry.Amount)), Band & ":" & Text(Total), ",")'})
    add("RemoveScopeRows", "Button", {"X": 350, "Y": 490, "Width": 200, "Height": 40,
        "Text": '"Remove matching row"',
        "OnSelect": "RemoveIf('Scope Rows' As candidate, candidate.Amount in Table({Amount: 5}).Amount, 'Scope Rows'[@Amount] < [@limit])"})
    return {
        "CanvasManifest.json": json.dumps({"Name": "FixtureScopes", "ScreenOrder": ["Scopes"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {"OnStart": "=" + on_start}}}),
        "src/Scopes.pa.yaml": json.dumps({"Scopes": {"Control": "Screen", "Children": children}}),
        "DataSources/Contacts.json": CONTACTS_JSON,
    }


def gallery_fixture_files() -> dict[str, str]:
    """Two persisted contacts with editable row controls and source actions."""
    def control(name, kind, props, children=None):
        node = {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}
        if children:
            node["Children"] = children
        return {name: node}

    row_children = [
        control("RowFirst", "TextInput", {"X": 8, "Y": 8, "Width": 180, "Height": 36,
            "Default": "contact.FirstName", "AccessibleLabel": '"First name"',
            "OnSelect": "Set(focusedId, ThisItem.ID)",
            "OnChange": 'Patch([@Contacts], contact, {FirstName: Self.Text}); Set(savedRow, RowFirst.Text)'}),
        control("RowLast", "TextInput", {"X": 200, "Y": 8, "Width": 180, "Height": 36,
            "Default": "ThisItem.LastName", "AccessibleLabel": '"Last name"',
            "OnSelect": "Set(focusedId, ThisItem.ID)",
            "DisplayMode": 'If(lockRows, DisplayMode.Disabled, DisplayMode.Edit)'}),
        control("RowPreview", "Label", {"X": 8, "Y": 52, "Width": 220, "Height": 32,
            "Text": 'RowFirst.Text & " " & RowLast.Text'}),
        control("RowSave", "Button", {"X": 390, "Y": 8, "Width": 100, "Height": 36,
            "Text": '"Save row"', "OnSelect": 'Patch([@Contacts], LookUp([@Contacts] As persisted, persisted.ID = contact.ID), {FirstName: RowFirst.Text, LastName: RowLast.Text}); Set(savedRow, RowFirst.Text); Select(Parent); Set(childFinished, true)'}),
        control("RowReset", "Button", {"X": 390, "Y": 52, "Width": 100, "Height": 32,
            "Text": '"Reset row"', "OnSelect": 'Reset(RowLast)'}),
        control("RowChoice", "ComboBox", {"X": 8, "Y": 94, "Width": 180, "Height": 34,
            "Items": "Contacts", "DisplayFields": '["FirstName"]',
            "DefaultSelectedItems": "[ThisItem]", "OnSelect": "Set(focusedId, ThisItem.ID)",
            "OnChange": 'Set(chosenName, RowChoice.Selected.FirstName)'}),
        control("RowImage", "Image", {"X": 240, "Y": 90, "Width": 32, "Height": 32,
            "Image": '"data:image/svg+xml," & EncodeUrl("<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'32\' height=\'32\'><rect width=\'32\' height=\'32\' fill=\'" & If(ThisItem.ID = "one", "blue", "red") & "\'/></svg>")'}),
    ]
    children = [
        control("ContactRows", "Gallery", {"X": 20, "Y": 20, "Width": 520, "Height": 360,
            "TemplateSize": 150, "TemplatePadding": 0,
            "Items": 'SortByColumns(Contacts, "ID", If(reverseRows, Descending, Ascending)) As contact',
            "OnSelect": 'Set(parentCalls, parentCalls + 1); Set(parentSawFinished, childFinished); Set(selectedName, contact.FirstName)'},
            [control("RowTemplate", "GalleryTemplate", {}, row_children)]),
        control("UnrelatedUpdate", "Button", {"X": 570, "Y": 20, "Width": 180, "Height": 40,
            "Text": '"Update counter"', "OnSelect": "Set(counter, counter + 1)"}),
        control("LockRows", "Button", {"X": 570, "Y": 80, "Width": 180, "Height": 40,
            "Text": '"Lock rows"', "OnSelect": "Set(lockRows, !lockRows)"}),
        control("SortRows", "Button", {"X": 570, "Y": 140, "Width": 180, "Height": 40,
            "Text": '"Reverse order"', "OnSelect": "Set(reverseRows, !reverseRows)"}),
    ]
    return {
        "CanvasManifest.json": json.dumps({"Name": "FixtureGallery", "ScreenOrder": ["GalleryScreen"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {
            "OnStart": "=Set(counter, 0); Set(lockRows, false); Set(parentCalls, 0); Set(childFinished, false); Set(reverseRows, false)"}}}),
        "src/GalleryScreen.pa.yaml": json.dumps({"GalleryScreen": {"Control": "Screen", "Children": children}}),
        "DataSources/Contacts.json": json.dumps({"Name": "Contacts", "Type": "StaticDataSourceInfo",
            "Fields": [], "SampleData": [
                {"ID": "one", "FirstName": "Ada", "LastName": "Lovelace"},
                {"ID": "two", "FirstName": "Grace", "LastName": "Hopper"}]}),
    }


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


def timer_fixture_files() -> dict[str, str]:
    def control(name, kind, props):
        return {name: {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}}
    loading = [control("LoadingMessage", "Label", {"Text": '"Loading contacts"', "Width": 240, "Height": 40}),
        control("LoadingTimer", "Timer", {"Duration": 250, "Start": "locStartTimer", "Visible": "false",
            "OnTimerStart": "Set(timerStarted, true)",
            "OnTimerEnd": 'ClearCollect(TimerRows, {Name: "Ready"}); Set(timerEnded, true); Navigate(ReadyScreen)'})]
    ready = [
        control("ReadyMessage", "Label", {"X": 20, "Y": 20, "Width": 300, "Height": 40, "Text": "First(TimerRows).Name"}),
        control("FocusInput", "TextInput", {"X": 20, "Y": 80, "Width": 300, "Height": 40, "Default": '""'}),
        control("FocusTimer", "Timer", {"Duration": 50, "AutoStart": "true", "Visible": "false", "OnTimerEnd": "SetFocus(FocusInput)"}),
        control("RepeatTimer", "Timer", {"X": 20, "Y": 140, "Width": 300, "Height": 40,
            "Duration": 100, "Start": "runTimer", "AutoPause": "true", "Repeat": "cycles < 3",
            "Text": 'Text(Self.Value, "0")', "OnTimerEnd": "Set(cycles, cycles + 1)"}),
        control("StartRepeat", "Button", {"X": 20, "Y": 200, "Width": 140, "Height": 40,
            "Text": '"Start"', "OnSelect": "Set(runTimer, true)"}),
        control("ResetRepeat", "Button", {"X": 180, "Y": 200, "Width": 140, "Height": 40,
            "Text": '"Reset"', "OnSelect": "Set(runTimer, false); Reset(RepeatTimer); Set(cycles, 0)"}),
        control("GoOther", "Button", {"X": 20, "Y": 260, "Width": 300, "Height": 40,
            "Text": '"Other screen"', "OnSelect": "Navigate(OtherScreen)"}),
    ]
    other = [control("ReturnReady", "Button", {"X": 20, "Y": 20, "Width": 300, "Height": 40,
        "Text": '"Return"', "OnSelect": "Back()"})]
    files = {
        "CanvasManifest.json": json.dumps({"Name": "FixtureTimer", "ScreenOrder": ["LoadingScreen", "ReadyScreen", "OtherScreen"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {
            "OnStart": "=/* source initialization */ Concurrent(Set(cycles, 0); Set(runTimer, false), Set(timerStarted, false))"}}}),
    }
    for name, children in [("LoadingScreen", loading), ("ReadyScreen", ready), ("OtherScreen", other)]:
        node = {"Control": "Screen", "Children": children}
        if name == "LoadingScreen":
            node["Properties"] = {"OnVisible": "=If(Not(false) And true, UpdateContext({locStartTimer: true}); Set(enteredLoading, true))"}
        files[f"src/{name}.pa.yaml"] = json.dumps({name: node})
    return files


def storage_fixture_files() -> dict[str, str]:
    """Inspection's local draft cache lifecycle, isolated from its connectors."""
    def control(name, kind, props):
        return {name: {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}}
    children = [
        control("DraftNote", "TextInput", {"X": 20, "Y": 20, "Width": 360, "Height": 44,
            "Default": 'Coalesce(First(Drafts).Note, "")', "AccessibleLabel": '"Inspection note"'}),
        control("DraftDate", "DatePicker", {"X": 450, "Y": 20, "Width": 220, "Height": 44,
            "DefaultDate": "First(Drafts).LoggedAt", "AccessibleLabel": '"Inspection date"'}),
        control("DraftDone", "CheckBox", {"X": 450, "Y": 80, "Width": 28, "Height": 28,
            "Default": "First(Drafts).Done", "AccessibleLabel": '"Inspection complete"'}),
        control("CacheStatus", "Label", {"X": 20, "Y": 80, "Width": 360, "Height": 40, "Text": "cacheStatus"}),
        control("DraftCount", "Label", {"X": 20, "Y": 130, "Width": 360, "Height": 40, "Text": "Text(CountRows(Drafts))"}),
        control("SaveDraft", "Button", {"X": 20, "Y": 190, "Width": 180, "Height": 44,
            "DisplayMode": "If(IsBlank(DraftNote.Text), DisplayMode.Disabled, DisplayMode.Edit)",
            "Text": '"Save draft"', "OnSelect": 'ClearCollect(Drafts, {Note: DraftNote.Text, Done: false, Count: 0, LoggedAt: Date(2026, 9, 9), Detail: {Code: "inspection"}}); IfError(SaveData(Drafts, "inspection-draft"); Set(cacheStatus, "saved"), Set(cacheStatus, "save failed"))'}),
        control("AppendDraft", "Button", {"X": 220, "Y": 190, "Width": 180, "Height": 44,
            "Text": '"Append saved draft"', "OnSelect": 'IfError(LoadData(Drafts, "inspection-draft"); Set(cacheStatus, "loaded"), Set(cacheStatus, "load failed"))'}),
        control("SaveBackup", "Button", {"X": 20, "Y": 250, "Width": 180, "Height": 44,
            "Text": '"Save backup"', "OnSelect": 'SaveData(Drafts, "backup"); Set(cacheStatus, "backup saved")'}),
        control("ClearDraft", "Button", {"X": 220, "Y": 250, "Width": 180, "Height": 44,
            "Text": '"Clear saved draft"', "OnSelect": 'ClearData("inspection-draft"); Set(cacheStatus, "draft cleared")'}),
        control("ClearAppCache", "Button", {"X": 20, "Y": 310, "Width": 380, "Height": 44,
            "Text": '"Clear all saved drafts"', "OnSelect": 'ClearData(); Set(cacheStatus, "cache cleared")'}),
        control("DraftReset", "Button", {"X": 20, "Y": 370, "Width": 180, "Height": 44,
            "Text": '"Reset note"', "OnSelect": 'Reset(DraftNote)'}),
        control("DraftUnrelated", "Button", {"X": 220, "Y": 370, "Width": 180, "Height": 44,
            "Text": '"Update status"', "OnSelect": 'Set(cacheStatus, "editing")'}),
    ]
    return {
        "CanvasManifest.json": json.dumps({"Name": "FixtureStorage", "ScreenOrder": ["DraftScreen"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {
            "OnStart": '=ClearCollect(Drafts, Table()); IfError(LoadData(Drafts, "inspection-draft", true); Set(cacheStatus, "ready"), Set(cacheStatus, "load failed"))'}}}),
        "src/DraftScreen.pa.yaml": json.dumps({"DraftScreen": {"Control": "Screen", "Children": children}}),
    }


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
    _write_msapp(
        FIXTURE_DIR / "fixtureCharts.msapp",
        {
            "CanvasManifest.json": json.dumps({"Name": "FixtureCharts", "ScreenOrder": ["Charts"]}),
            "src/App.pa.yaml": APP_CHARTS_YAML,
            "src/Charts.pa.yaml": SCREEN_CHARTS_YAML,
        },
    )
    _write_msapp(FIXTURE_DIR / "fixtureScopes.msapp", scope_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureGallery.msapp", gallery_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureTimer.msapp", timer_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureStorage.msapp", storage_fixture_files())


if __name__ == "__main__":
    build_fixtures()
    for f in sorted(FIXTURE_DIR.glob("*.msapp")):
        print(f.name)
