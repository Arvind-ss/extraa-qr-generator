"""Safe template substitution for profile configuration.

Profiles are data, never code. A template is literal text with ``{column}``
placeholders; nothing else is interpreted. Deliberately NOT ``str.format``,
which would let a profile reach through to attributes and internals via
``{x.__class__.__init__.__globals__}``. No eval, no exec, no f-strings.
"""

import re

# A token is {name}: a leading letter or underscore, then word characters.
# Anything else -- {0}, {a.b}, {a!r}, a lone brace -- is left as literal text
# and can never resolve to a value.
TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class TemplateError(ValueError):
    pass


def tokens(template):
    """The set of column names a template refers to."""
    return set(TOKEN.findall(template))


def resolve(template, row):
    """Substitute ``{column}`` from ``row``. Missing column is an error."""
    def sub(match):
        key = match.group(1)
        try:
            value = row[key]
        except KeyError:
            raise TemplateError(
                f"template {template!r} needs column {key!r}, which the row does "
                f"not have (has: {sorted(row)})") from None
        return "" if value is None else str(value)

    return TOKEN.sub(sub, template)


def check(template, allowed_columns, label):
    """Reject a template that references columns the profile does not declare.

    Run at profile-save time so a bad template is caught once by an admin
    rather than 50,000 times during a batch.
    """
    if not isinstance(template, str):
        raise TemplateError(f"{label} must be text, got {type(template).__name__}")
    unknown = tokens(template) - set(allowed_columns)
    if unknown:
        raise TemplateError(
            f"{label} uses unknown column(s) {sorted(unknown)}; "
            f"this profile declares {sorted(allowed_columns)}")
    return template
