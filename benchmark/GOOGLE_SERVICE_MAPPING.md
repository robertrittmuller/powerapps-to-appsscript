# Microsoft service migration to Google

The user requires Microsoft dependencies to move to Google services where
possible. Keeping Microsoft Graph as the target backend is not the default.
An adapter must preserve the source workflow, report differences, and fail
explicitly when configuration, migration data, authorization or an operation
is missing. Empty successful responses cannot stand in for an unmigrated service.

| Source capability | Google target | Contract |
|---|---|---|
| Dataverse/SharePoint structured records | Google Sheets and Apps Script | Typed storage, source keys, relationships and migration ledger. Dataverse user/team ownership defaults to the migrated Google caller; explicit assignment updates derived owner columns. This does not reproduce source security privileges. |
| Planner shared plans, buckets and assigned tasks | Google Sheets and Apps Script task-board adapter | Implemented for eight operations below. Explicit Google-user mapping and plan/task migration are required. Generated-server and Chromium tests preserve IDs, membership checks, buckets, assignments, progress, dates and description writes. |
| Personal task lists and tasks that fit the native API | Google Tasks | Candidate native adapter; shared assignments, bucket semantics and due-time fidelity must not be claimed. |
| Teams team/channel selectors and notifications | Native Google Chat | Implemented four operations with explicit source-ID/space mappings, native membership checks and deterministic HTML-to-Markdown translation. Generated-server, Chromium and unchanged Employee Ideas notification tests use native API fixtures; live delivery remains unverified. |
| Office365Users/Microsoft365Users search, profiles and photos | Native Google People domain directory plus migrated user mapping | Implemented SearchUser, UserProfileV2 and UserPhotoV2. Generated-server and Chromium assignment tests use explicit native API fixtures; live domain access remains unverified. |
| Files and attachments | Google Drive | Candidate storage and access adapter with upload/download evidence. |

## Dataverse ownership and Google callers

For native `ownerid` fields exported as Owner, generated create operations resolve
the active Google email against exactly one migrated Dataverse Users record.
Original user keys remain the stored identity. Explicit user/team owners must
resolve to migrated records; assignments update Owning User/Team and the exported
owner name/type. Ordinary edits retain ownership. Read-only derived owner columns
cannot independently change it. Validation, identity and write failures occur
before a partial row write. Both the ledger and data contract retain this adapter;
validation rejects silently dropped ownership metadata.

The Dataverse Users table uses its own source key and `internalemailaddress`
mapping. Office365Users' Microsoft-directory IDs can differ from Dataverse user
IDs, so its private Google People mapping remains separate. Import Users before
creating owned business records. The adapter stores key/name/email snapshots;
source security roles, assignment privileges, cascading ownership, business units,
audit timestamps and status defaults remain unimplemented. Workbook permissions
and the generated API do not reproduce Dataverse row security.

The unchanged Milestones app previously created ownerless settings, missed them
in its My Project User Setting view and repeated onboarding after every reload.
It now passes 19 checks covering first-run dismissal, reload, a second simulated
Google user and return to the first user, with separate persisted settings and
zero runtime errors. Project creation remains a failed probe because editable
milestone row values are not yet preserved correctly.
See Microsoft's [default record ownership contract](https://learn.microsoft.com/en-us/dotnet/api/microsoft.xrm.sdk.iorganizationservice.create?view=dataverse-sdk-latest).

## Planner implementation scope

The pinned Inspection, Inspection Manager and Review Inspections exports use
eight Planner operations: `ListMyPlansV2`, `ListGroupPlans`, `ListBucketsV3`,
`ListTasksV3`, `ListTasks`, `ListMyTasks`, `CreateTaskV3` and `UpdateTaskDetails`.
Inspection creates a task with a bucket, due date and semicolon-separated
assignee emails, then saves its description. These are the first adapter
acceptance cases. Source formulas and export bytes must remain unchanged.

Google Tasks has no API for creating tasks assigned from Chat/Docs. Assignment
metadata is read-only, and the due field discards the time of day. A native
Tasks-only replacement would therefore lose required source functionality.
The shared-board adapter uses Google Sheets as its authoritative store and
the converted Apps Script UI as its task interface. This does not imply that
the board appears in the native Google Tasks UI.

Every supported operation needs generated-server execution and a browser
journey with actual persisted records. Missing migration, unknown IDs, denied
membership and failed writes must remain errors. A private migration entry
point must not allow browser callers to grant themselves plan access.

The Planner subset now passes generated-server and Chromium tests. The fixture
creates an assigned task, preserves due time and description, selects the saved
row, edits its description, reloads, rejects a nonmember assignee and recovers
from injected write failures. It checks input labels and visible/readable controls.
Inspection's unchanged source passes all five first-action checks with an
explicitly authored migrated board. That proves only its loading/first action;
the complete inspection/task-creation workflow is still unassessed.

Generated projects include an operator-edited, private `PlannerMigration.gs`
entry point and `planner-migration.md` with the import schema. Existing migration
files survive reconversion. Reads use a cache for synchronous value bindings;
pending results are Blank, failures propagate, and app writes invalidate older
snapshots. This does not implement push updates for other users' changes.

Planner roles, assignment audit metadata, ordering hints, categories and external
notifications are not reproduced. The canonical service name must be `Planner`;
connector aliases and additional operations remain gaps. Live Google deployment,
authorization, contention and quota behavior have not been verified.
Plan checks apply to the server API; users with workbook access can bypass those
checks by editing storage directly. An app executing as its owner may lack the
active user's email, particularly across domains; missing identity is denied.
An app executing as the accessing user requires their workbook permissions.
Deployment must establish both usable identity and the intended storage access
boundary. See Google's [Session identity contract](https://developers.google.com/apps-script/reference/base/session)
and [web-app execution modes](https://developers.google.com/apps-script/guides/web).

## Native Google directory implementation

Both exported service names route to Google People: V1 SearchUser returns a
profile array through searchDirectoryPeople/listDirectoryPeople pagination;
UserProfileV2 and UserPhotoV2 resolve mapped identities through People.get.
Returned IDs retain the original Microsoft identity, while mail/principal names
use the mapped Google email. Names, organization, location and phones come from
native primary fields. A custom photo returns its Google HTTPS URL; an absent
custom photo is Blank. This is an approximation of Microsoft's binary photo API.

Google prefix matching, directory visibility and supported profile fields differ
from Microsoft. Unmapped identities, ambiguous primary fields, unsupported
selected fields, permission/API errors and pagination limits fail explicitly.
An editor-only DirectoryMigration.gs imports validated IDs, Google emails,
resource names and optional old-email aliases into reserved storage. Operator
edits survive reconversion. The manifest enables People v1, directory.readonly
and userinfo.email; owner-delegated or unidentified directory access is denied.
The accessing user needs both Google domain-directory and workbook permissions.

The generated Chromium fixture searches, handles revoked permissions, selects
the correct native profile/photo, excludes the assigned person from the picker,
creates a task with the preserved source user ID, and verifies persistence after
reload. Photo and write failures recover without an unintended assignment or
task. Keyboard activation, input labeling, visible geometry and image decoding
are checked. Native API responses and the photo image are authored test fixtures;
live Google authorization, visibility, URL lifetime and quotas remain unverified.
No full real-app workflow is inferred from this fixture.

Contracts: Microsoft's [Office 365 Users connector](https://learn.microsoft.com/en-us/connectors/office365users/),
Google's [directory guide](https://developers.google.com/people/v1/directory),
[directory search](https://developers.google.com/people/api/rest/v1/people/searchDirectoryPeople),
[directory listing](https://developers.google.com/people/api/rest/v1/people/listDirectoryPeople),
[person lookup](https://developers.google.com/people/api/rest/v1/people/get), and
[Apps Script People service](https://developers.google.com/apps-script/advanced/people).

## Native Google Chat implementation

The six pinned Microsoft exports contain four Teams operations: GetAllTeams,
GetTeam, GetChannelsForGroup and PostMessageToChannelV3. GetAllTeams lists joined
teams. Each source team maps to a named Chat anchor space; each channel maps to a
named space, optionally its own team's anchor. IDs stay unchanged in formulas,
while names/descriptions come from Google. The converted UI retains the logical
hierarchy; native Google Chat has no equivalent team/channel hierarchy.

The private ChatMigration.gs import validates all mappings before one write,
refuses re-import and preserves operator edits across reconversion. The manifest
enables Chat v1 and the chat.spaces.readonly/chat.messages.create scopes alongside
People when both are declared. Deploy as the identified accessing user with the
Chat API, Cloud project and OAuth configuration completed. Workbook editors can
change mappings; native joined-space membership and posting permissions remain
the final access check. Missing migration, unknown IDs, pagination limits, denied
membership and native API errors cannot become empty success.

Notifications use user-authenticated text messages with explicit CommonMark
syntax, generally available since August 7, 2026. Subjects become a bold first
paragraph. A bounded deterministic parser preserves source text, line breaks,
simple emphasis, paragraphs and HTTP(S)/mailto links; unsupported markup and
options fail before posting. Literal text is escaped against unintended formatting
or mentions. Payload size is checked in UTF-8 bytes. Each post makes one create
request with a request ID; uncertain outcomes require inspection before manual
retry. Native message IDs are returned. Rich HTML, attachments, native Teams
roles/settings, connector aliases and other message operations remain gaps.

The Chromium fixture selects teams/channels by readable labels while preserving
source IDs, checks dropdown Value in ordinary controls and gallery rows, posts a
notification, reloads, rejects unsupported content and recovers from denied API
calls. The unchanged Employee Ideas mobile app also passes 31 checks with explicit
space mappings and an active settings record: its actual Teams formula reaches
native Chat create, retains submitted data, and does not repost after reload.
Both use explicit API response fixtures; no real messages were sent. Live Google
authorization, native message rendering and complete app usability remain open.

Contracts: [Microsoft Teams connector](https://learn.microsoft.com/en-us/connectors/teams/),
[Apps Script Chat service](https://developers.google.com/apps-script/advanced/chat),
[joined spaces](https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces/list),
[message creation](https://developers.google.com/workspace/chat/api/reference/rest/v1/spaces.messages/create),
[message formatting](https://developers.google.com/workspace/chat/format-messages),
[Chat release notes](https://developers.google.com/workspace/chat/release-notes), and
[dropdown Value](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/controls/control-drop-down).

The remaining candidate adapters above are planned. No real app has complete
conversion acceptance; current evidence is in
[the progress report](PROGRESS_2026-09-09.md).

Sources: Google's [Tasks resource](https://developers.google.com/tasks/reference/rest/v1/tasks)
and [task creation contract](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/insert);
Microsoft's [Planner connector contract](https://learn.microsoft.com/en-us/connectors/planner/).
