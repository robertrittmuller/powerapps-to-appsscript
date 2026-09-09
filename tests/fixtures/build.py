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
    add('ConcurrentSave', 'Button', {'X':20, 'Y':550, 'Width':220, 'Height':40,
        'Text':'"Save independent fields"', 'OnSelect':
        'Set(leftDone, false); Set(rightDone, false); Set(concurrentStatus, "saving"); '
        'Set(concurrentResult, Concurrent('
        'Patch(Contacts, First(Contacts), {FirstName: "Concurrent"}); Set(leftDone, true), '
        'Patch(Contacts, First(Contacts), {LastName: "Finished"}); Set(rightDone, true))); '
        'Set(concurrentStatus, If(concurrentResult And leftDone And rightDone, "complete", "incorrect"))'})
    add('ConcurrentFailure', 'Button', {'X':350, 'Y':550, 'Width':250, 'Height':40,
        'Text':'"Recover one branch failure"', 'OnSelect':
        'Set(leftDone, false); Set(rightDone, false); Set(concurrentStatus, "saving"); '
        'Set(concurrentStatus, IfError(Concurrent('
        'Find("x", "text", 0); Set(leftDone, true), '
        'Patch(Contacts, First(Contacts), {LastName: "Survivor"}); Set(rightDone, true)), "recovered")); '
        'Set(afterConcurrent, rightDone And Not(leftDone))'})
    add('ConcurrentStatus', 'Label', {'X':20, 'Y':610, 'Width':400, 'Height':40,'Text':'concurrentStatus'})
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


def dataverse_fixture_files() -> dict[str, str]:
    """Sanitized native export shapes, with source keys, choices and aliases."""
    def label(text):
        return {"UserLocalizedLabel": {"Label": text, "LanguageCode": 1033}}
    definitions = [
        ("msft_projectid", "Project", "Uniqueidentifier"), ("msft_name", "Name", "String"),
        ("msft_status", "Status", "Picklist"), ("msft_active", "Active", "Boolean"),
        ("msft_budget", "Budget", "Decimal"), ("msft_start", "Start Date", "DateTime"),
        ("msft_owner", "Owner", "Lookup"), ("msft_tags", "Tags", "MultiSelectPicklist"),
    ]
    attrs = [{"LogicalName": logical, "AttributeType": kind,
              "AttributeTypeName": {"Value": kind + "Type"}, "DisplayName": label(name),
              "IsValidForCreate": True, "IsValidForUpdate": logical != "msft_projectid",
              "RequiredLevel": {"Value": "SystemRequired" if logical == "msft_projectid" else "None"},
              "Targets": ["systemuser"] if kind == "Lookup" else []}
             for logical, name, kind in definitions]
    options = [{"Value": 0, "Label": label("Open")}, {"Value": 1, "Label": label("Closed")}]
    relation = {"ReferencingAttribute": "msft_owner", "ReferencedEntity": "systemuser", "ReferencedAttribute": "systemuserid"}
    definition = {"EntityMetadata": json.dumps({"LogicalName": "msft_project", "EntitySetName": "msft_projects",
        "PrimaryIdAttribute": "msft_projectid", "PrimaryNameAttribute": "msft_name", "Attributes": attrs,
        "ManyToOneRelationships": [relation]}),
        "PicklistOptionSetAttribute": json.dumps({"value": [{"LogicalName": "msft_status", "OptionSet": {"Options": options}}]}),
        "BooleanOptionSetAttribute": json.dumps({"value": [{"LogicalName": "msft_active", "OptionSet": {
            "TrueOption": {"Value": 1, "Label": label("Yes")}, "FalseOption": {"Value": 0, "Label": label("No")}}}]}),
        "MultiSelectPicklistOptionSetAttribute": json.dumps({"value": [{"LogicalName": "msft_tags", "OptionSet": {"Options": options}}]}),
        "Views": json.dumps({"value": [{"name": "Active projects", "fetchxml": "<fetch/>"}]})}
    rows = [{"msft_projectid": "project-one", "msft_name": "First project", "msft_status": 0, "msft_active": True, "msft_budget": 0},
            {"msft_projectid": "project-two", "msft_name": "Second project", "msft_status": 1, "msft_active": False, "msft_budget": 50}]
    sources = [{"Name": "Projects", "Type": "NativeCDSDataSourceInfo", "LogicalName": "msft_project",
                "TableDefinition": json.dumps(definition), "Data": json.dumps(rows),
                "NativeCDSDataSourceInfoNameMapping": {logical: name for logical, name, _ in definitions}},
               {"Name": "project_status", "DisplayName": "Project Status", "Type": "OptionSetInfo",
                "OptionSetInfoNameMapping": {"0": "Open", "1": "Closed"}},
               {"Name": "project_active", "DisplayName": "Project Active", "Type": "OptionSetInfo",
                "OptionSetIsBooleanValued": True, "OptionSetInfoNameMapping": {"0": "No", "1": "Yes"}},
               {"Name": "DirectoryService", "Type": "ServiceInfo"}, {"Name": "Project Views", "Type": "ViewInfo"}]
    def control(name, kind, props):
        return {"Name": name, "Template": {"Name": kind},
                "Rules": [{"Property": key, "InvariantScript": str(value)} for key, value in props.items()]}
    controls = [
        control("ContractName", "text", {"Default": "selectedProject.Name", "Mode": "TextMode.SingleLine",
            "X": 20, "Y": 20, "Width": 360, "Height": 44}),
        control("ContractChoice", "dropdown", {"Items": "Choices(Projects.Status)", "Default": "selectedProject.Status",
            "X": 400, "Y": 20, "Width": 200, "Height": 44}),
        control("ContractResult", "label", {"Text": "projectResult", "X": 20, "Y": 80, "Width": 360, "Height": 40}),
        control("ContractCount", "label", {"Text": "Text(CountRows(Projects))", "X": 400, "Y": 80, "Width": 200, "Height": 40}),
        control("ContractSave", "button", {"Text": '"Save selected project"', "X": 20, "Y": 140, "Width": 250, "Height": 44,
            "OnSelect": 'IfError(Set(selectedProject, Patch(Projects, selectedProject, {msft_name: ContractName.Text, msft_status: ContractChoice.Selected.Value, msft_active: \'Project Active\'.No})); Set(projectResult, "saved"), Set(projectResult, "save failed"))'}),
        control("ContractInvalid", "button", {"Text": '"Try invalid choice"', "X": 290, "Y": 140, "Width": 250, "Height": 44,
            "OnSelect": 'IfError(Patch(Projects, selectedProject, {Name: "Must not persist", Status: 999}); Set(projectResult, "unexpected"), Set(projectResult, "invalid choice"))'}),
        control("ContractNew", "button", {"Text": '"New project"', "X": 20, "Y": 200, "Width": 250, "Height": 44,
            "OnSelect": 'Set(selectedProject, Patch(Projects, Defaults(Projects), {Name: "New project", Status: \'Project Status\'.Open, Active: \'Project Active\'.Yes, Budget: 0, msft_start: Date(2026, 9, 9), Owner: {UserId: "user-1", FullName: "Grace"}, Tags: [0, 1]})); Set(projectResult, "created")'}),
        control("ContractDelete", "button", {"Text": '"Delete selected project"', "X": 290, "Y": 200, "Width": 250, "Height": 44,
            "OnSelect": 'Remove(Projects, selectedProject); Set(selectedProject, Last(Projects)); Set(projectResult, "deleted")'}),
        control('ContractKeySave','button',{'Text':'"Save by source key"','X':20,'Y':260,'Width':250,'Height':44,
            'OnSelect':'IfError(Set(selectedProject, Patch(Projects, {msft_projectid: selectedProject.Project, '
            'msft_name: ContractName.Text, msft_budget: 0, msft_active: false})); Set(projectResult, "key saved"), '
            'Set(projectResult, "key save failed"))'}),
        control('ContractKeyUpsert','button',{'Text':'"Upsert a fixed source key"','X':290,'Y':260,'Width':250,'Height':44,
            'OnSelect':'Set(selectedProject, Patch(Projects, {Project: "fixed-new-key", Name: ContractName.Text, Status: 0})); '
            'Set(projectResult, "key upserted")'}),
        control('ContractKeyInvalid','button',{'Text':'"Try a missing source key"','X':20,'Y':320,'Width':250,'Height':44,
            'OnSelect':'IfError(Patch(Projects, {Name: "Do not create"}); Set(projectResult, "unexpected"), Set(projectResult, "key required"))'}),
    ]
    return {"Properties.json": json.dumps({"Name": "FixtureDataverse"}),
        "Controls\\1.json": json.dumps({"TopParent": control("App", "appinfo", {
            "OnStart": 'Set(selectedProject, Last(Projects)); Set(projectResult, "ready")'})}),
        "Controls\\2.json": json.dumps({"TopParent": {**control("ContractScreen", "screen", {}), "Children": controls}}),
        "References\\DataSources.json": json.dumps({"DataSources": sources})}


def collection_alias_fixture_files() -> dict[str, str]:
    files = dataverse_fixture_files()
    data = json.loads(files['References\\DataSources.json'])
    projects = data['DataSources'][0]
    rows = json.loads(projects['Data'])
    for index, row in enumerate(rows):
        row['msft_owner'] = {'systemuserid':f'user-{index}', 'firstname':['Ada','Grace'][index]}
    projects['Data'] = json.dumps(rows)
    user_fields = [('systemuserid','User','Uniqueidentifier'),('firstname','First Name','String')]
    data['DataSources'].append({'Name':'Users','Type':'NativeCDSDataSourceInfo',
        'NativeCDSDataSourceInfoNameMapping':{key:name for key,name,_ in user_fields},
        'TableDefinition':json.dumps({'EntityMetadata':json.dumps({'LogicalName':'systemuser',
            'PrimaryIdAttribute':'systemuserid','Attributes':[{'LogicalName':key,'AttributeType':kind,
                'DisplayName':{'UserLocalizedLabel':{'Label':name}}} for key,name,kind in user_fields]})})})
    files['References\\DataSources.json'] = json.dumps(data)
    def control(name, kind, props, children=None):
        return {'Name':name, 'Template':{'Name':kind}, 'Rules':[
            {'Property':key,'InvariantScript':str(value)} for key,value in props.items()], 'Children':children or []}
    app = json.loads(files['Controls\\1.json'])
    for rule in app['TopParent']['Rules']:
        if rule['Property']=='OnStart':
            rule['InvariantScript']='Set(expandDrafts, false); ClearCollect(Drafts, Filter(Projects, false)); Collect(Drafts, {msft_projectid:"project-one",msft_name:"Draft one",msft_budget:0,msft_active:false}, {msft_projectid:"project-two",msft_name:"Draft two",msft_budget:0,msft_active:true}); Set(draftStatus, "ready")'
    files['Controls\\1.json']=json.dumps(app)
    screen=json.loads(files['Controls\\2.json'])
    screen['TopParent']['Children']=[
        control('DraftSummary','label',{'X':20,'Y':20,'Width':700,'Height':40,
            'Text':'Concat(Drafts, Name & ":" & Text(msft_budget), ", ")'}),
        control('DraftStatus','label',{'X':20,'Y':70,'Width':500,'Height':40,'Text':'draftStatus'}),
        control('DraftRows','gallery',{'X':20,'Y':130,'Width':600,'Height':300,'TemplateSize':80,'TemplatePadding':0,'Items':'Drafts'},[
            control('DraftTemplate','gallerytemplate',{},[
                control('DraftName','text',{'X':0,'Y':0,'Width':380,'Height':44,'Mode':'If(expandDrafts, TextMode.MultiLine, TextMode.SingleLine)',
                    'Default':'ThisItem.Name','AccessibleLabel':'"Draft name"',
                    'OnChange':'UpdateIf(Drafts, ThisItem.Project = Project, {msft_name: Self.Text})'}),
                control('SaveDraftRow','button',{'X':400,'Y':0,'Width':180,'Height':44,'Text':'"Save row and cache"',
                    'OnSelect':'Patch(Projects, LookUp(Projects, Project = ThisItem.Project), {Name: DraftName.Text}); SaveData(Drafts, "draft-cache"); Set(draftStatus, "saved")'}),
                control('DraftOwner','label',{'X':0,'Y':48,'Width':380,'Height':24,
                    'Text':"LookUp(Projects, Project = ThisItem.Project).Owner.'First Name'"}),
                control('NestedTemplate','gallery',{'X':580,'Y':50,'Width':10,'Height':10,'Visible':'false','Items':'Table()'},[
                    control('NestedCaption','label',{'Text':'"Nested template must not become an outer row"'})]),
            ])]),
        control('BumpDrafts','button',{'X':20,'Y':460,'Width':180,'Height':44,'Text':'"Increment budgets"',
            'OnSelect':'UpdateIf(Drafts, Budget >= 0, {msft_budget:Budget + 1}, true, {Budget:99})'}),
        control('RestoreDrafts','button',{'X':220,'Y':460,'Width':180,'Height':44,'Text':'"Restore cache"',
            'OnSelect':'Clear(Drafts); LoadData(Drafts, "draft-cache")'}),
        control('ConflictingDraft','button',{'X':420,'Y':460,'Width':200,'Height':44,'Text':'"Test invalid aliases"',
            'OnSelect':'IfError(ClearCollect(Drafts, {Name:"A",msft_name:"B"}), Set(draftStatus, "conflict retained draft"))'}),
        control('ToggleDraftMode','button',{'X':20,'Y':520,'Width':180,'Height':44,'Text':'"Toggle multiline"',
            'OnSelect':'Set(expandDrafts, !expandDrafts)'}),
        control('AppendDraft','button',{'X':220,'Y':520,'Width':180,'Height':44,'Text':'"Append draft"',
            'OnSelect':'Collect(Drafts, {msft_projectid:"project-three",msft_name:"Third draft",msft_budget:0})'}),
        control('StandaloneModeDraft','text',{'X':650,'Y':130,'Width':380,'Height':80,'Default':'"Standalone draft"',
            'Mode':'If(expandDrafts, TextMode.MultiLine, TextMode.SingleLine)',
            'OnChange':'Set(modeChanged, Self.Text)'}),
        control('ModeChanged','label',{'X':650,'Y':220,'Width':380,'Height':60,'Text':'modeChanged'}),
        control('MaskedExample','text',{'X':650,'Y':300,'Width':380,'Height':44,
            'Default':'"sample only"','Mode':'TextMode.Password'}),
    ]
    files['Controls\\2.json']=json.dumps(screen)
    files['Properties.json']=json.dumps({'Name':'FixtureCollectionAliases'})
    return files


def source_formula_fixture_files() -> dict[str, str]:
    """Complete MIT-licensed Microsoft formulas in a small UI test harness.

    Formula text and original names are preserved; the surrounding controls
    and collection data are test scaffolding, not a converted real app.
    See microsoft-formulas.json and MICROSOFT-LICENSE.txt for provenance.
    """
    formulas = json.loads((FIXTURE_DIR / "microsoft-formulas.json").read_text())
    def control(name, kind, props):
        return {name: {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}}
    children = [control("txtSetupSharePoint_URL", "TextInput", {
        "X": 20, "Y": 20, "Width": 820, "Height": 44, "Default": '""',
        "AccessibleLabel": '"SharePoint site URL"'})]
    for formula in formulas:
        children.append(control(formula["control"], "Label", {
            "X": 20, "Y": 130 if formula["app"] == "milestones" else 80,
            "Width": 950, "Height": 40, "Text": formula["raw"]}))
    # The real formula includes both today's timestamp and localized older dates.
    actions = [
        ("FormulaToday", 'ClearCollect(\'Project Work Items\', {\'Project Work item\': "work-1", \'Created On\': Now()}); Set(gblUserLanguage, "en-US")'),
        ("FormulaFrench", 'Set(gblUserLanguage, "fr-FR"); ClearCollect(colLocalization, {OOBTextID: "lblEditWorkItemCreatedOn1__locText", LocalizedText: "Créé le"})'),
        ("FormulaJapanese", 'Set(gblUserLanguage, "ja-JP"); Clear(colLocalization)'),
        ("FormulaOlder", 'ClearCollect(\'Project Work Items\', {\'Project Work item\': "work-1", \'Created On\': Date(2014, 9, 9)}); Set(gblUserLanguage, "en-US"); Clear(colLocalization)'),
    ]
    for i, (name, action) in enumerate(actions):
        children.append(control(name, "Button", {"X": 20 + 240 * i, "Y": 210,
            "Width": 220, "Height": 44, "Text": '"' + name + '"', "OnSelect": action}))
    return {
        "CanvasManifest.json": json.dumps({"Name": "FixtureSourceFormulas", "ScreenOrder": ["SourceFormulas"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {
            "OnStart": '=Set(gblUserLanguage, "en-US"); ClearCollect(colLocalization, Table()); Set(locSelectedWorkItem, {\'Project Work item\': "work-1"}); ' + actions[-1][1]}}}),
        "src/SourceFormulas.pa.yaml": json.dumps({"SourceFormulas": {"Control": "Screen", "Children": children}}),
    }


def canvas_fixture_files(scale_to_fit=False) -> dict[str, str]:
    """Responsive and fixed canvases with source formulas and manual containers."""
    def control(name, kind, props, children=None, variant=None):
        node = {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}
        if children is not None:
            node["Children"] = children
        if variant:
            node["Variant"] = variant
        return {name: node}
    screen_props = {
        "Width": "Max(App.Width, App.MinScreenWidth)",
        "Height": "Max(App.Height, App.MinScreenHeight)",
        "Size": "1 + CountRows(App.SizeBreakpoints) - CountIf(App.SizeBreakpoints, Value >= Self.Width)",
        "Orientation": "If(Self.Width < Self.Height, Layout.Vertical, Layout.Horizontal)",
        "Fill": 'If(ThemeToggle.Value, ColorValue("#ddeeff"), ColorValue("#f4f4f4"))',
    }
    nested = control("ManualPanel", "GroupContainer", {
        "X": 20, "Y": 160, "Width": "Parent.Width - 40", "Height": 180,
        "LayoutMode": "LayoutMode.Manual", "LayoutDirection": "LayoutDirection.Horizontal",
        "Fill": 'ColorValue("#ffffff")',
    }, [control("CanvasCard", "DataCard", {"X": 0, "Y": 0, "Width": "Parent.Width", "Height": "Parent.Height"}, [
        control("Draft", "TextInput", {"X": 20, "Y": 20, "Width": "Parent.Width - 40", "Height": 44,
            "Default": '"Keep this draft"', "AccessibleLabel": '"Draft text"'}),
        control("OpenDetails", "Button", {"X": 20, "Y": 100, "Width": "Parent.Width - 40", "Height": 44,
            "Text": '"Open details"', "OnSelect": "Set(chosenTheme, ThemeToggle.Value); Navigate('Details Screen')"}),
    ])])
    props = {"Name": "FixtureCanvas", "DocumentLayoutWidth": 1200, "DocumentLayoutHeight": 800,
             "DocumentLayoutScaleToFit": scale_to_fit, "DocumentLayoutMaintainAspectRatio": True,
             "DocumentLayoutLockOrientation": False, "DocumentLayoutOrientation": "landscape"}
    return {
        "Properties.json": json.dumps(props),
        "CanvasManifest.json": json.dumps({"Name": "FixtureCanvas", "ScreenOrder": ["Responsive Screen", "Details Screen"]}),
        "src/App.pa.yaml": json.dumps({"App": {"Control": "AppHost", "Properties": {
            "MinScreenWidth": "=320", "MinScreenHeight": "=400", "SizeBreakpoints": "=[600, 900, 1200, 1400]",
            "OnStart": "=Set(initialWidth, App.Width); Set(initialToggle, ThemeToggle.Value); Set(exitCount, 0)"}}}),
        "src/Responsive Screen.pa.yaml": json.dumps(control("Responsive Screen", "Screen", {
            **screen_props, "OnHidden": 'Set(exitCount, exitCount + 1); Set(exitScreenWidth, Self.Width); Set(exitDraft, Draft.Text)'}, [
            control("CanvasTitle", "Label", {"X": 20, "Y": 20, "Width": "Parent.Width - 40", "Height": 40,
                "Text": "Text(App.ActiveScreen.Width) & \" / \" & Text('Responsive Screen'.Size)"}),
            control("ThemeToggle", "Toggle", {"X": 20, "Y": 90, "Width": 44, "Height": 44, "Default": "false",
                "AccessibleLabel": '"Blue theme"'}),
            control("ThemeCaption", "Label", {"X": 80, "Y": 90, "Width": 200, "Height": 44,
                "Text": 'If(ThemeToggle.Value, "Blue theme", "Light theme")'}),
            nested,
            control("CaptionReference", "Label", {"X": 20, "Y": 360, "Width": "Parent.Width - 40", "Height": 40,
                "Text": 'OpenDetails.Text & ": " & Draft.Text'}),
            control("AutoPanel", "GroupContainer", {"X": 20, "Y": 430, "Width": "Parent.Width - 40", "Height": 48,
                "LayoutMode": "LayoutMode.Auto", "LayoutDirection": "LayoutDirection.Horizontal", "LayoutGap": 8}, [
                control("AutoFirst", "Label", {"X": 999, "Y": 999, "Width": 80, "Height": 40, "Text": '"Automatic"'}),
                control("AutoSecond", "Label", {"X": 999, "Y": 999, "Width": 80, "Height": 40, "Text": '"layout"'}),
            ]),
        ])),
        "src/Details Screen.pa.yaml": json.dumps(control("Details Screen", "Screen", {
            **screen_props, "OnVisible": 'Set(enteredAfterExit, exitCount > 0)'}, [
            control("DetailsTitle", "Label", {"X": 20, "Y": 20, "Width": "Parent.Width - 40", "Height": 44,
                "Text": 'If(chosenTheme, "Blue details", "Light details")'}),
            control("ReturnCanvas", "Button", {"X": 20, "Y": 90, "Width": "Parent.Width - 40", "Height": 44,
                "Text": '"Return"', "OnSelect": "Navigate('Responsive Screen')"}),
        ])),
    }


def card_layout_fixture_files() -> dict[str, str]:
    def control(name, kind, props, children=None):
        return {name:{'Control':kind, 'Properties':{key:'='+str(value) for key,value in props.items()},
                      'Children':children or []}}
    def card(name, x, y, width, height, fit, children=None, visible='true'):
        return control(name,'DataCard',{'X':x,'Y':y,'Width':width,'Height':height,
            'WidthFit':fit,'Visible':visible,'Fill':'ColorValue("#eef2f7")'},children)
    cards = [
        card('WideCard',400,0,'Parent.Width / 3',100,'true',[
            control('WideDraft','TextInput',{'X':8,'Y':8,'Width':'Parent.Width - 16','Height':40,
                'Default':'"Retain this draft"','AccessibleLabel':'"Card draft"'})]),
        card('FirstCard',0,0,120,80,'false',[
            control('FirstCaption','Label',{'X':8,'Y':8,'Width':104,'Height':40,'Text':'"First card"'})]),
        card('FullCard',0,1,'Parent.Width',60,'false',[
            control('BoundedTitle','Label',{'X':8,'Y':8,'Width':'Parent.Width - 16','Height':40,
                'Wrap':'false','Overflow':'Overflow.Hidden','Text':'"A long source title stays inside its label instead of painting across adjacent controls"'})]),
        card('LastCard',300,2,160,140,'true',[
            control('ScrollableText','Label',{'X':8,'Y':8,'Width':'Parent.Width - 16','Height':40,
                'Wrap':'true','Overflow':'Overflow.Scroll','Text':'"First line with enough words to wrap. Second line with enough words to wrap. Third line with more content to read. Final line is reachable by scrolling."'})]),
        card('HiddenCard',0,2,160,60,'true',visible='!hideCard'),
        card('FooterCard',0,5,'Parent.Width',90,'false',[
            control('FooterAction','Button',{'X':8,'Y':8,'Width':'Parent.Width - 16','Height':44,
                'Text':'"Read edited draft"','OnSelect':'Set(capturedDraft, WideDraft.Text)'}),
            control('CapturedDraft','Label',{'X':8,'Y':54,'Width':'Parent.Width - 16','Height':32,
                'Text':'capturedDraft'})]),
    ]
    return {
        'Properties.json':json.dumps({'Name':'FixtureCardLayout','DocumentLayoutWidth':640,
            'DocumentLayoutHeight':600,'DocumentLayoutScaleToFit':False}),
        'CanvasManifest.json':json.dumps({'Name':'FixtureCardLayout','ScreenOrder':['Card Screen']}),
        'src/App.pa.yaml':json.dumps(control('App','AppHost',{
            'MinScreenWidth':280,'MinScreenHeight':400,'OnStart':'Set(hideCard, false); Set(capturedDraft, "")'})),
        'src/Card Screen.pa.yaml':json.dumps(control('Card Screen','Screen',{
            'Width':'App.Width','Height':'App.Height'},[
            control('ToggleCard','Button',{'X':8,'Y':8,'Width':240,'Height':44,'Text':'"Toggle optional card"',
                'OnSelect':'Set(hideCard, !hideCard)'}),
            control('CardCanvas','fluidGrid',{'X':0,'Y':60,'Width':'Parent.Width','Height':'Parent.Height-60',
                'NumberOfColumns':2,'SnapToColumns':'false'},cards)])),
    }


def navigation_fixture_files() -> dict[str, str]:
    """Screen-local records, shadowing, and an awaited save after navigation."""
    def control(name, kind, props, children=None):
        node = {"Control": kind, "Properties": {k: "=" + str(v) for k, v in props.items()}}
        if children:
            node["Children"] = children
        return {name: node}
    def box(y, text, **props):
        return {"X": 20, "Y": y, "Width": 420, "Height": 44, "Text": text, **props}
    rows = control("NavigationRows", "Gallery", {
        "X": 20, "Y": 90, "Width": 440, "Height": 160, "Items": "Contacts",
        "TemplateSize": 64, "TemplatePadding": 0}, [
        control("NavigationTemplate", "GalleryTemplate", {}, [
            control("OpenContact", "Button", box(4, 'ThisItem.FirstName & " " & ThisItem.LastName',
                OnSelect="Navigate('Detail Screen', ScreenTransition.None, {currentItem: ThisItem, draftLabel: \"detail\", CamelCase: 0, enabled: false, 'quoted key': \"quoted\"})"))])])
    files = {
        "CanvasManifest.json": json.dumps({"Name": "FixtureNavigation", "ScreenOrder": ["Browse Screen", "Detail Screen", "Other Screen"]}),
        "src/App.pa.yaml": json.dumps(control("App", "AppHost", {"OnStart": 'Set(currentItem, "global"); Set(draftLabel, "global draft")'})),
        "src/Browse Screen.pa.yaml": json.dumps(control("Browse Screen", "Screen", {
            "OnVisible": 'UpdateContext({draftLabel: "browse"}); If(false, UpdateContext({currentItem: Blank()}))'}, [
            control("BrowseScope", "Label", box(20, 'draftLabel & ":" & If(IsBlank(currentItem), "blank", "leaked") & ":" & [@currentItem]')),
            rows,
        ])),
        "src/Detail Screen.pa.yaml": json.dumps(control("Detail Screen", "Screen", {
            "OnVisible": 'Set(enteredName, currentItem.FirstName); UpdateContext({visits: Coalesce(visits, 0) + 1})'}, [
            control("DetailTitle", "Label", box(20, 'currentItem.FirstName & " " & currentItem.LastName')),
            control("DetailFirst", "TextInput", {"X": 20, "Y": 90, "Width": 420, "Height": 44,
                "Default": "currentItem.FirstName", "AccessibleLabel": '"First name"'}),
            control("DetailStatus", "Label", box(160, 'draftLabel & ":" & Text(camelcase) & ":" & If(enabled, "enabled", "disabled") & ":" & \'quoted key\'')),
            control("SaveContact", "Button", box(230, '"Save contact"', OnSelect="Navigate('Other Screen'); UpdateContext({currentItem: Patch(Contacts, currentItem, {FirstName: DetailFirst.Text}), draftLabel: \"saved\"})")),
            control("ClearDetail", "Button", box(300, '"Clear local selection"', OnSelect='UpdateContext({currentItem: Blank()})')),
            control("DetailScope", "Label", box(370, 'If(IsBlank(currentItem), "blank", "selected") & ":" & [@currentItem] & ":" & Text(visits)')),
            control("BrowseAgain", "Button", box(440, '"Browse contacts"', OnSelect="Navigate('Browse Screen')")),
        ])),
        "src/Other Screen.pa.yaml": json.dumps(control("Other Screen", "Screen", {
            "OnVisible": 'UpdateContext({draftLabel: "other"})'}, [
            control("OtherScope", "Label", box(20, 'draftLabel & ":" & [@currentItem]')),
            control("HiddenDetail", "Label", box(90, 'DetailStatus.Text')),
            control("ReturnDetail", "Button", box(160, '"Return to contact"', OnSelect="Back()")),
        ])),
    }
    files["DataSources/Contacts.json"] = gallery_fixture_files()["DataSources/Contacts.json"]
    return files


VIEW_QUERY = '''<fetch version="1.0" distinct="false"><entity name="msft_project">
<attribute name="msft_name"/><attribute name="msft_projectid"/>
<filter type="and"><condition attribute="msft_status" operator="eq" value="0"/>
<filter type="or"><condition attribute="msft_active" operator="eq" value="1"/>
<condition attribute="msft_budget" operator="ge" value="10"/></filter></filter>
<order attribute="msft_budget" descending="true"/><order attribute="msft_name"/>
</entity></fetch>'''
VIEW_ID = '11111111-1111-1111-1111-111111111111'


def view_fixture_files() -> dict[str, str]:
    files = dataverse_fixture_files()
    app = json.loads(files['Controls\\1.json'])
    for rule in app['TopParent']['Rules']:
        if rule['Property'] == 'OnStart':
            rule['InvariantScript'] = 'Set(selectedProjectName, "")'
    files['Controls\\1.json'] = json.dumps(app)
    sources = json.loads(files['References\\DataSources.json'])['DataSources']
    view_source = next(source for source in sources if source['Type'] == 'ViewInfo')
    view_source.update(RelatedEntityName='Projects', ViewInfoNameMapping={VIEW_ID: 'Open by budget'})
    table = sources[0]
    records = json.loads(table['Data'])
    records.append({'msft_projectid':'project-three', 'msft_name':'Third project', 'msft_status':0, 'msft_active':False, 'msft_budget':20})
    table['Data'] = json.dumps(records)
    files['References\\DataSources.json'] = json.dumps({'DataSources': sources})
    def control(name, kind, y, props):
        return {'Name':name, 'Template':{'Name':kind}, 'Rules':[
            {'Property':key, 'InvariantScript':str(value)} for key,value in {
                'X':20, 'Y':y, 'Width':520, 'Height':44, **props}.items()]}
    view = "Filter(Projects, 'Project Views'.'Open by budget')"
    children = [
        control('ViewSearch','text',20,{'Default':'""','Mode':'TextMode.SingleLine','AccessibleLabel':'"Search projects"'}),
        control('ViewRows','label',90,{'Text':f'Concat(Search({view}, ViewSearch.Text, "msft_name"), Name, ", ")'}),
        control('ViewCount','label',160,{'Text':f'Text(CountRows(Filter(Projects, \'Project Views\'.\'Open by budget\', Budget > 0)))'}),
        control('OpenSecond','button',230,{'Text':'"Open second project"',
            'OnSelect':'Patch(Projects, LookUp(Projects, msft_projectid = "project-two"), {Status: 0})'}),
        control('SelectedProject','label',560,{'Text':'selectedProjectName'}),
    ]
    row_button = control('SelectProject', 'button', 0, {'X':0, 'Width':480,
        'Text':'ThisItem.Name', 'OnSelect':'Select(Parent)'})
    template = control('ProjectTemplate', 'gallerytemplate', 0,
        {'OnSelect':'Set(selectedProjectName, ThisItem.Name)'})
    template['Children'] = [row_button]
    gallery = control('ProjectGallery', 'gallery', 310,
        {'Height':230, 'TemplateSize':60, 'TemplatePadding':0, 'Items':view})
    gallery['Children'] = [template]
    children.append(gallery)
    screen=json.loads(files['Controls\\2.json'])
    screen['TopParent']['Children']=children
    files['Controls\\2.json']=json.dumps(screen)
    files['Properties.json']=json.dumps({'Name':'FixtureViews'})
    return files


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
    _write_msapp(FIXTURE_DIR / "fixtureDataverse.msapp", dataverse_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureSourceFormulas.msapp", source_formula_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureCanvas.msapp", canvas_fixture_files())
    _write_msapp(FIXTURE_DIR / "fixtureScaledCanvas.msapp", canvas_fixture_files(True))
    _write_msapp(FIXTURE_DIR / "fixtureNavigation.msapp", navigation_fixture_files())
    _write_msapp(FIXTURE_DIR / 'fixtureCardLayout.msapp', card_layout_fixture_files())
    _write_msapp(FIXTURE_DIR / 'fixtureCollectionAliases.msapp', collection_alias_fixture_files())
    _write_msapp(FIXTURE_DIR / 'fixtureViews.msapp', view_fixture_files())
    _write_msapp(FIXTURE_DIR / 'fixtureViews.solution.zip', {'customizations.xml':
        f'<ImportExportXml><Entities><Entity><savedqueries><savedquery><savedqueryid>{{{VIEW_ID}}}</savedqueryid><fetchxml>{VIEW_QUERY}</fetchxml></savedquery></savedqueries></Entity></Entities></ImportExportXml>'})


if __name__ == "__main__":
    build_fixtures()
    for f in sorted(FIXTURE_DIR.glob("*.msapp")):
        print(f.name)
