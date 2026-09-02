"""Intermediate representation for a parsed canvas app."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FxExpr(BaseModel):
    """A Power Fx expression attached to a control property."""

    raw: str = ""  # original Power Fx (without the leading '=')
    kind: Literal["value", "behavior"] = "value"
    js: str | None = None  # transpiled JS; None when unsupported


class SupportEntry(BaseModel):
    """One row of the fidelity ledger."""

    subject: str
    status: Literal["full", "partial", "unmapped", "stubbed"]
    detail: str = ""


class FieldDef(BaseModel):
    name: str
    type: str = "text"  # text | number | date | bool


class DataSource(BaseModel):
    name: str
    origin: str = "other"  # sharepoint | excel | dataverse | collection | other
    fields: list[FieldDef] = Field(default_factory=list)
    # Embedded rows from StaticDataSourceInfo sources (keys already normalized
    # to the JS field-name convention) — used to seed the generated workbook.
    sample_data: list[dict] = Field(default_factory=list)


class ControlNode(BaseModel):
    name: str
    type: str
    variant: str | None = None
    properties: dict[str, FxExpr] = Field(default_factory=dict)
    children: list["ControlNode"] = Field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class ScreenNode(BaseModel):
    name: str
    on_visible: FxExpr | None = None
    controls: list[ControlNode] = Field(default_factory=list)

    def walk_controls(self):
        for c in self.controls:
            yield from c.walk()


class AppIR(BaseModel):
    name: str
    on_start: FxExpr | None = None
    screens: list[ScreenNode] = Field(default_factory=list)
    data_sources: list[DataSource] = Field(default_factory=list)
    global_vars: list[str] = Field(default_factory=list)
    choice_fields: list[str] = Field(default_factory=list)  # 'DataSource.Field'
    support_matrix: list[SupportEntry] = Field(default_factory=list)
