"""Intermediate representation for a parsed canvas app."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FxExpr(BaseModel):
    """A Power Fx expression attached to a control property."""

    raw: str = ""  # original Power Fx (without the leading '=')
    kind: Literal["value", "behavior"] = "value"
    js: str | None = None  # transpiled JS; None when unsupported
    # Translation and emission are deliberately separate. Syntactically valid
    # JS is not a converted feature until synthesis actually wires it into the
    # generated runtime.
    translation_status: Literal["pending", "rule", "llm", "stubbed"] = "pending"
    emission_status: Literal[
        "pending", "emitted", "approximated", "ignored", "unsupported"
    ] = "pending"
    fidelity_note: str = ""
    blocked_dependencies: list[str] = Field(default_factory=list)
    approximations: list[str] = Field(default_factory=list)
    # Names in a reusable definition resolve within its particular instance.
    # Keep the source formula intact: strings, comments and row fields are not renamed.
    control_aliases: dict[str, str] = Field(default_factory=dict)
    component_owner: str | None = None
    component_private: bool = False


class SupportEntry(BaseModel):
    """One row of the fidelity ledger."""

    subject: str
    status: Literal["full", "partial", "unmapped", "stubbed"]
    detail: str = ""


class FieldDef(BaseModel):
    name: str
    type: str = "text"  # text | number | date | bool | choice | choices | lookup | unsupported
    logical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_type: str | None = None
    choices: list[dict] = Field(default_factory=list)  # name + typed value
    lookup_targets: list[str] = Field(default_factory=list)
    required_level: str | None = None
    writable_create: bool | None = None
    writable_update: bool | None = None


class DataSource(BaseModel):
    name: str
    origin: str = "other"  # sharepoint | excel | dataverse | collection | other
    fields: list[FieldDef] = Field(default_factory=list)
    # Embedded rows from StaticDataSourceInfo sources (keys already normalized
    # to the JS field-name convention) — used to seed the generated workbook.
    sample_data: list[dict] = Field(default_factory=list)
    logical_name: str | None = None
    primary_key: str | None = None  # source field name, normalized when emitted
    aliases: list[str] = Field(default_factory=list)
    option_values: list[dict] = Field(default_factory=list)
    # Retain source relationships/views for explicit follow-up; preservation
    # of metadata does not claim that Dataverse services execute in Sheets.
    metadata: dict = Field(default_factory=dict)


class ControlNode(BaseModel):
    name: str
    type: str
    variant: str | None = None
    # Exported template metadata, not inferred from the rendered HTML tag.
    primary_output: str | None = None
    # Legacy canvas-component instances point at a reusable definition. The
    # adapter expands the definition's child tree under the instance and keeps
    # the declared input names so synthesis can expose them to child formulas.
    component_template: str | None = None
    component_name: str | None = None
    component_library: str | None = None
    component_error: str | None = None
    component_inputs: list[str] = Field(default_factory=list)
    properties: dict[str, FxExpr] = Field(default_factory=dict)
    children: list["ControlNode"] = Field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class ScreenNode(BaseModel):
    name: str
    on_visible: FxExpr | None = None
    properties: dict[str, FxExpr] = Field(default_factory=dict)
    context_vars: list[str] = Field(default_factory=list)
    controls: list[ControlNode] = Field(default_factory=list)

    def walk_controls(self):
        for c in self.controls:
            yield from c.walk()


class AppIR(BaseModel):
    name: str
    on_start: FxExpr | None = None
    properties: dict[str, FxExpr] = Field(default_factory=dict)
    named_formulas: dict[str, FxExpr] = Field(default_factory=dict)
    named_formula_error: str | None = None
    layout: dict = Field(default_factory=dict)
    power_fx_v1: bool = False
    screens: list[ScreenNode] = Field(default_factory=list)
    data_sources: list[DataSource] = Field(default_factory=list)
    global_vars: list[str] = Field(default_factory=list)
    choice_fields: list[str] = Field(default_factory=list)  # 'DataSource.Field'
    view_sets: dict[str, dict] = Field(default_factory=dict)
    source_metadata: dict = Field(default_factory=dict)
    support_matrix: list[SupportEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Local image resources embedded in the .msapp, keyed by the Power Apps
    # resource name and encoded as browser-safe data URIs.  Keeping these in
    # the IR lets HtmlService render packaged assets without relying on the
    # expired docserver URLs found in older exports.
    media_resources: dict[str, str] = Field(default_factory=dict)
    # Safe defaults: signed-in users execute as themselves. Public/deployer
    # execution must be an explicit conversion choice.
    webapp_access: Literal["MYSELF", "DOMAIN", "ANYONE", "ANYONE_ANONYMOUS"] = "ANYONE"
    webapp_execute_as: Literal["USER_ACCESSING", "USER_DEPLOYING"] = "USER_ACCESSING"
    # Screen-order fallback when App.StartScreen is blank or fails.
    start_screen: str | None = None
