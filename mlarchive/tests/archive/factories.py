from django.contrib.auth.models import User
from mlarchive.archive.models import *
import factory

class UserFactory(factory.DjangoModelFactory):
    FACTORY_FOR = User

    username = 'admin'
    password = 'pass'

class EmailListFactory(factory.DjangoModelFactory):
    FACTORY_FOR = EmailList

    name = 'test'