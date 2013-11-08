import datetime
import pytest
from factories import *
from mlarchive.archive.view_funcs import *

DUMMY_DAY = datetime.datetime(2013,1,1)

def test_chunks():
    result = list(chunks([1,2,3,4,5,6,7,8,9],3))
    assert len(result) == 3
    assert result[0] == [1,2,3]

def test_initialize_formsets():
    query = 'text:value -text:negvalue'
    reg, neg = initialize_formsets(query)
    assert len(reg.forms) == 1
    assert len(neg.forms) == 1
    assert reg.forms[0].initial['field'] == 'text'
    assert reg.forms[0].initial['value'] == 'value'
    assert neg.forms[0].initial['field'] == 'text'
    assert neg.forms[0].initial['value'] == 'negvalue'

@pytest.mark.django_db(transaction=True)
def test_get_columns():
    user = UserFactory.build()
    x = EmailListFactory.create(name='public')
    columns = get_columns(user)
    assert len(columns) == 3
    assert len(columns['active']) == 1

#def test_get_export()
