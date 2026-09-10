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

PROFILE_OPERATIONS = {
    'SearchUser': {'arity': [0, 1], 'write': False},
    'UserProfileV2': {'arity': [1, 2], 'write': False},
    'UserPhotoV2': {'arity': [1], 'write': False},
}
PROFILE_NAMES = {'Office365Users', 'Microsoft365Users'}
PROFILE_LIMITATION = ('Office365 profiles use the accessing user\'s Google People domain directory and explicit '
    'source-ID/Google-account mappings. Google prefix search, directory visibility, primary field selection and '
    'Google email addresses replace Microsoft directory semantics. Only mapped profile fields are returned; '
    'account status, Microsoft-only fields, guest directories and exact search ordering require review. '
    'Photos return Google-hosted image URLs rather than binary content; absent custom photos return Blank.')


def service_contracts(ir):
    result = {ds.name: {'target': 'google-sheets-task-board', 'operations': PLANNER_OPERATIONS,
                     'migrationRequired': True, 'limitations': [PLANNER_LIMITATION]}
            for ds in ir.data_sources if ds.origin == 'service' and ds.name == 'Planner'}
    result.update({ds.name: {'target':'google-people-directory','operations':PROFILE_OPERATIONS,
                   'migrationRequired':True,'limitations':[PROFILE_LIMITATION]}
                   for ds in ir.data_sources if ds.origin=='service' and ds.name in PROFILE_NAMES})
    return result
