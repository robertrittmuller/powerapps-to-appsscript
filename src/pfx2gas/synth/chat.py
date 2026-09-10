"""Native Google Chat adapter for migrated Microsoft team/channel workflows."""

SERVER = r'''
var CHAT_STORE_ = '__pfx2gas_chat';

function hasChat_() {
  return Object.keys(GOOGLE_SERVICE_ADAPTERS).some(function (name) { return GOOGLE_SERVICE_ADAPTERS[name].target === 'google-chat'; });
}
function setupChat_(workbook) {
  if (!hasChat_() || workbook.getSheetByName(CHAT_STORE_)) return;
  var sheet=workbook.insertSheet(CHAT_STORE_);
  sheet.getRange(1,1,1,3).setValues([['kind','id','json']]); sheet.setFrozenRows(1);
}
function chatText_(value,label) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(label+' must be nonempty text');
  return value;
}
function chatFields_(value,keys,label) {
  assertRecord(value,label);
  Object.keys(value).forEach(function (key) { if (!keys.includes(key)) throw new Error('Unsupported '+label+' field: '+key); });
}
function validateChatMappings_(data) {
  chatFields_(data,['teams','channels'],'Chat migration');
  if (!Array.isArray(data.teams) || !Array.isArray(data.channels)) throw new Error('Chat migration requires teams and channels arrays');
  var teams=new Map(),anchors=new Map(),channels=new Set(),spaces=new Set();
  data.teams.forEach(function (team) {
    chatFields_(team,['id','space_name'],'team mapping');
    chatText_(team.id,'Source team ID');
    if (teams.has(team.id)) throw new Error('Duplicate source team ID');
    if (typeof team.space_name !== 'string' || !/^spaces\/[A-Za-z0-9_-]+$/.test(team.space_name) || anchors.has(team.space_name))
      throw new Error('Invalid or duplicate team anchor space');
    teams.set(team.id,team); anchors.set(team.space_name,team.id);
  });
  data.channels.forEach(function (channel) {
    chatFields_(channel,['id','team_id','space_name'],'channel mapping');
    chatText_(channel.id,'Source channel ID');
    if (!teams.has(channel.team_id)) throw new Error('Channel requires a mapped source team');
    var key=JSON.stringify([channel.team_id,channel.id]);
    if (channels.has(key)) throw new Error('Duplicate source channel ID within a team');
    channels.add(key);
    if (typeof channel.space_name !== 'string' || !/^spaces\/[A-Za-z0-9_-]+$/.test(channel.space_name) || spaces.has(channel.space_name))
      throw new Error('Invalid or duplicate channel space');
    if (anchors.has(channel.space_name) && anchors.get(channel.space_name)!==channel.team_id)
      throw new Error('Channel cannot use another team anchor space');
    spaces.add(channel.space_name);
  });
  data.teams.concat(data.channels).forEach(function (record) {
    if (JSON.stringify(record).length>49000) throw new Error('Chat mapping exceeds the Sheets cell limit');
  });
  return data;
}
function chatMappings_() {
  var sheet=ss().getSheetByName(CHAT_STORE_);
  if (!sheet) throw new Error('Chat migration is not configured; run setup() and import team/channel mappings');
  var rows=sheet.getDataRange().getValues(),data={teams:[],channels:[]},seen=new Set(),ready=false;
  if (JSON.stringify(rows[0])!==JSON.stringify(['kind','id','json'])) throw new Error('Invalid Chat storage headers');
  rows.slice(1).forEach(function (row) {
    if (row.every(function (cell) { return cell===''; })) return;
    var key=JSON.stringify([row[0],row[1]]),value;
    if (seen.has(key)) throw new Error('Duplicate Chat storage key'); seen.add(key);
    try { value=JSON.parse(row[2]); } catch (_) { throw new Error('Invalid Chat storage JSON'); }
    if (row[0]==='config' && row[1]==='v1' && value && value.ready===true) { ready=true; return; }
    if (!value || !['teams','channels'].includes(row[0])) throw new Error('Invalid Chat storage record');
    var expected=row[0]==='teams' ? value.id : JSON.stringify([value.team_id,value.id]);
    if (row[1]!==expected) throw new Error('Mismatched Chat storage record ID');
    data[row[0]].push(value);
  });
  validateChatMappings_(data);
  return {configured:ready,data:data};
}
function importChat_(data) {
  if (!hasChat_()) throw new Error('Chat adapter is not declared by this app');
  validateChatMappings_(data);
  data=JSON.parse(JSON.stringify(data));
  return withDataWriteLock_(function () {
    var existing=chatMappings_();
    if (existing.configured || existing.data.teams.length || existing.data.channels.length)
      throw new Error('Chat storage is already initialized or requires administrator repair');
    var rows=data.teams.map(function (team) { return ['teams',team.id,JSON.stringify(team)]; })
      .concat(data.channels.map(function (channel) { return ['channels',JSON.stringify([channel.team_id,channel.id]),JSON.stringify(channel)]; }));
    rows.push(['config','v1',JSON.stringify({ready:true})]);
    ss().getSheetByName(CHAT_STORE_).getRange(2,1,rows.length,3).setValues(rows);
    return {ok:true,teams:data.teams.length,channels:data.channels.length};
  });
}
function chatSession_() {
  var active=(Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  var effective=(Session.getEffectiveUser().getEmail() || '').trim().toLowerCase();
  if (!active || active!==effective) throw new Error('Chat requires the identified accessing Google user; owner-delegated access is not supported');
  if (typeof Chat==='undefined' || !Chat.Spaces) throw new Error('Enable the Google Chat advanced service and configure its Cloud project');
}
function chatJoinedSpaces_() {
  var spaces=new Map(),tokens=new Set(),token,deadline=Date.now()+20000;
  for (var page=0;page<100;page++) {
    if (Date.now()>deadline) throw new Error('Chat pagination exceeded the request budget');
    var options={pageSize:1000,filter:'spaceType = "SPACE"'};
    if (token) options.pageToken=token;
    var response=Chat.Spaces.list(options);
    assertRecord(response,'Google Chat space list');
    if (response.spaces!==undefined && !Array.isArray(response.spaces)) throw new Error('Invalid Google Chat spaces');
    (response.spaces || []).forEach(function (space) {
      assertRecord(space,'Google Chat space');
      if (typeof space.name!=='string' || !/^spaces\/[A-Za-z0-9_-]+$/.test(space.name) || space.spaceType!=='SPACE')
        throw new Error('Invalid named Google Chat space');
      if (spaces.has(space.name)) throw new Error('Repeated Google Chat space; retry the lookup');
      chatText_(space.displayName,'Google Chat space name'); spaces.set(space.name,space);
    });
    if (spaces.size>10000) throw new Error('Chat spaces exceed the 10000-result adapter limit');
    token=response.nextPageToken;
    if (token===undefined || token==='') return spaces;
    if (typeof token!=='string' || tokens.has(token)) throw new Error('Invalid or repeated Google Chat page token');
    tokens.add(token);
  }
  throw new Error('Chat pagination exceeded the page limit');
}
function chatSpaceRecord_(mapping,spaces) {
  var space=spaces.get(mapping.space_name);
  if (!space) throw new Error('Access denied: join the mapped Google Chat space');
  return {id:mapping.id,display_name:space.displayName,
    description:space.spaceDetails && space.spaceDetails.description || null,
    web_url:space.spaceUri || null};
}
function chatEscape_(text) {
  // CommonMark backslash escapes prevent source text becoming formatting or mentions.
  return text.replace(/[\\`*_{}\[\]<>#!~|+.&()-]/g,'\\$&');
}
function chatEntities_(text) {
  var named={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:'\u00a0',ndash:'\u2013',mdash:'\u2014',
    hellip:'\u2026',copy:'\u00a9',reg:'\u00ae',trade:'\u2122',bull:'\u2022',
    lsquo:'\u2018',rsquo:'\u2019',ldquo:'\u201c',rdquo:'\u201d'};
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z][a-z0-9]*);/gi,function (entity,key) {
    if (Object.prototype.hasOwnProperty.call(named,key)) return named[key];
    if (key[0]==='#') {
      var point=key[1].toLowerCase()==='x' ? parseInt(key.slice(2),16) : Number(key.slice(1));
      if (point>0 && point<=0x10ffff && !(point>=0xd800 && point<=0xdfff)) return String.fromCodePoint(point);
    }
    throw new Error('Unsupported HTML entity in Chat notification: '+entity);
  });
}
function chatHtml_(html) {
  // A deliberately bounded HTML subset, parsed without executing source markup.
  // Unknown tags/attributes fail before posting instead of silently dropping content.
  var root={tag:'root',children:[]},stack=[root],offset=0,count=0;
  var token=/<(?:[^<>"']|"[^"]*"|'[^']*')*>|[^<]+/g,match;
  while ((match=token.exec(html))) {
    if (match.index!==offset || ++count>10000) throw new Error('Malformed or oversized Chat HTML');
    offset=token.lastIndex;
    var part=match[0],parent=stack[stack.length-1];
    if (part[0]!=='<') { parent.children.push(chatEntities_(part).replace(/[\t\r\n ]+/g,' ')); continue; }
    var tag=part.match(/^<\s*(\/?)\s*([a-z][a-z0-9]*)\b([\s\S]*?)>$/i);
    if (!tag) throw new Error('Unsupported Chat HTML markup');
    var closing=!!tag[1],name=tag[2].toLowerCase(),attributes=tag[3].trim();
    if (!['b','strong','i','em','br','p','div','a'].includes(name)) throw new Error('Unsupported Chat HTML tag: '+name);
    if (name==='br') {
      if (attributes && attributes!=='/') throw new Error('Unsupported Chat HTML break attributes');
      if (!closing) parent.children.push({tag:'br',children:[]});
      continue; // Accept the exported Inspection app's <br></br> spelling.
    }
    if (closing) {
      if (attributes || stack.length===1 || parent.tag!==name) throw new Error('Mismatched Chat HTML closing tag');
      stack.pop(); continue;
    }
    var node={tag:name,children:[]};
    if (['b','strong','i','em'].includes(name) && stack.some(function (item) { return ['b','strong','i','em'].includes(item.tag); }))
      throw new Error('Nested emphasis requires review before Chat posting');
    if (name==='a') {
      var href=attributes.match(/^href\s*=\s*(?:"([^"]*)"|'([^']*)')$/i);
      if (!href || stack.some(function (item) { return item.tag==='a'; })) throw new Error('Unsupported Chat HTML link attributes or nesting');
      node.url=chatEntities_(href[1]===undefined ? href[2] : href[1]);
      if (!/^(https?:\/\/[^/\s]+|mailto:[^\s@]+@[^\s@]+)(?:[^\s]*)$/i.test(node.url) || /[<>\x00-\x20\x7f]/.test(node.url))
        throw new Error('Unsupported Chat link URL');
      node.url=node.url.replace(/[\\()]/g,function (char) { return '%'+char.charCodeAt(0).toString(16).toUpperCase(); });
      node.url=node.url.replace(/&/g,'&amp;'); // One CommonMark entity decode must preserve the actual URL.
    } else if (attributes) throw new Error('Unsupported Chat HTML attributes: '+name);
    if (stack.length>100) throw new Error('Chat HTML nesting exceeds the adapter limit');
    parent.children.push(node); stack.push(node);
  }
  if (offset!==html.length || stack.length!==1) throw new Error('Malformed or unclosed Chat HTML');
  function render(node) {
    if (typeof node==='string') return chatEscape_(node);
    if (node.tag==='br') return '  \n';
    var inside=node.children.map(render).join('');
    if (node.tag==='root') return inside;
    if (node.tag==='p' || node.tag==='div') return '\n\n'+inside.trim()+'\n\n';
    var edges=inside.match(/^(\s*)([\s\S]*?)(\s*)$/),body=edges[2];
    if (!body) return inside;
    if (node.tag==='a') return edges[1]+'['+body+']('+node.url+')'+edges[3];
    if (body.includes('\n')) throw new Error('Multiline emphasis requires review before Chat posting');
    var marker=['b','strong'].includes(node.tag) ? '**' : '*';
    return edges[1]+marker+body+marker+edges[3];
  }
  return render(root).replace(/\n{3,}/g,'\n\n').trim();
}
function chatMessage_(body,options) {
  chatFields_(body,['content','content_type'],'Chat message body');
  options=options===undefined ? {} : options;
  chatFields_(options,['subject'],'Chat message options');
  if (typeof body.content!=='string' || body.content.length>128000) throw new Error('Chat content must be text within the adapter limit');
  var type=body.content_type===undefined ? 'text' : body.content_type;
  if (typeof type!=='string' || !['text','html'].includes(type.toLowerCase())) throw new Error('Unsupported Chat content type');
  var subject=options.subject==null ? '' : options.subject;
  if (typeof subject!=='string' || subject.length>128000 || /[\r\n]/.test(subject)) throw new Error('Chat subject must be single-line text');
  var content=type.toLowerCase()==='html' ? chatHtml_(body.content) : chatEscape_(body.content).replace(/\r\n?|\n/g,'  \n');
  var text=(subject.trim() ? '**'+chatEscape_(subject.trim())+'**\n\n' : '')+content;
  if (!text.trim()) throw new Error('Chat message must not be empty');
  var message={text:text,markupSyntax:'MARKUP_SYNTAX_MARKDOWN'};
  if (Utilities.newBlob(JSON.stringify(message)).getBytes().length>32000) throw new Error('Chat message exceeds the 32000-byte native limit');
  return message;
}
function chatOperation_(operation,args) {
  chatSession_();
  var migration=withDataWriteLock_(chatMappings_);
  if (!migration.configured) throw new Error('Chat migration is not configured; import source team/channel mappings');
  var data=migration.data,team,channel,message;
  if (operation!=='GetAllTeams') {
    chatText_(args[0],'Team ID');
    team=data.teams.find(function (entry) { return entry.id===args[0]; });
    if (!team) throw new Error('Team requires a migrated Google Chat anchor mapping');
  }
  if (operation==='PostMessageToChannelV3') {
    chatText_(args[1],'Channel ID');
    channel=data.channels.find(function (entry) { return entry.team_id===team.id && entry.id===args[1]; });
    if (!channel) throw new Error('Channel requires a migrated Google Chat space mapping for this team');
    message=chatMessage_(args[2],args[3]); // Validate before any remote write.
  }
  var spaces=chatJoinedSpaces_();
  if (operation==='GetAllTeams') return {value:data.teams.filter(function (entry) { return spaces.has(entry.space_name); })
    .map(function (entry) { return chatSpaceRecord_(entry,spaces); })};
  var record=chatSpaceRecord_(team,spaces);
  if (operation==='GetTeam') return record;
  if (operation==='GetChannelsForGroup') return {value:data.channels.filter(function (entry) {
    return entry.team_id===team.id && spaces.has(entry.space_name);
  }).map(function (entry) { return chatSpaceRecord_(entry,spaces); })};
  if (operation==='PostMessageToChannelV3') {
    chatSpaceRecord_(channel,spaces);
    var result=Chat.Spaces.Messages.create(message,channel.space_name,{requestId:Utilities.getUuid()});
    if (!result || typeof result.name!=='string' || !result.name.startsWith(channel.space_name+'/messages/') ||
        !/^[A-Za-z0-9_.-]+$/.test(result.name.slice((channel.space_name+'/messages/').length)))
      throw new Error('Invalid Chat message response; delivery may have succeeded, inspect the channel before retrying');
    return {id:result.name};
  }
  throw new Error('Unsupported Google Chat operation: '+operation);
}
'''

MIGRATION_TEMPLATE = '''// Run setup(), then supply reviewed source team/channel mappings. See chat-migration.md.
// Keep the trailing underscore: this import must remain editor-only.
function migrateChat_() {
  var migration = null;
  if (migration === null) throw new Error('Supply reviewed Chat space mappings before importing');
  return importChat_(migration);
}
'''

MIGRATION_GUIDE = '''# Migrate Teams notifications and selectors to Google Chat

MicrosoftTeams.GetAllTeams, GetTeam, GetChannelsForGroup and
PostMessageToChannelV3 use the native Google Chat advanced service. The generated
manifest enables Chat v1 and requests chat.spaces.readonly, chat.messages.create
and userinfo.email. Configure a standard Google Cloud project, enable the Chat
API, configure its Chat application and OAuth consent, and link the Apps Script
project as described in Google's
[Apps Script quickstart](https://developers.google.com/workspace/chat/api/guides/quickstart/apps-script).
Deploy as the accessing Google user and authorize the requested scopes. Unknown
users and owner-delegated access are rejected. The user also needs access to the
app workbook; workbook editors can change its data and migration mappings.

Google Chat has spaces, not the Teams team/channel hierarchy. Create or choose
the intended named Chat spaces and arrange membership separately. Map each source
team ID to an anchor space representing membership in that logical team, then map
each source channel ID to its destination space. A team's General channel may
use its own anchor; other channel mappings must be unique. Channels cannot use
another team's anchor. The import does not create spaces or grant membership.

Run setup(), replace null in ChatMigration.gs with a reviewed object such as:

```json
{"teams":[{"id":"original-team-id","space_name":"spaces/TEAM"}],
 "channels":[{"id":"original-channel-id","team_id":"original-team-id",
              "space_name":"spaces/CHANNEL"}]}
```

Run migrateChat_() in the editor. IDs returned to formulas remain the source IDs;
names and descriptions come from the mapped Google spaces. The migration is
validated before a single write and refuses re-import or incomplete storage.
An explicitly empty import is allowed; absent migration is an error. Keep import
functions private with trailing underscores. Re-conversion preserves the edited
ChatMigration.gs. The reserved __pfx2gas_chat sheet is excluded from the generic
data API, but workbook editors can change it.

List joined teams exposes mapped anchors in the caller's joined named spaces;
unmapped Google spaces are outside this app's migrated hierarchy. GetTeam requires
anchor membership. Channel listing and posting also require anchor membership,
and show/use only joined mapped channel spaces. Native Chat authorization remains
the final check. Space pages are read to completion; 10,000 spaces, 100 pages or
a 20-second pagination budget fail explicitly instead of truncating results.
Value bindings cache reads until connector invalidation or reload.

Posts are native user-authenticated text messages in a new thread. Subjects become
a bold first paragraph. Text is escaped to prevent accidental formatting or
mentions. Supported HTML: b/strong, i/em, br (including exported br closing tags),
p/div and links with a single quoted HTTP(S) or mailto href. Ordinary HTML spaces
collapse; basic and numeric entities are decoded. Unsupported tags/attributes,
entities, nested/multiline emphasis, attachments, mentions, cards and Teams-only
options fail before posting. HTML is converted deterministically to Google's
[CommonMark message syntax](https://developers.google.com/workspace/chat/format-messages),
generally available since August 7, 2026. Lists and richer source HTML require
review. This does not reproduce Teams styling exactly; verify native rendering.

The JSON message payload must fit within 32,000 UTF-8 bytes. Each post makes one
create call with a request ID and returns the native message resource name as id.
There is no automatic retry. A network or malformed-response error may follow a
successful delivery; inspect the destination before manually retrying to avoid
duplicates. Native permission and quota errors remain errors for source IfError
logic. No message list/history or modification operation is currently mapped.

Local tests execute the generated server against explicit Google API fixtures.
They do not prove live OAuth permissions, space membership or native rendering.
Complete a reviewed deployment check before claiming production fidelity.
'''
