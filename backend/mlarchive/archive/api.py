import base64
import binascii
from collections import OrderedDict
import datetime
from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
import json
import jsonschema
import re
import os
import sys
import tempfile

from django.conf import settings
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.utils.decorators import method_decorator

from mlarchive.exceptions import HttpJson400, HttpJson404
from mlarchive.archive.models import Message, EmailList, Subscriber
from mlarchive.archive.forms import AdvancedSearchForm
from mlarchive.archive.mail import archive_message
from mlarchive.utils.decorators import require_api_key
from mlarchive.archive.backends.elasticsearch import search_from_form

import logging
logger = logging.getLogger(__name__)

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
                sdate = isoparse(self.data['start'])
                filters['date__gte'] = sdate.astimezone(datetime.timezone.utc)
            except ValueError:
                raise HttpJson400('invalid start date')
        if 'end' in self.request.GET:
            if 'start' not in self.request.GET and 'duration' not in self.request.GET:
                raise HttpJson400('cannot provide end date without start date or duration')
            self.data['end'] = self.request.GET.get('end')
            try:
                edate = isoparse(self.data['end'])
                filters['date__lt'] = edate.astimezone(datetime.timezone.utc)
            except ValueError:
                raise HttpJson400('invalid end date')
        # default to previous month if no dates or duration given
        if 'start' not in self.request.GET and 'end' not in self.request.GET and 'duration' not in self.request.GET:
            end = datetime.datetime.now(datetime.timezone.utc)
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
                end = datetime.datetime.now(datetime.timezone.utc)
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
                date = isoparse(self.data['date'])
                filters['date'] = date.astimezone(datetime.timezone.utc)
            except ValueError:
                raise HttpJson400('invalid date')
        # default to previous month if date not given
        else:
            date = datetime.datetime.now(datetime.timezone.utc) - relativedelta(months=1)
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


_import_message_json_validator = jsonschema.Draft202012Validator(
    schema={
        "type": "object",
        "properties": {
            "list_name": {
                "type": "string",  # email list name
                "minLength": 1,
            },
            "list_visibility": {
                "type": "string",
                "enum": ["public", "private"],
                "description": "Visibility setting for the email list",
            },
            "message": {
                "type": "string",  # base64-encoded mail message
            },
        },
        "required": ["message"],
    }
)


@method_decorator(require_api_key, name='dispatch')
@method_decorator(csrf_exempt, name='dispatch')
class ImportMessageView(View):
    '''An API to import a message.
    Expect a POST request with JSON payload
    message: base64 encoded email message
    and X-API-Key header
    '''
    http_method_names = ['post']

    def _err(self, code, text):
        return HttpResponse(text, status=code, content_type="text/plain")

    def post(self, request, **kwargs):

        if request.content_type != "application/json":
            return self._err(415, "Content-Type must be application/json")

        # Validate
        try:
            payload = json.loads(request.body)
            _import_message_json_validator.validate(payload)
        except json.decoder.JSONDecodeError as err:
            msg = f'JSON parse error at line {err.lineno} col {err.colno}: {err.msg}'
            logger.error(msg)
            return self._err(400, msg)
        except jsonschema.exceptions.ValidationError as err:
            msg = f'JSON schema error at {err.json_path}: {err.message}'
            logger.error(msg)
            return self._err(400, msg)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(f"Exception type: {exc_type}, Exception message: {exc_value}", exc_info=True)
            msg = f'Error processing request. ({exc_value})'
            return self._err(400, msg)

        try:
            message = base64.b64decode(payload["message"], validate=True)
        except binascii.Error:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(f"Exception type: {exc_type}, Exception message: {exc_value}", exc_info=True)
            msg = f'Invalid message: bad base64 encoding ({exc_value})'
            return self._err(400, msg)

        list_name = payload["list_name"]
        list_visibility = payload["list_visibility"]

        # stash message on disk
        if not os.path.exists(settings.IMPORT_DIR):
            os.makedirs(settings.IMPORT_DIR)
        prefix = f'{list_name}.{list_visibility}.'
        try:
            fd, filepath = tempfile.mkstemp(prefix=prefix, dir=settings.IMPORT_DIR)
            with os.fdopen(fd, 'wb') as f:
                f.write(message)
        except (FileNotFoundError, PermissionError, OSError) as e:
            msg = str(e)
            logger.error(msg)
            return self._err(500, msg)
        logger.info(f'Received message: {filepath}')

        # process message
        status = archive_message(message, list_name, private=bool(list_visibility == 'private'))
        logger.info(f'Archive message status: {filepath} {status}')
        if status == 0:
            return HttpResponse(status=201)
        else:
            return self._err(400, 'archive_message error')


# @method_decorator(require_api_key, name='dispatch')
class SearchMessageView(View):
    '''An API to search messages'''
    http_method_names = ['get']

    def _http_err(self, code, text):
        return HttpResponse(text, status=code, content_type="text/plain")

    def _api_response(self, result):
        return JsonResponse(data={"results": result})

    def get(self, request, **kwargs):
        '''Use AdvancedSearchForm to build search query'''

        # validate email_list
        if 'email_list' not in request.GET:
            self._http_err(400, 'Missing parameter: email_list')
        email_list = request.GET.get('email_list')
        try:
            EmailList.objects.get(name=email_list)
        except EmailList.DoesNotExist:
            self._http_err(400, 'Invalid email list')

        # validate start_date
        if 'start_date' in request.GET:
            start_date = request.GET.get('start_date')
            try:
                datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                self._http_err(400, 'Invalid start date')

        # build search
        form = AdvancedSearchForm(request.GET, request=request)
        if not form.is_valid():
            print(form.errors)
        assert form.is_valid()
        search = search_from_form(form)
        response = search.execute()
        # build response
        results = []
        for hit in response:
            try:
                msg_obj = Message.objects.get(pk=hit.django_id)
            except Message.DoesNotExist:
                continue
            message = {}
            message['from'] = msg_obj.frm
            message['subject'] = msg_obj.subject
            message['content'] = msg_obj.get_body()
            message['message_id'] = msg_obj.msgid
            message['url'] = msg_obj.url
            message['date'] = msg_obj.date.strftime('%a, %d %b %Y %H:%M:%S %z')
            results.append(message)
        return self._api_response(results)
