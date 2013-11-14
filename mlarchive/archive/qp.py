from haystack.query import SQ

import collections
import re
'''
expr        = 1*word
word        = *ALPHA

ALPHA          =  %x41-5A / %x61-7A   ; A-Z / a-z

searchExpr ::= searchAnd [ OR searchAnd ]...
searchAnd ::= searchTerm [ AND searchTerm ]...
searchTerm ::= [NOT] ( single-word | quotedString | '(' searchExpr ')' )

'''

# Token Specification
modifiers = ['date','email_list','from','frm','frm_email','msgid','subject','to','spam_score','text']
ALPHA  = r'(?P<ALPHA>[a-zA-Z]+)'
LPAREN = r'(?P<LPAREN>\()'
RPAREN = r'(?P<RPAREN>\))'
WS     = r'(?P<WS>\s+)'
QUOTED_WORD = r'(?P<QUOTED_WORD>"[^"]+")'
DASH   = r'(?P<DASH>-)'
FIELD = r'(?P<FIELD>subject|to|frm):'

master_pat = re.compile('|'.join([FIELD, DASH, QUOTED_WORD, ALPHA, LPAREN, RPAREN, WS]))

# Tokenizer
Token = collections.namedtuple('Token', ['type','value'])

def generate_tokens(text):
    scanner = master_pat.scanner(text)
    for m in iter(scanner.match, None):
        tok = Token(m.lastgroup, m.group())
        if tok.type != 'WS':
            yield tok

# Parser
class ExpressionEvaluator:
    '''
    Implementation of a recursive descent parser.  Each method
    implements a single grammar rule.  Use the ._accept() method
    to test and accept the current lookahead token.  Use the ._expect()
    method to exactly match and discard the next token on the input
    (or raise a SyntaxError if it doesn't match).
    '''

    def parse(self,text):
        self.tokens = generate_tokens(text)
        self.tok = None             # Last symbol consumed
        self.nexttok = None         # Nest symbol tokenized
        self._advance()             # Load first lookahead token

        # self.field = 'content'
        # self.negate = False
        # self.sq = SQ()

        return self.top()

    def _advance(self):
        'Advance one token ahead'
        self.tok, self.nexttok = self.nexttok, next(self.tokens, None)

    def _accept(self,toktype):
        'Test and consume the next token if it matches toktype'
        if self.nexttok and self.nexttok.type == toktype:
            self._advance()
            return True
        else:
            return False

    def _expect(self,toktype):
        'Consume next token if it matches toktype or raise SyntaxError'
        if not self._accept(toktype):
            raise SyntaxError('Expected ' + toktype)

    def _add_part(self,value):
        if self.negate:
            self.sq.add(~SQ(self.field=value),'AND')
            self.negate = False
        else:
            self.sq.add(SQ(self.field=value),'AND')

class ExpressionTreeBuilder(ExpressionEvaluator):
    def query(self):
        'query ::= expr*'
        
        while True:
            exprval = self.expr()
            
        return sq
    
    def expr(self):
        'expr ::= 1*ALPHA'

        while self._accept('DASH') or self._accept('ALPHA') or self._accept('QUOTED_WORD'):
            op = self.tok.type
            if op == 'DASH':
                self.negate = True
            elif op == 'ALPHA':
                self._add_part(self.tok.value)
            elif op == 'QUOTED_WORD':
                self.field += '__exact'
                self._add_part(self.tok.value)
            elif op == 'FIELD':
                self.field = self.tok.value
                val = self.literal()
                self._add_part(self.field,val)

        return self.sq

    def literal(self):
        if self._accept('ALPHA') or self._accept('QUOTED_WORD'):
            op = self.tok.type
            if op == 'ALPHA':
                return self.tok.value
            elif op == 'QUOTED_WORD':
                self.field += '__exact'
                return self.tok.value
