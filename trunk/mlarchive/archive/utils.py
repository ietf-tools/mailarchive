try:
    import json
except ImportError:
    import simplejson as json

from django.http import HttpResponse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.shortcuts import render_to_response
from mlarchive.archive.models import EmailList

import mailbox

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
US_CHARSETS = ('us-ascii','iso-8859-1')

def handle_plain(part):
    # get_charset() doesn't work??
    if part.get_content_charset():
        charset = part.get_content_charset()
    elif part.get_param('charset'):
        charset = part.get_param('charset').lower()
    else:
        charset = US_CHARSETS[0]
    
    payload = part.get_payload(decode=True)
    if charset not in US_CHARSETS:
        # TODO log failure and pass
        #try:
        payload = payload.decode(charset)
        #except UnicodeDecodeError:
    #return render_to_string('archive/message_plain.html', {'payload': payload})
    return payload
    
def handle_html(part):
    return render_to_string('archive/message_html.html', {'payload': part.get_payload(decode=True)})
    
# a dictionary of supported mime types
HANDLERS = {'text/plain':handle_plain,
            'text/html':handle_html}
            
def get_html(msg,request):
    '''
    This function takes a Message object and Request object and returns the message content in
    HTML
    '''
    try:
        with open(msg.get_file_path()) as f:
            maildirmessage = mailbox.MaildirMessage(f)
            headers = maildirmessage.items()
            parts = []
            for part in maildirmessage.walk():
                handler = HANDLERS.get(part.get_content_type(),None)
                if handler:
                    parts.append(handler(part))
    except IOError, e:
        return ''
    
    return render_to_string('archive/message.html', {
        'msg': msg,
        'maildirmessage': maildirmessage,
        'headers': headers,
        'parts': parts,
        'request': request}
    )

def get_noauth(request):
    '''
    This function takes a request object and returns a list of private email list ids (as string)
    the user does NOT have access to, for use in an exclude().  The list is stored in the request
    session to minimize database hits.
    '''
    noauth = request.session.get('noauth',None)
    if noauth:
        return noauth
    else:
        request.session['noauth'] = [ str(x.pk) for x in EmailList.objects.filter(
            private=True).exclude(members=request.user) ]
        return request.session['noauth']

def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data),
                mimetype='application/json')
    return to_json

def render(template, data, request):
    return render_to_response(template,
                              data,
                              context_instance=RequestContext(request))

def template(template):
    def decorator(fn):
        def render(request, *args, **kwargs):
            context_data = fn(request, *args, **kwargs)
            if isinstance(context_data, HttpResponse):
                # View returned an HttpResponse like a redirect
                return context_data
            else:
                # For any other type of data try to populate a template
                return render_to_response(template,
                        context_data,
                        context_instance=RequestContext(request)
                    )
        return render
    return decorator