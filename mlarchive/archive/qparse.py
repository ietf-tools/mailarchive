from pyparsing import *

'''
searchExpr ::= searchAnd [ OR searchAnd ]...
searchAnd ::= searchTerm [ AND searchTerm ]...
searchTerm ::= [NOT] ( single-word | quotedString | '(' searchExpr ')' )
'''

# classes to be constructed at parse time, from intermediate ParseResults
class UnaryOperation(object):
    def __init__(self, tokens):
        self.op, self.a = tokens[0]

class BinaryOperation(object):
    def __init__(self, tokens):
        self.op = tokens[0][1]
        self.operands = tokens[0][0::2]

class SearchAnd(BinaryOperation):
    def generateSetExpression(self):
        return "(%s)" % " & ".join(oper.generateSetExpression() for oper in self.operands)
    def __repr__(self):
        return "AND:(%s)" % (",".join(str(oper) for oper in self.operands))

class SearchOr(BinaryOperation):
    def generateSetExpression(self):
        return "(%s)" % " | ".join(oper.generateSetExpression() for oper in self.operands)
    def __repr__(self):
        return "OR:(%s)" % (",".join(str(oper) for oper in self.operands))

class SearchNot(UnaryOperation):
    def generateSetExpression(self):
        return "(set(recipes) - %s)" % self.a.generateSetExpression()
    def __repr__(self):
        return "NOT:(%s)" % str(self.a)

class SearchTerm(object):
    def __init__(self, tokens):
        self.term = tokens[0]
    def generateSetExpression(self):
        if self.term in recipesByIngredient:
            return "set(recipesByIngredient['%s'])" % self.term
        else:
            return "set()"
    def __repr__(self):
        return self.term

and_ = CaselessLiteral("and")
or_ = CaselessLiteral("or")
not_ = CaselessLiteral("not")

searchTerm = Word(alphanums) | quotedString.setParseAction( removeQuotes )
searchTerm.setParseAction(SearchTerm)
searchExpr = operatorPrecedence( searchTerm,[(not_, 1, opAssoc.RIGHT, SearchNot),
                                             (and_, 2, opAssoc.LEFT, SearchAnd),
                                             (or_, 2, opAssoc.LEFT, SearchOr)])
