"""Generate readable MATLAB commands using semantic, validated split IDs."""

def matlab_split_fields(fields):
    if not isinstance(fields, (list, tuple)) or len(fields) > 8:
        raise ValueError('Choose up to 8 distinct tree fields')
    if any(not isinstance(field, str) or not field or any(char in field for char in '\r\n\x00') for field in fields):
        raise ValueError('Tree fields must be nonempty single-line strings')
    if len(set(fields)) != len(fields):
        raise ValueError('Tree fields must be distinct')
    def literal(field):
        if field.startswith('joint/'):
            from workspace_tree import joint_components
            return matlab_split_fields(joint_components(field))
        return "'" + field.replace("'", "''") + "'"
    return '{' + ', '.join(literal(field) for field in fields) + '}'


def matlab_tree_command(fields):
    return "[tree, gui] = launchWorkspaceTree('recordings.mat', " + matlab_split_fields(fields) + ');'
