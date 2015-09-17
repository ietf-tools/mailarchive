from django import template
from django.utils.safestring import mark_safe

import urllib

register = template.Library()

# --------------------------------------------------
# Classes
# --------------------------------------------------
class AppendGetNode(template.Node):
    """This is a custom tag which takes one or more arguments in the form key=val,
    key=val, etc. The key value pairs are added to the current URL parameters overriding
    parameters of the same name.  The new URL is returned.
    NOTE: request must be in the template context
    """
    def __init__(self, dict):
        self.dict_pairs = {}
        for pair in dict.split(','):
            pair = pair.split('=')
            self.dict_pairs[pair[0]] = template.Variable(pair[1])

    def render(self, context):
        # GET is a QueryDict object
        params = context['request'].GET.copy()

        # use this method to replace keys if they already exist.  update() won't replace
        for key in self.dict_pairs:
            params[key] = self.dict_pairs[key].resolve(context)

        path = context['request'].META['PATH_INFO']

        if len(params):
            path += "?%s" % params.urlencode()

        return path

# --------------------------------------------------
# Decorators
# --------------------------------------------------
"""
from: http://djangosnippets.org/snippets/1627/

Decorator to facilitate template tag creation
"""
def easy_tag(func):
    """deal with the repetitive parts of parsing template tags"""
    def inner(parser, token):
        try:
            return func(*token.split_contents())
        except TypeError:
            raise template.TemplateSyntaxError('Bad arguments for tag "%s"' % token.split_contents()[0])
    inner.__name__ = func.__name__
    inner.__doc__ = inner.__doc__
    return inner

# --------------------------------------------------
# Tags
# --------------------------------------------------
@register.tag()
@easy_tag
def append_to_get(_tag_name, dict):
    return AppendGetNode(dict)

@register.simple_tag
def checked(request,key,val):
    """Returns "checked" if key=value appears in the request URL parameters
    Use this tag to set the class, for highlighting selected filter options
    """
    params = request.GET.dict()
    if key in params:
        values = params[key].split(',')
        if val in values:
            return 'checked'
    return ''

@register.simple_tag
def get_column(length,count):
    """This custom tag takes two integers, the length of a ordered list and the count of the current
    list item.  It returns col[1-4] to be used as a class to position the item in the
    correct column.
    """
    col_length = length / 4
    if count <= col_length:
        return 'col1'
    elif count <= 2 * col_length:
        return 'col2'
    elif count <= 3 * col_length:
        return 'col3'
    else:
        return 'col4'

@register.simple_tag
def get_params(params, exclude):
    """This custom template tag takes a dictionary of parameters (requets.GET) and
    a list of keys to exclude and returns a urlencoded string for use in a link
    """
    for key in exclude:
        if key in params:
            params.pop(key)

    url = 'test'

    return template.defaultfilters.urlencode(url)

@register.simple_tag
def selected(request,key,val):
    """Returns "selected" if key=value appears in the request URL parameters
    Use this tag to set the class, for highlighting selected filter options
    """
    params = request.GET.dict()
    if key in params:
        if params.get(key,None) == val:
            return 'selected'
    else:
        if val == '':
            return 'selected'

# --------------------------------------------------
# From: https://djangosnippets.org/snippets/2237/
# --------------------------------------------------

@register.tag
def query_string(parser, token):
    """
    Allows you too manipulate the query string of a page by adding and removing keywords.
    If a given value is a context variable it will resolve it.
    Based on similiar snippet by user "dnordberg".

    requires you to add:

    TEMPLATE_CONTEXT_PROCESSORS = (
    'django.core.context_processors.request',
    )

    to your django settings.

    Usage:
    http://www.url.com/{% query_string "param_to_add=value, param_to_add=value" "param_to_remove, params_to_remove" %}

    Example:
    http://www.url.com/{% query_string "" "filter" %}filter={{new_filter}}
    http://www.url.com/{% query_string "page=page_obj.number" "sort" %}

    """
    try:
        tag_name, add_string,remove_string = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag requires two arguments" % token.contents.split()[0]
    if not (add_string[0] == add_string[-1] and add_string[0] in ('"', "'")) or not (remove_string[0] == remove_string[-1] and remove_string[0] in ('"', "'")):
        raise template.TemplateSyntaxError, "%r tag's argument should be in quotes" % tag_name

    add = string_to_dict(add_string[1:-1])
    remove = string_to_list(remove_string[1:-1])

    return QueryStringNode(add,remove)

class QueryStringNode(template.Node):
    def __init__(self, add,remove):
        self.add = add
        self.remove = remove

    def render(self, context):
        p = {}
        for k, v in context["request"].GET.items():
            p[k]=v
        return get_query_string(p,self.add,self.remove,context)

def get_query_string(p, new_params, remove, context):
    """
    Add and remove query parameters. From `django.contrib.admin`.
    """
    for r in remove:
        for k in p.keys():
            if k.startswith(r):
                del p[k]
    for k, v in new_params.items():
        if k in p and v is None:
            del p[k]
        elif v is not None:
            p[k] = v

    for k, v in p.items():
        try:
            p[k] = template.Variable(v).resolve(context)
        except:
            p[k]=v

    #return mark_safe('?' + '&amp;'.join([u'%s=%s' % (k, v) for k, v in p.items()]).replace(' ', '%20'))
    return mark_safe('?' + '&amp;'.join([u'%s=%s' % (urllib.quote_plus(convert_utf8(k)), urllib.quote_plus(convert_utf8(v))) for k, v in p.items()]))

def convert_utf8(v):
    '''Returns a string given various inputs: unicode, string, int'''
    if isinstance(v, unicode):
        return v.encode('utf8')
    if isinstance(v, str):
        return v
    if isinstance(v, int):
        return str(v)

# Taken from lib/utils.py
def string_to_dict(string):
    kwargs = {}

    if string:
        string = str(string)
        if ',' not in string:
            # ensure at least one ','
            string += ','
        for arg in string.split(','):
            arg = arg.strip()
            if arg == '': continue
            kw, val = arg.split('=', 1)
            kwargs[kw] = val
    return kwargs

def string_to_list(string):
    args = []
    if string:
        string = str(string)
        if ',' not in string:
            # ensure at least one ','
            string += ','
        for arg in string.split(','):
            arg = arg.strip()
            if arg == '': continue
            args.append(arg)
    return args