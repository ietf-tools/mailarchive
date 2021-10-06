from dateutil.parser import isoparse

from django.views import View
from django.http import JsonResponse

from mlarchive.archive.models import Message


class MsgCountView(View):
    '''An API to get message counts for given lists.
    
    Parameters:
    list:   the email list name. Multiple can be provided
    start:  start date in ISO form
    end:    end date in ISO form
    '''
    def setup(self, request, *args, **kwargs):
        self.data = {}
        return super().setup(request, *args, **kwargs)

    def get_filters(self, request):
        '''Build Message query filters from GET parameters'''
        filters = {}
        if 'start' in request.GET:
            self.data['start'] = request.GET.get('start')
            filters['date__gte'] = isoparse(self.data['start'])
        if 'end' in request.GET:
            self.data['end'] = request.GET.get('end')
            filters['date__lte'] = isoparse(self.data['end'])
        return filters
    
    def get(self, request, *args, **kwargs):
        msg_counts = {}
        try:
            filters = self.get_filters(request)
        except ValueError:
            return JsonResponse({"error": "can't parse date"})
        for list_name in request.GET.getlist('list'):
            msg_counts[list_name] = Message.objects.filter(email_list__name=list_name, **filters).count()
        self.data['msg_counts'] = msg_counts
        return JsonResponse(self.data)
        