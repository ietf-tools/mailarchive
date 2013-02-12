import re
import sys
from haystack.query import SQ
from django.conf import settings

Patern_Field_Query = re.compile(r"^(\w+):(\w+)\s*",re.U)
Patern_Field_Exact_Query = re.compile(r"^(\w+):\"(.+)\"\s*",re.U)
Patern_Normal_Query = re.compile(r"^(\w+)\s*",re.U)             
Patern_Operator = re.compile(r"^(AND|OR|NOT)\s*",re.U)
Patern_Quoted_Text = re.compile(r"^\"(.+)\"\s*",re.U)

HAYSTACK_DEFAULT_OPERATOR = getattr(settings,'HAYSTACK_DEFAULT_OPERATOR','AND')

class NoMatchingBracketsFound(Exception):
    def __init__(self,value=''):
        self.value = value

    def __str__(self):
        return "Matching brackets were not found: "+self.value

class UnhandledException(Exception):
    def __init__(self,value=''):
        self.value = value
    def __str__(self):
        return self.value        

def handle_field_query(sq,q,current=HAYSTACK_DEFAULT_OPERATOR ):
    mat = re.search(Patern_Field_Query,q)
    sq.add(SQ(**{str(mat.group(1)):mat.group(2)}),current)
    q, n = re.subn(Patern_Field_Query,'',q,1)
    return sq,q, HAYSTACK_DEFAULT_OPERATOR

def handle_field_exact_query(sq,q,current=HAYSTACK_DEFAULT_OPERATOR ):
    mat = re.search(Patern_Field_Exact_Query,q)
    query = mat.group(2)
    #it seams that haystack exact only works if there is a space in the query.So adding a space
    if not re.search(r'\s',query):
        query+=" "   
    sq.add(SQ(**{str(mat.group(1)+"__exact"):query}),current)
    q,n = re.subn(Patern_Field_Exact_Query,'',q,1)
    return sq,q,HAYSTACK_DEFAULT_OPERATOR
    

def handle_brackets(sq,q,current=HAYSTACK_DEFAULT_OPERATOR):
    no_brackets = 1
    i=1
    assert q[0]=="("
    while no_brackets and i<len(q):
        if q[i]==")":
            no_brackets-=1
        elif q[i]=="(":
            no_brackets+=1
        i+=1
    if not no_brackets:
        sq.add((parse(q[1:i-1])),current)
    else:
        raise NoMatchingBracketsFound(q)
    return sq, q[i:], HAYSTACK_DEFAULT_OPERATOR
    
def handle_normal_query(sq,q,current):
    if re.search(Patern_Operator,q):
        current = re.search(Patern_Operator,q).group(1)
    else:
        mat = re.search(Patern_Normal_Query,q)
        if current == "NOT":
            sq.add(~SQ(content=mat.group(1)),HAYSTACK_DEFAULT_OPERATOR)
        else:
            sq.add(SQ(content=mat.group(1)),current)
        current = HAYSTACK_DEFAULT_OPERATOR
    q, n = re.subn(Patern_Normal_Query,'',q)
    return sq,q,current

def handle_quoted_query(sq,q,current):
    mat = re.search(Patern_Quoted_Text,q)
    query = mat.group(1)
    #it seams that haystack exact only works if there is a space in the query.So adding a space
    if not re.search(r'\s',query):
        query+=" "        
    sq.add(SQ(content__exact=query),current)
    q,n = re.subn(Patern_Quoted_Text,'',q,1)
    return sq,q,HAYSTACK_DEFAULT_OPERATOR
    
def parse(q):
    try:
        sq= SQ()
        current = HAYSTACK_DEFAULT_OPERATOR
    
        while q:
            q=q.lstrip()
            if re.search(Patern_Field_Query,q):
                sq, q, current = handle_field_query(sq,q,current)
            elif re.search(Patern_Field_Exact_Query,q):
                sq, q, current = handle_field_exact_query(sq,q,current )
            elif re.search(Patern_Quoted_Text,q):
                sq, q, current = handle_quoted_query(sq,q,current)
            elif re.search(Patern_Normal_Query,q):
                sq, q,current = handle_normal_query(sq,q,current)
            elif q[0]=="(":
                sq, q,current = handle_brackets(sq,q,current)
            else:
                q=q[1:]
    except:
        raise UnhandledException(sys.exc_info()[0])
    return sq