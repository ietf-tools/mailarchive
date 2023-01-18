from collections import OrderedDict
import datetime
from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
import re

from django.views import View
from django.http import JsonResponse

from mlarchive.exceptions import HttpJson400, HttpJson404
from mlarchive.archive.models import Message, EmailList, Subscriber


duration_pattern = re.compile(r'(?P<num>\d+)(?P<unit>years|months|weeks|days|hours|minutes)')

class MsgCountView(View):
    '''An API to get message counts for given lists.
    
    Parameters:
    list:   the email list name. Multiple can be provided
    start:  start date in ISO form
    end:    end date in ISO form
    '''
    def setup(self, request, *args, **kwargs):
        self.data = OrderedDict()
        return super().setup(request, *args, **kwargs)

    def get_filters(self):
        '''Build Message query filters from GET parameters'''
        filters = {}

        # start / end dates
        if 'start' in self.request.GET:
            self.data['start'] = self.request.GET.get('start')
            try:
                filters['date__gte'] = isoparse(self.data['start'])
            except ValueError:
                raise HttpJson400('invalid start date')
        if 'end' in self.request.GET:
            if 'start' not in self.request.GET and 'duration' not in self.request.GET:
                raise HttpJson400('cannot provide end date without start date or duration')
            self.data['end'] = self.request.GET.get('end')
            try:
                filters['date__lt'] = isoparse(self.data['end'])
            except ValueError:
                raise HttpJson400('invalid end date')
        # default to previous month if no dates or duration given
        if 'start' not in self.request.GET and 'end' not in self.request.GET and 'duration' not in self.request.GET:
            end = datetime.date.today()
            start = end - relativedelta(months=1)
            self.data['start'] = start.strftime("%Y%m%d")
            self.data['end'] = end.strftime("%Y%m%d")
            filters['date__lt'] = end
            filters['date__gte'] = start

        # duration
        if 'duration' in self.request.GET:
            duration = self.request.GET['duration']
            match = duration_pattern.match(duration)
            if not match:
                raise HttpJson400('invalid duration')
            kwargs = {}
            kwargs[match.group('unit')] = int(match.group('num'))
            if 'start' in self.request.GET and 'end' in self.request.GET:
                raise HttpJson400('cannont use all three "start", "end" and "duration" parameters together')
            if 'start' in self.request.GET:
                end = filters['date__gte'] + relativedelta(**kwargs)
                self.data['end'] = end.strftime("%Y%m%d")
                filters['date__lt'] = end
            elif 'end' in self.request.GET:
                start = filters['date__lt'] - relativedelta(**kwargs)
                self.data['start'] = start.strftime("%Y%m%d")
                filters['date__gte'] = start
            else:
                # only duration appears in parameters
                end = datetime.date.today()
                start = end - relativedelta(**kwargs)
                self.data['start'] = start.strftime("%Y%m%d")
                self.data['end'] = end.strftime("%Y%m%d")
                filters['date__lt'] = end
                filters['date__gte'] = start
            self.data['duration'] = duration
        return filters
    
    def get_lists(self):
        assert self.request
        if 'list' in self.request.GET:
            list_names = self.request.GET.get('list', '').split(',')
            for list_name in list_names:
                try:
                    elist = EmailList.objects.get(name=list_name, private=False)
                except EmailList.DoesNotExist:
                    raise HttpJson404('list not found')
        else:
            list_names = [x.name for x in EmailList.objects.filter(private=False)]
        return list_names

    def get(self, request, *args, **kwargs):
        msg_counts = {}
        filters = self.get_filters()
        list_names = self.get_lists()

        for list_name in list_names:
            msg_counts[list_name] = Message.objects.filter(email_list__name=list_name, **filters).count()
        
        self.data['msg_counts'] = msg_counts
        return JsonResponse(self.data)
        

class SubscriberCountsView(View):
    '''An API to get subscriber counts for given lists.
    
    Parameters:
    list:   the email list name. Multiple can be provided
    date:   date in ISO form
    '''
    def setup(self, request, *args, **kwargs):
        self.data = OrderedDict()
        return super().setup(request, *args, **kwargs)
    
    def get_filters(self):
        '''Build Message query filters from GET parameters'''
        filters = {}

        # date
        if 'date' in self.request.GET:
            self.data['date'] = self.request.GET.get('date')
            try:
                filters['date'] = isoparse(self.data['date'])
            except ValueError:
                raise HttpJson400('invalid date')
        # default to previous month if date not given
        else:
            date = datetime.date.today() - relativedelta(months=1)
            date = date.replace(day=1)
            self.data['date'] = date.strftime("%Y%m%d")
            filters['date'] = date

        return filters
    
    def get_lists(self):
        assert self.request
        if 'list' in self.request.GET:
            list_names = self.request.GET.get('list', '').split(',')
            for list_name in list_names:
                try:
                    elist = EmailList.objects.get(name=list_name, private=False)
                except EmailList.DoesNotExist:
                    raise HttpJson404('list not found')
        else:
            list_names = [x.name for x in EmailList.objects.filter(private=False)]
        return list_names

    def get(self, request, *args, **kwargs):
        subscribers = {}
        filters = self.get_filters()
        list_names = self.get_lists()

        for list_name in list_names:
            try:
                subscribers[list_name] = Subscriber.objects.get(email_list__name=list_name, **filters).count
            except Subscriber.MultipleObjectsReturned:
                data = dict(error='multiple records for that date')
                return JsonResponse(data, status=500)
            except Subscriber.DoesNotExist:
                return JsonResponse({})
        self.data['subscriber_counts'] = subscribers
        return JsonResponse(self.data)