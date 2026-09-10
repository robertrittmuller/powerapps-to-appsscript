"""Dataverse state/status defaults and dependent values over Sheets records."""
from ..fx.naming import snake


def state_contract(source):
    if source.origin != 'dataverse':
        return None
    fields = {field.logical_name: field for field in source.fields if field.logical_name}
    state, status = fields.get('statecode'), fields.get('statuscode')
    if not state or state.source_type != 'State':
        return None
    contract = {'state': snake(state.name), 'status': snake(status.name) if status else None,
                'limitations': ['State/status defaults and pairs use exported metadata; missing initial states and supplied custom transition rules fail explicitly',
                    'Audit timestamps, plugins, business rules and other column defaults are not reproduced; existing rows are not backfilled']}
    try:
        if not status or status.source_type != 'Status' or state.type != 'choice' or status.type != 'choice':
            raise ValueError('exported State and Status choice fields are required')
        model = source.metadata.get('stateModel') or {}
        states, statuses = model.get('states', []), model.get('statuses', [])
        def codes(options):
            values = [option.get('value') for option in options]
            if not values or any(type(value) is not int for value in values) or len(set(values)) != len(values):
                raise ValueError('missing, duplicate or invalid state/status option metadata')
            return set(values)
        state_codes, status_codes = codes(states), codes(statuses)
        if state_codes != {choice['value'] for choice in state.choices} or status_codes != {choice['value'] for choice in status.choices}:
            raise ValueError('state/status metadata differs from the exported choices')
        status_states = {option['value']: option.get('state') for option in statuses}
        if any(type(value) is not int or value not in state_codes for value in status_states.values()):
            raise ValueError('each status reason needs an exported state')
        defaults = {option['value']: option.get('defaultStatus') for option in states}
        if any(type(value) is not int or status_states.get(value) != code for code, value in defaults.items()):
            raise ValueError('each state needs a valid exported default status reason')
        initial = model.get('defaultState')
        if initial is None and {(option['value'], option.get('invariantName')) for option in states} == {(0, 'Active'), (1, 'Inactive')}:
            # The standard two-state Dataverse model initializes Active. Do
            # not infer this from localized labels or a table-name prefix.
            initial = 0
        if initial is not None and (type(initial) is not int or initial not in state_codes):
            raise ValueError('invalid exported initial state')
        contract.update(initialState=initial, defaults={str(key):value for key,value in defaults.items()},
            statusStates={str(key):value for key,value in status_states.items()},
            writableCreate={snake(state.name): state.writable_create, snake(status.name): status.writable_create},
            writableUpdate={snake(state.name): state.writable_update, snake(status.name): status.writable_update},
            customTransitions=model.get('enforceTransitions') is True or any(option.get('transitionData') for option in statuses))
    except (ValueError, TypeError, KeyError) as error:
        contract['error'] = 'Dataverse state model for ' + source.name + ': ' + str(error)
    return contract


SERVER = r'''
function applyDataverseState_(ds, record, creating, previous) {
  var contract = DATA_CONTRACTS[ds].stateModel;
  if (!contract) return record;
  var has = function (field) { return Object.prototype.hasOwnProperty.call(record, field); };
  if (!creating && !has(contract.state) && !has(contract.status)) return record;
  if (contract.error) throw new Error(contract.error);
  var writable = creating ? contract.writableCreate : contract.writableUpdate;
  [contract.state, contract.status].forEach(function (field) {
    if (writable[field] === false) delete record[field];
  });
  if (!creating && !has(contract.state) && !has(contract.status)) return record;
  var prior = creating ? {} : previous();
  var state = has(contract.state) ? record[contract.state] : creating ? contract.initialState : prior[contract.state];
  if (typeof state !== 'number' || !Object.prototype.hasOwnProperty.call(contract.defaults, state))
    throw new Error('Dataverse state is missing or invalid in ' + ds + '; supply exported initial-state metadata or migrate the existing row');
  var status = has(contract.status) ? record[contract.status]
    : creating || has(contract.state) ? contract.defaults[state] : prior[contract.status];
  if (typeof status !== 'number' || contract.statusStates[status] !== state)
    throw new Error('Dataverse status reason does not belong to the selected state in ' + ds);
  if (!creating && contract.customTransitions && (state !== prior[contract.state] || status !== prior[contract.status]))
    throw new Error('Dataverse custom state transitions require a target adapter in ' + ds);
  record[contract.state] = state;
  record[contract.status] = status;
  return record;
}
'''
