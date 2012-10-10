from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from mlarchive.archive.utils import jsonapi
from mlarchive.archive.models import EmailList, Message

@jsonapi
def ajax_get_list(request):
    '''
    Ajax function for use with jQuery UI Autocomplete.  Returns list of EmailList objects
    '''
    if request.method != 'GET' or not request.GET.has_key('term'):
        return { 'success' : False, 'error' : 'No term submitted or not GET' }
    term = request.GET.get('term')

    results = EmailList.objects.filter(name__startswith=term)
    if results.count() > 20:
        results = results[:20]
    elif results.count() == 0:
        return { 'success' : False, 'error' : "No results" }

    response = [dict(id=r.id, label = r.name) for r in results]
    return response

'''
@jsonapi
def ajax_get_msg(request):
    if request.method != 'GET' or not request.GET.has_key('term'):
        return { 'success' : False, 'error' : 'No term submitted or not GET' }
    term = request.GET.get('term')
    
    try:
        msg = Message.objects.get(id=term)
    except Message.DoesNotExist:
        return { 'success' : False, 'error' : 'ID not found' }
    
    response = {'body':msg.body}
    return response
'''

def ajax_get_msg(request):
    if request.method != 'GET' or not request.GET.has_key('term'):
        return { 'success' : False, 'error' : 'No term submitted or not GET' }
    term = request.GET.get('term')
    
    try:
        msg = Message.objects.get(id=term)
    except Message.DoesNotExist:
        return { 'success' : False, 'error' : 'ID not found' }
    
    return render_to_response('archive/ajax_msg.html', {
        'msg': msg},
        RequestContext(request, {}),
    )
    
