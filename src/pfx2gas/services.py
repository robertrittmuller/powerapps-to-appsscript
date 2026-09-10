"""Explicit Microsoft-to-Google connector contracts, never invented by a model."""

PLANNER_OPERATIONS = {
    'ListMyPlansV2': {'arity': [0], 'write': False},
    'ListGroupPlans': {'arity': [1], 'write': False},
    'ListBucketsV3': {'arity': [2], 'write': False},
    'ListTasksV3': {'arity': [2], 'write': False},
    'ListTasks': {'arity': [1], 'write': False},
    'ListMyTasks': {'arity': [0], 'write': False},
    'CreateTaskV3': {'arity': [3, 4], 'write': True},
    'UpdateTaskDetails': {'arity': [2], 'write': True},
}

PLANNER_LIMITATION = ('Planner uses a Google Sheets task board in the converted app; '
    'source IDs, Google-user membership and task records require explicit migration. '
    'Native Google Tasks UI, Planner roles, assignment audit metadata, ordering hints and external notifications are not reproduced.')


def service_contracts(ir):
    return {ds.name: {'target': 'google-sheets-task-board', 'operations': PLANNER_OPERATIONS,
                     'migrationRequired': True, 'limitations': [PLANNER_LIMITATION]}
            for ds in ir.data_sources if ds.origin == 'service' and ds.name == 'Planner'}
