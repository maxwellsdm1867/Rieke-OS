"""Allowlisted startup diagnostics; never transport exception text or log contents."""
COMPONENTS = {'mysql': 'MySQL client', 'mysqld': 'MySQL server', 'mysqldump': 'MySQL backup tool'}
REASONS = {'missing': 'is missing', 'unavailable': 'could not run', 'incompatible': 'has an incompatible version'}


class RequiredComponentError(ValueError):
    def __init__(self, component, reason):
        if component not in COMPONENTS or reason not in REASONS:
            raise ValueError('Unknown required component failure')
        self.component, self.reason = component, reason
        super().__init__(f'Bundled {COMPONENTS[component]} {REASONS[reason]}')


def safe_component_failure(value):
    if (isinstance(value, dict) and isinstance(value.get('component'), str)
            and isinstance(value.get('reason'), str)
            and value['component'] in COMPONENTS and value['reason'] in REASONS):
        return {'component': value['component'], 'reason': value['reason']}
    return None


def startup_failure_message(log_path, failure=None):
    failure = safe_component_failure(failure)
    message = 'DISCO could not open this project. '
    if failure:
        message += f"The bundled {COMPONENTS[failure['component']]} {REASONS[failure['reason']]}. "
        message += ('Quit DISCO and confirm it has finished closing. Replace only the application with a complete '
                    'copy from your trusted distribution, then reopen this project. Keep your project folders '
                    'and settings; do not delete or replace the project database. ')
    else:
        message += ('The cause has not been identified. Review the recovery log before retrying; '
                    'do not delete or replace the project database. ')
    # Location is supplied by the parent, never by the child or a log parser.
    return message + f'Recovery log: {log_path}'


class ProjectSessionInUseError(ValueError):
    """One project is busy; the launcher and other projects remain available."""
    code = 'project_session_in_use'

    def __init__(self, project):
        super().__init__(
            'DISCO could not open this project. This project is already open in another DISCO session '
            'or recovery. Close it in the existing app or browser session, then retry. '
            'Closing a browser tab alone may leave its service running. You can open or create another '
            'project now. Keep your project files; reinstalling the app will not close that session. '
            'Project: ' + str(project))
