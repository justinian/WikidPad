"""Python code for building a parser from a grammar

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: kjParseBuild.py,v 1.1 2005/06/05 05:51:05 jhorman Exp $:
"""

# BUGS:
#  A bad grammar that has no derivations for
#  the root nonterminal may cause a name error
#  on the variable "GoodStartingPlace"

# this needs to be modified so the RULEGRAM is loaded from a
# compiled representation if available.

import string
import kjSet
import kjParser
import re

# import some constants
from kjParser import TERMFLAG, NOMATCHFLAG, MOVETOFLAG, REDUCEFLAG, \
    TRANSFLAG, KEYFLAG, NONTERMFLAG, TERMFLAG, EOFFLAG, ENDOFFILETOKEN

PMODULE = kjParser.THISMODULE

# errors raised here
TokenError = "TokenError" # may happen on autogen with bad grammar
NotSLRError = "NotSLRError" # may happen for nonSLR grammar

# set this flag to abort automatic generation on Errors
ABORTONERROR = 0

# token used to mark null productions
NULLTOKEN = (None,None)


class CFSMachine(kjParser.FSMachine):
    ''' a derived FSM class, with closure computation methods defined
        (compilable FSMachine)
    '''
    def __init__(self, nonterm):
        kjParser.FSMachine.__init__(self, nonterm)

    def Eclosure(self, Epsilon, DoNullMaps=0):
        ''' return the epsilon closure of the FSM as a new FSM

            DoNullMap, if set, will map unexpected tokens to
            the "empty" state (usually creating a really big fsm)
        '''
        Closure = CFSMachine( self.root_nonTerminal )

        # compute the Epsilon Graph between states
        EGraph = kjSet.NewDG([])
        for State in range(0,self.maxState+1):
            # every state is E-connected to self
            kjSet.AddArc( EGraph, State, State )
            # add possible transition on epsilon (ONLY ONE SUPPORTED!)
            key = (State, Epsilon)
            if self.StateTokenMap.has_key(key):
                keymap = self.StateTokenMap[key]
                if keymap[0][0] != MOVETOFLAG:
                    raise TypeError, "unexpected map type in StateTokenMap"
                for (Flag,ToState) in keymap:
                    kjSet.AddArc( EGraph, State, ToState )
        #endfor
        # transitively close EGraph
        kjSet.TransClose( EGraph )

        # Translate EGraph into a dictionary of lists
        EMap = {}
        for State in range(0,self.maxState+1):
            EMap[State] = kjSet.Neighbors( EGraph, State )

        # make each e-closure of each self.state a state of the closure FSM.
        # here closure states assumed transient -- reset elsewhere.
        # first do the initial state
        Closure.States[ Closure.initial_state ] = \
           [TRANSFLAG, kjSet.NewSet(EMap[self.initial_state]) ]
        # do all other states (save initial and successful final states)
        #for State in range(0,self.maxState+1):
        #   if State != self.initial_state \
        #    and State != self.successful_final_state:
        #      Closure.NewSetState(TRANSFLAG, kjSet.NewSet(EMap[State]) )
        ##endfor

        # compute set of all known tokens EXCEPT EPSILON
        Tokens = kjSet.NewSet( [] )
        for (State, Token) in self.StateTokenMap.keys():
            if Token != Epsilon:
                kjSet.addMember(Token, Tokens)
        # tranform it into a list
        Tokens = kjSet.get_elts(Tokens)

        # for each state of the the closure FSM (past final) add transitions
        # and add new states as needed until all states are processed
        # (uses convention that states are allocated sequentially)
        ThisClosureState = 1
        while ThisClosureState <= Closure.maxState:
            MemberStates = kjSet.get_elts(Closure.States[ThisClosureState][1])
            # for each possible Token, compute the union UTrans of all
            # e-closures for all transitions for all member states,
            # on the Token, make  UTrans a new state (if needed),
            # and transition ThisClosureState to UTrans on Token
            for Token in Tokens:
                UTrans = kjSet.NewSet( [] )
                for MState in MemberStates:
                    # if MState has a transition on Token, include
                    # EMap for the destination state
                    key = (MState, Token)
                    if self.StateTokenMap.has_key(key):
                        DStateTup = self.StateTokenMap[key]
                        if DStateTup[0][0] != MOVETOFLAG:
                            raise TypeError, "unknown map type"
                        for (DFlag, DState) in DStateTup:
                            for EDState in EMap[DState]:
                                kjSet.addMember(EDState, UTrans)
                    #endif
                #endfor MState
                # register UTrans as a new state if needed
                UTState = Closure.NewSetState(TRANSFLAG, UTrans)
                # record transition from
                # ThisClosureState to UTState on Token
                if DoNullMaps:
                    Closure.SetMap( ThisClosureState, Token, UTState)
                else:
                    if not kjSet.Empty(UTrans):
                        Closure.SetMap( ThisClosureState, Token, UTState)
            #endfor Token
            ThisClosureState = ThisClosureState +1
        #endwhile
        return Closure

    def NewSetState(self, kind, InSet):
        ''' add an set-marked state to self if not present
            uses self.States[s][1] as the set marking the state s

            only used by Eclosure above
        '''
        # return existing state if one is present that matches the set
        LastState= self.maxState
        # skip state 0 (successful final state)???
        for State in range(1,LastState+1):
            MarkSet = self.States[State][1]
            if kjSet.Same(InSet,MarkSet):
                return State  # nonlocal
        #endfor
        # if not exited then allocate a new state
        LastState = LastState + 1
        self.States[LastState] = [ kind , InSet ]
        self.maxState = LastState
        return LastState


class Ruleset:
    ''' Ruleset class, used to compute NFA and then DFA for parsing based on
        a list of rules.
    '''
    def __init__(self, StartNonterm, Rulelist):
        self.StartNonterm = StartNonterm
        self.Rules = Rulelist

    def compFirst(self):
        ''' method to compute prefixes and First sets for nonterminals
        '''
        # uses the special null production token NULLTOKEN
        # snarfed directly from Aho+Ullman (terminals glossed)
        First = kjSet.NewDG([])
        # repeat the while loop until no change is made to First
        done = 0
        while not done:
            # assume we're done until a change is made to First
            done = 1

            # iterate through all rules looking for a new arc to add
            # indicating Terminal > possible first token derivation
            #
            for R in self.Rules:
                GoalNonterm = R.Nonterm
                Bodylength = len(R.Body)
                # look through the body of the rule up to the token with
                # no epsilon production (yet seen)
                Bodyindex = 0
                Processindex = 1
                while Processindex:
                    # unless otherwise indicated below, don't go to next token
                    Processindex = 0

                    # if index is past end of body then record
                    # an epsilon production for this nonterminal
                    if Bodyindex >= Bodylength:
                        if not kjSet.HasArc(First, GoalNonterm, NULLTOKEN ):
                            kjSet.AddArc( First, GoalNonterm, NULLTOKEN )
                            done = 0 # change made to First
                    else:
                        # otherwise try to add firsts of this token
                        # to firsts of the Head of the rule.
                        Token = R.Body[Bodyindex]
                        (type, name) = Token
                        if type in (KEYFLAG,TERMFLAG):
                            # try to add this terminal to First for GoalNonterm
                            if not kjSet.HasArc(First, GoalNonterm, Token):
                                kjSet.AddArc( First, GoalNonterm, Token)
                                done = 0
                        elif type == NONTERMFLAG:
                            # try to add each First entry for nonterminal
                            # to First entry for GoalNonterm
                            for FToken in kjSet.Neighbors( First, Token ):
                                if not kjSet.HasArc(First, GoalNonterm, FToken):
                                    kjSet.AddArc( First, GoalNonterm, FToken)
                                    done = 0
                            # does this nonterminal have a known e production?
                            if kjSet.HasArc( First, Token, NULLTOKEN ):
                                # if so, process next token in rule
                                Processindex = 1
                        else:
                            raise TokenError, "unknown token type in rule body"
                    #endif
                    Bodyindex = Bodyindex + 1
                #endwhile Processindex
            #endfor R in self.Rules
        #endwhile not done
        self.First = First

    def compFollow(self):
        ''' computing the Follow set for the ruleset
            the good news: I think it's correct.
            the bad news: It's slower than it needs to be for epsilon cases.
        '''
        Follow = kjSet.NewDG([])

        # put end marker on follow of start nonterminal
        kjSet.AddArc(Follow, self.StartNonterm, kjParser.ENDOFFILETOKEN)

        # now compute other follows using the rules;
        # repeat the loop until no change to Follow.
        while not self.compFollowRules(Follow):
            pass

        self.Follow = Follow

    def compFollowRules(self, Follow):
        done = 1 # assume done unless Follow changes
        for R in self.Rules:
            newdone = self.compFollowRule(Follow, R)
            if not newdone: done = 0
        return done

    def compFollowRule(self, Follow, R):
        done = 1
        # work backwards in the rule body to
        # avoid retesting for epsilon nonterminals
        Bodylength = len(R.Body)
        # the tail of rule may expand to null
        EpsilonTail = 1
        # loop starts at the last
        for BodyIndex in range(Bodylength-1, -1, -1):
            Token = R.Body[BodyIndex]
            (Ttype,Tname) = Token

            if Ttype not in (KEYFLAG, TERMFLAG, NONTERMFLAG):
                raise TokenError, "unknown token type in rule body"

            if Ttype in (KEYFLAG,TERMFLAG):
                # keywords etc cancel epsilon tail, otherwise ignore
                EpsilonTail = 0
                continue

            # if the tail expands to epsilon, map
            # follow for the goal nonterminal to this token
            # and also follow for the tail nonterms
            if EpsilonTail:
                # add follow for goal
                for FToken in kjSet.Neighbors(Follow,R.Nonterm):
                    if not kjSet.HasArc(Follow, Token, FToken):
                        kjSet.AddArc(Follow, Token, FToken)
                        # follow changed, loop again
                        done = 0
                # add follow for tail members
                #for Index2 in range(BodyIndex+1, Bodylength):
                #   TailToken = R.Body[Index2]
                #   for FToken in kjSet.Neighbors(Follow,TailToken):
                #       if not kjSet.HasArc(Follow,Token,FToken):
                #          kjSet.AddArc(Follow,Token,FToken)
                #          done = 0
            #endif EpsilonTail

            # if we are not at the end use First set for next token
            if BodyIndex != Bodylength-1:
                NextToken = R.Body[BodyIndex+1]
                (NTtype, NTname) = NextToken
                if NTtype in (KEYFLAG,TERMFLAG):
                    if not kjSet.HasArc(Follow, Token, NextToken):
                        kjSet.AddArc(Follow, Token, NextToken)
                        done = 0
                elif NTtype == NONTERMFLAG:
                    for FToken in kjSet.Neighbors(self.First, NextToken):
                        if FToken != NULLTOKEN:
                            if not kjSet.HasArc(Follow, Token, FToken):
                                kjSet.AddArc(Follow, Token, FToken)
                                done = 0
                            continue
                        # next token expands to epsilon:
                        # add its follow, unless already done above
                        for FToken in kjSet.Neighbors(Follow, NextToken):
                            if not kjSet.HasArc(Follow, Token, FToken):
                                kjSet.AddArc(Follow, Token, FToken)
                                done = 0
                else:
                    raise TokenError, "unknown token type in rule body"

            # finally, check whether next iteration has epsilon tail
            if not kjSet.HasArc(self.First, Token, NULLTOKEN):
                EpsilonTail = 0

        return done

    def DumpFirstFollow(self):
        First = self.First
        Follow = self.Follow
        print "First:"
        for key in First.keys():
            name = key[1]
            print name," :: ",
            for (flag2,name2) in First[key].keys():
                print name2,", ",
            print
        print "Follow:"
        for key in Follow.keys():
            name = key[1]
            print name," :: ",
            for (flag2,name2) in Follow[key].keys():
                print name2,", ",
            print

    def FirstOfTail(self, Rule, TailIndex, Token=None):
        ''' computing the "first" of the tail of a rule followed by an optional
            terminal.

            doesn't include NULLTOKEN
            requires self.First to be computed
        '''
        Result = kjSet.NewSet( [] )
        # go through all tokens in rule tail so long as there is a
        #  null derivation for the remainder
        Nullprefix = 1
        BodyLength = len(Rule.Body)
        ThisIndex = TailIndex
        while Nullprefix and ThisIndex < BodyLength:
            RToken = Rule.Body[ThisIndex]
            (RTtype, RTname) = RToken
            if RTtype == NONTERMFLAG:
                for FToken in kjSet.Neighbors(self.First, RToken):
                    if FToken != NULLTOKEN:
                        kjSet.addMember(FToken, Result)
                #endfor
                # check whether this symbol might have a null production
                if not kjSet.HasArc(self.First, RToken, NULLTOKEN):
                    Nullprefix = 0
            elif RTtype in [KEYFLAG, TERMFLAG]:
                kjSet.addMember(RToken, Result)
                Nullprefix = 0
            else:
                raise TokenError, "unknown token type in rule body"
            ThisIndex = ThisIndex + 1
        #endwhile
        # add the optional token if given and Nullprefix still set
        if Nullprefix and Token != None:
            kjSet.addMember(Token, Result)
        return Result

    def compSLRNFA(self):
        '''compute an SLR NFA for the ruleset with states for each SLR "item"
           and transitions, eg:
               X > .AB
             on A maps to X > A.B
             on epsilon maps to A > .ZC
                            and A > .WK
           an item is a pair (rulenumber, bodyposition)
           where body position 0 is interpreted to point before the
           beginning of the body.

           SLR = "simple LR" in Aho+Ullman terminology
        '''
        NFA = CFSMachine(self.StartNonterm)
        Nrules = len(self.Rules)
        itemStateMap = {}
        for Ruleindex in range(0,Nrules):
            Rule = self.Rules[Ruleindex]
            # make an item for each "dot" position in the body
            for DotPos in range(0, len(Rule.Body) + 1):
                item = (Ruleindex, DotPos)
                itemState = NFA.NewState(TRANSFLAG, [item])
                itemStateMap[item] = itemState
            #endfor DotPos
        #endfor Ruleindex

        # now that the states are initialized
        # compute transitions except for the last item of a rule
        # (which has none)
        for Ruleindex in range(0,Nrules):
            Rule = self.Rules[Ruleindex]
            for DotPos in range(0, len(Rule.Body)):
                item = (Ruleindex, DotPos)
                CurrentToken = Rule.Body[DotPos]
                ThisState = itemStateMap[item]
                NextState = itemStateMap[ (Ruleindex, DotPos + 1) ]
                NFA.SetMap( ThisState, CurrentToken, NextState  )
                # if the current token is a nonterminal
                # ad epsilon transitions to first item for any
                # rule that derives this nonterminal
                (CTtype, CTname) = CurrentToken
                if CTtype == NONTERMFLAG:
                    for Rule2index in range(0,Nrules):
                        Rule2 = self.Rules[Rule2index]
                        Head = Rule2.Nonterm
                        if Head == CurrentToken:
                            NextState = itemStateMap[( Rule2index, 0 )]
                            NFA.SetMap( ThisState, NULLTOKEN, NextState )
                    #endfor Rule2index
                #endif CTtype == NONTERMFLAG
            #endfor DotPos
        #endfor Ruleindex

        # must handle the initial state properly here!
        # Make a dummy state with e-transitions to all first items
        # for rules that derive the initial nonterminal
        ThisState = NFA.initial_state
        GoodStartingPlace = None
        for Ruleindex in range(0,Nrules):
            Rule = self.Rules[Ruleindex]
            Head = Rule.Nonterm
            if Head == self.StartNonterm:
                GoodStartingPlace= (Ruleindex, 0)
                NextState = itemStateMap[ GoodStartingPlace ]
                NFA.SetMap( ThisState, NULLTOKEN, NextState )
        # fix the NFA.States entry
        if GoodStartingPlace == None:
            raise NotSLRError, "No derivation for root nonterminal."
        NFA.States[ NFA.initial_state ] = \
             [ 'transient', GoodStartingPlace ]

        self.SLRNFA = NFA
    #enddef compSLRNFA

    def ItemDump(self, item):
        ''' dump an item
        '''
        (ruleindex, position) = item
        Rule = self.Rules[ruleindex]
        print Rule.Nonterm[1],' >> ',
        for bindex in range(0, len(Rule.Body)):
            if position == bindex:
                print " (*) ",
            print Rule.Body[bindex][1],
        if position == len(Rule.Body):
            print " (*) "
        else:
            print

    def SLRItemIsFinal(self, item):
        ''' utility function -- returns true if an item is a final item
        '''
        (ruleindex, position) = item
        Rule = self.Rules[ruleindex]
        if position == len(Rule.Body):
            return 1
        else:
            return 0

    def DumpSLRNFA(self):
        ''' dump the NFA
        '''
        NFA = self.SLRNFA
        print "root: ", NFA.root_nonTerminal
        for key in NFA.StateTokenMap.keys():
            map = NFA.StateTokenMap[key]
            (fromstate, token) = key
            fromitem = NFA.States[ fromstate ][1]
            self.ItemDump(fromitem)
            print " on ", token[1], " maps "
            for Tostate in map:
                Toitem = NFA.States[Tostate][1]
                print "    ",
                self.ItemDump(Toitem)

    def compDFA(self):
        ''' compute DFA for ruleset by computing the E-closure of the NFA
        '''
        self.DFA = self.SLRNFA.Eclosure(NULLTOKEN)

    def DumpDFAsets(self):
        DFA = self.DFA
        print "root: ", DFA.root_nonTerminal
        for State in range(1, len(DFA.States) ):
            self.DumpItemSet(State)

    def DumpItemSet(self,State):
        DFA = self.DFA
        NFA = self.SLRNFA
        print
        print "STATE ", State, " *******"
        fromNFAindices = kjSet.get_elts(DFA.States[State][1])
        for NFAindex in fromNFAindices:
            item = NFA.States[NFAindex][1]
            print "  ", NFAindex, ": ",
            self.ItemDump(item)

    def SLRFixDFA(self):
        '''this function completes the computation of an SLR DFA
           by adding reduction states for each DFA state S containing
           item   H > B.
           which reduces rule H > B
           for each token T in Follow of H.
           if S already has a transition for T then there is a conflict!

           assumes DFA and SLRNFA and Follow have been computed.
        '''
        DFA = self.DFA
        NFA = self.SLRNFA
        # look through the states (except 0=success) of the DFA
        # initially don't add any new states, just record
        # actions to be done
        #   uses convention that 0 is successful final state

        # ToDo is a dictionary which maps
        #     (State, Token) to a item to reduce
        ToDo = {}
        Error = None
        for State in range(1, len(DFA.States) ):
            # look for a final item for a rule in this state
            fromNFAindices = kjSet.get_elts(DFA.States[State][1])
            for NFAindex in fromNFAindices:
                item = NFA.States[NFAindex][1]
                # if the item is final remember to do the reductions...
                if self.SLRItemIsFinal(item):
                    (ruleindex, position) = item
                    Rule = self.Rules[ruleindex]
                    Head = Rule.Nonterm
                    Following = kjSet.Neighbors( self.Follow, Head )
                    for Token in Following:
                        key = (State, Token)
                        if not ToDo.has_key(key):
                            ToDo[ key ] = item
                        else:
                            # it might be okay if the items are identical?
                            item2 = ToDo[key]
                            if item != item2:
                                print "reduce/reduce conflict on ",key
                                self.ItemDump(item)
                                self.ItemDump(item2)
                            Error = " apparent reduce/reduce conflict"
                        #endif
                    #endfor
                #endif
            #endfor NFAindex
        #endfor State

        # for each (State,Token) pair which indicates a reduction
        # record the reduction UNLESS the map is already set for the pair
        for key in ToDo.keys():
            (State,Token) = key
            item = ToDo[key]
            (rulenum, dotpos) = item
            ExistingMap = DFA.map( State, Token )
            if ExistingMap[0] == NOMATCHFLAG:
                DFA.SetReduction( State, Token, rulenum )
            else:
                print "apparent shift/reduce conflict"
                print "reduction: ", key, ": "
                self.ItemDump(item)
                print "existing map ", ExistingMap
                Error = " apparent shift/reduce conflict"
        #endfor
        if Error and ABORTONERROR:
            raise NotSLRError, Error
    #enddef SLRfixDFA()

    def DoSLRGeneration(self):
        ''' do complete SLR DFA creation starting after initialization
        '''
        self.compFirst()
        self.compFollow()
        self.compSLRNFA()
        self.compDFA()
        self.SLRFixDFA()


################ the following are interpretation functions
################ used by RULEGRAM meta grammar
# some constants used here
COMMENTFORM = "##.*\n"
RSKEY = "@R"
COLKEY = "::"
LTKEY = ">>"
IDNAME = "ident"
# an identifier in the meta grammar is any nonwhite string
# except the keywords @R :: >> or comment flag ##
IDFORM = "[^" + string.whitespace + "]+"

def IdentFun(string):
    ''' for identifiers simply return the string
    '''
    return string

def RootReduction(list, ObjectGram):
    ''' RootReduction should receive list of form
       [ nontermtoken, keyword COLKEY, RuleList ]
    '''
    if len(list) != 3 or list[1] != COLKEY:
        raise FlowError, "unexpected metagrammar root reduction"
    return (list[0], list[2])

def NullRuleList(list, ObjectGram):
    ''' NullRuleList should receive list of form []
    '''
    if list != []:
        raise FlowError, "unexpected null RuleList form"
    return []

def FullRuleList(list, ObjectGram):
    ''' FullRuleList should receive list of form
          [ Rule, RuleList ]
    '''
    if type(list) != type([]) or len(list)!=2:
        raise FlowError, "unexpected full RuleList form"
    NewRule = list[0]
    OldRules = list[1]
    return [NewRule] + OldRules

def InterpRule(list, ObjectGram):
    ''' InterpRule should receive list of form
         [keyword RSKEY,
          RuleNameStr,
          keyword COLKEY,
          Nontermtoken,
          keyword LTKEY,
          Bodylist]
    '''
    # check keywords:
    if len(list)!=6 or list[0]!=RSKEY or list[2]!=COLKEY or list[4]!=LTKEY:
        raise FlowError, "unexpected meta rule reduction form"
    ruleName = list[1]
    ruleNonterm = list[3]
    ruleBody = list[5]
    # upcase the the representation of keywords if needed
    if not ObjectGram.LexD.isCaseSensitive():
        for i in range(0,len(ruleBody)):
            (flag, name) = ruleBody[i]
            if flag == KEYFLAG:
                ruleBody[i] = (KEYFLAG, string.upper(name))
            elif not flag in (TERMFLAG, NONTERMFLAG):
                raise FlowError, "unexpected rule body member"
    rule = kjParser.ParseRule( ruleNonterm, ruleBody )
    rule.Name = ruleName
    return rule

def InterpRuleName(list, ObjectGram):
    ''' InterpRuleName should receive
          [ string ]
    '''
    # add error checking?
    return list[0]

def InterpNonTerm(list, ObjectGram):
    ''' InterpNonTerm should receive
          [ string ]
    '''
    if type(list)!=type([]) or len(list)!=1:
        raise FlowError, "unexpected rulename form"
    Name = list[0]
    # determine whether this is a valid nonterminal
    if not ObjectGram.NonTermDict.has_key(Name):
        raise TokenError, "LHS of Rule must be nonterminal: "+Name
    return ObjectGram.NonTermDict[Name]

def NullBody(list, ObjectGram):
    ''' NullBody should receive []
    '''
    if list != []:
        raise FlowError, "unexpected null Body form"
    return []

def FullBody(list,ObjectGram):
    ''' FullBody should receive
        [ string, Bodylist]
       must determine whether the string represents
       a keyword, a nonterminal, or a terminal of the object
       grammar.
       returns (KEYFLAG, string) (TERMFLAG, string) or
               (NONTERMFLAG, string) respectively
    '''
    if type(list)!=type([]) or len(list)!=2:
        raise FlowError, "unexpected body form"
    Name = list[0]
    # Does the Name rep a nonterm, keyword or term
    # of the object grammar (in that order).
    if ObjectGram.NonTermDict.has_key(Name):
        kind = NONTERMFLAG
    elif ObjectGram.LexD.keywordmap.has_key(Name):
        kind = KEYFLAG
    elif ObjectGram.TermDict.has_key(Name):
        kind = TERMFLAG
    else:
        raise TokenError, "Rule body contains unregistered string: "+Name
    restOfBody = list[1]
    return [(kind, Name)] + restOfBody

def ruleGrammar():
    ''' function to generate a grammar for parsing grammar rules
    '''
    LexD = kjParser.LexDictionary()
    # use SQL/Ansi style comments
    LexD.comment( COMMENTFORM )
    # declare keywords
    RStart = LexD.keyword( RSKEY )
    TwoColons = LexD.keyword( COLKEY )
    LeadsTo = LexD.keyword( LTKEY )
    # declare terminals
    ident = LexD.terminal(IDNAME, IDFORM, IdentFun )
    # declare nonterminals
    Root = kjParser.nonterminal("Root")
    Rulelist = kjParser.nonterminal("RuleList")
    Rule = kjParser.nonterminal("Rule")
    RuleName = kjParser.nonterminal("RuleName")
    NonTerm = kjParser.nonterminal("NonTerm")
    Body = kjParser.nonterminal("Body")

    # declare rules
    #   Root >> NonTerm :: Rulelist
    InitRule = kjParser.ParseRule( Root, \
                [NonTerm, TwoColons, Rulelist], RootReduction )
    #   Rulelist >>
    RLNull = kjParser.ParseRule( Rulelist, [], NullRuleList)
    #   Rulelist >> Rule Rulelist
    RLFull = kjParser.ParseRule( Rulelist, [Rule,Rulelist], FullRuleList)
    #   Rule >> "@R :: NonTerm >> Body
    RuleR = kjParser.ParseRule( Rule, \
       [RStart, RuleName, TwoColons, NonTerm, LeadsTo, Body],\
       InterpRule)
    #   Rulename >> ident
    RuleNameR = kjParser.ParseRule( RuleName, [ident], InterpRuleName)
    #   NonTerm >> ident
    NonTermR = kjParser.ParseRule( NonTerm, [ident], InterpNonTerm)
    #   Body >>
    BodyNull = kjParser.ParseRule( Body, [], NullBody)
    #   Body >> ident Body
    BodyFull = kjParser.ParseRule( Body, [ident,Body], FullBody)

    # declare Rules list and Associated Name dictionary
    Rules = [RLNull, RLFull, RuleR, RuleNameR, NonTermR,\
                 BodyNull, BodyFull, InitRule]
    RuleDict = \
     { "RLNull":0, "RLFull":1, "RuleR":2, "RuleNameR":3, \
       "NonTermR":4, "BodyNull":5, "BodyFull":6 , "InitRule":7 }
    # make the RuleSet and compute the associate DFA
    RuleSet = Ruleset( Root, Rules )
    RuleSet.DoSLRGeneration()
    # construct the Grammar object
    Result = kjParser.Grammar( LexD, RuleSet.DFA, Rules, RuleDict )
    return Result

#enddef RuleGrammar()


# this is the rule grammar object for parsing
RULEGRAM = ruleGrammar()

class CGrammar(kjParser.Grammar):
    ''' a derived grammar class
        this is a compilable grammar for automatic parser generation.
    '''

    def Keywords(self, Stringofkeys):
        ''' insert a white separated list of keywords into the LexD
            TODO: THIS SHOULD CHECK FOR KEYWORD/NONTERMINAL/PUNCT NAME
            COLLISIONS (BUT DOESN'T YET).
        '''
        keywordlist = string.split(Stringofkeys)
        for keyword in keywordlist:
            self.LexD.keyword( keyword )

    def punct(self, Stringofpuncts):
        ''' insert a string of punctuations into the LexD
        '''
        for p in Stringofpuncts:
            self.LexD.punctuation(p)

    def comments(self, listOfCommentStrings):
        ''' register a list of regular expression strings
            to represent comments in LexD
        '''
        for str in listOfCommentStrings:
            self.LexD.comment(str)

    def Nonterms(self, StringofNonterms):
        ''' register a white separated list of nonterminal strings
        '''
        nonTermlist = string.split(StringofNonterms)
        for NonTerm in nonTermlist:
            self.NonTermDict[NonTerm] = kjParser.nonterminal(NonTerm)

    def Declarerules(self, StringWithRules):
        ''' initialize or add more rules to the RuleString
        '''
        self.RuleString = self.RuleString + "\n" + StringWithRules

    def Compile(self, MetaGrammar=RULEGRAM):
        ''' The compilation function assumes
              NonTermDict
              RuleString
              LexD
              TermDict
            have all been set up properly
            (at least if the default MetaGrammar is used).
            On successful completion it will set up
              DFA
              RuleL
              RuleNameToIndex

            the following should return a list of rules
            with punctuations of self.LexD interpreted as trivial keywords
              keywords of seld.LexD interpreted as keywords
            and nonterminals registered in NonTermDict interpreted as
            nonterms.
             ParseResult should be of form ( (rootNT, RuleL), self )
        '''
        ParseResult = MetaGrammar.DoParse1( self.RuleString, self )
        (RootNonterm, Rulelist) = ParseResult

        # make a ruleset and compute its DFA
        RuleS = Ruleset( RootNonterm, Rulelist )
        RuleS.DoSLRGeneration()

        # make the rulename to index map to allow future bindings
        for i in range(0,len(Rulelist)):
            Rule = Rulelist[i]
            self.RuleNameToIndex[ Rule.Name ] = i

        # fill in the blanks
        self.DFA = RuleS.DFA
        self.RuleL = Rulelist

        # FOR DEBUG AND TESTING
        self.Ruleset = RuleS

        # DON'T clean up the grammar (misc structures are used)
        # in future bindings
    #enddef Compile

    def Reconstruct(self, VarName, Tofile, FName=None, indent=""):
        ''' Write a reconstructable representation for this grammar to a file
           EXCEPT:
             - rule associations to reduction functions
               will be lost (must be reset elsewhere)
             - terminals in the lexical dictionary
               will not be initialized

           IND is used for indentation, should be whitespace (add check!)

           FName if given will cause the reconstructed to be placed
           inside a function `FName`+"()" returning the grammar object

           NOTE: this function violates information hiding principles;
            in particular it "knows" the guts of the FSM and LexD classes
        '''
        Reconstruction = codeReconstruct(VarName, Tofile, self, FName, indent)
        GrammarDumpSequence(Reconstruction)

    def MarshalDump(self, Tofile):
        ''' marshalling of a grammar to a file
        '''
        Reconstruction = marshalReconstruct(self, Tofile)
        GrammarDumpSequence(Reconstruction)

#endclass CGrammar

def GrammarDumpSequence(ReconstructObj):
    ''' general procedure for different types of archiving for grammars
    '''
    # assume an initialized Reconstruct Object with appropriate grammar etc.
    # put the lexical part
    ReconstructObj.PutLex()
    # put the rules
    ReconstructObj.PutRules()
    # put transitions
    ReconstructObj.PutTransitions()
    # finish up
    ReconstructObj.Cleanup()

def NullCGrammar():
    ''' function to create a "null CGrammar"
    '''
    return CGrammar(None,None,None,{})


# utility classes
class Reconstruct:
    ''' Grammar reconstruction objects encapsulate the process of grammar
        archiving.

        This "virtual class" is only for common behaviors of subclasses.
    '''
    def MakeTokenArchives(self):
        # make a list of all tokens and
        # initialize token > int dictionary
        keys = self.Gram.DFA.StateTokenMap.keys()
        tokenToInt = {}
        tokenSet = kjSet.NewSet([])
        for k in keys:
            kjSet.addMember(k[1], tokenSet)
        tokens = kjSet.get_elts(tokenSet)
        for i in range(0,len(tokens)):
            tokenToInt[ tokens[i] ] = i

        self.keys = keys
        self.tokens = tokens # global sub
        self.tokInt = tokenToInt # global sub

class codeReconstruct(Reconstruct):
    ''' grammar reconstruction to a file
    '''
    def __init__(self, VarName, Tofile, Grammar, FName=None, indent =""):
        # do global subs for each of these
        self.Var = VarName
        self.File = Tofile
        self.FName = FName
        self.Gram = Grammar

        # put the reconstruction in a function if FName is given
        if FName != None:
            Tofile.write("\n\n")
            Tofile.write(indent+"def "+FName+"():\n")
            IND = indent+"   "
        else:
            IND = indent
        self.I = IND # global sub!
        Tofile.write("\n\n")
        Tofile.write(IND+"# ***************************BEGIN RECONSTRUCTION\n")
        Tofile.write(IND+"# Python declaration of Grammar variable "+VarName+".\n")
        Tofile.write(IND+"# automatically generated by module "+PMODULE+".\n")
        Tofile.write(IND+"# Altering this sequence by hand will probably\n")
        Tofile.write(IND+"# leave it unusable.\n")
        Tofile.write(IND+"#\n")
        Tofile.write(IND+"import "+PMODULE+"\n\n")
        Tofile.write(IND+"# variable declaration:\n")
        Tofile.write(IND+VarName+"= "+PMODULE+".NullGrammar()\n\n")

        # make self.keys list of dfa keys,
        #      self.tokens list of grammar tokens,
        #      self.tokInt inverted dictionary for self.tokens
        self.MakeTokenArchives()

        Tofile.write("\n\n"+IND+"# case sensitivity behavior for keywords.\n")
        if self.Gram.LexD.isCaseSensitive():
            Tofile.write(IND+VarName+".SetCaseSensitivity(1)\n")
        else:
            Tofile.write(IND+VarName+".SetCaseSensitivity(0)\n")
    #enddef __init__

    def PutLex(self):
        IND = self.I
        Tofile = self.File
        VarName = self.Var
        LexD = self.Gram.LexD
        tokens = self.tokens

        Tofile.write("\n\n"+IND+"# declaration of lexical dictionary.\n")
        Tofile.write(IND+"# EXCEPT FOR TERMINALS\n")
        Tofile.write(IND+VarName+".LexD.punctuationlist = ")
        Tofile.write(`LexD.punctuationlist`+"\n")
        Tofile.write(IND+"# now comment patterns\n")
        for comment in LexD.commentstrings:
            Tofile.write(IND+VarName+".LexD.comment("+`comment`+")\n")
        Tofile.write(IND+"# now define tokens\n")
        for i in range(0,len(tokens)):
            tok = tokens[i]
            (kind, name) = tok
            if kind == TERMFLAG:
                # put warning at end!
                #  nonterminal not installed in lexical dictionary here!
                Tofile.write(IND+VarName+".IndexToToken["+`i`+"] = ")
                Tofile.write(PMODULE+".termrep("+`name`+")\n")
            elif kind == KEYFLAG:
                Tofile.write(IND+VarName+".IndexToToken["+`i`+"] = ")
                Tofile.write(VarName+".LexD.keyword("+`name`+")\n")
            elif kind == NONTERMFLAG:
                Tofile.write(IND+VarName+".IndexToToken["+`i`+"] = ")
                Tofile.write(PMODULE+".nonterminal("+`name`+")\n")
            else:
                raise FlowError, "unknown token type"
    #enddef PutLex

    def PutRules(self):
        IND = self.I
        VarName = self.Var
        Rules = self.Gram.RuleL
        Tofile = self.File
        Root = self.Gram.DFA.root_nonTerminal
        Tofile.write("\n\n"+IND+"# declaration of rule list with names.\n")
        Tofile.write(IND+"# EXCEPT FOR INTERP FUNCTIONS\n")
        nrules = len(Rules)
        Tofile.write(IND+VarName+".RuleL = [None] * "+`nrules`+"\n")
        for i in range(0,nrules):
            # put warning at end:
            #  rule reduction function not initialized here!
            rule = Rules[i]
            name = rule.Name
            Tofile.write(IND+"rule = "+`rule`+"\n")
            Tofile.write(IND+"name = "+`name`+"\n")
            Tofile.write(IND+"rule.Name = name\n")
            Tofile.write(IND+VarName+".RuleL["+`i`+"] = rule\n")
            Tofile.write(IND+VarName+".RuleNameToIndex[name] = "+`i`+"\n")

        Tofile.write("\n\n"+IND+"# DFA root nonterminal.\n")
        Tofile.write(IND+VarName+".DFA.root_nonTerminal =")
        Tofile.write(`Root`+"\n")
    #enddef PutRules

    def PutTransitions(self):
        IND = self.I
        Tofile = self.File
        VarName = self.Var
        maxState = self.Gram.DFA.maxState
        tokenToInt = self.tokInt
        StateTokenMap = self.Gram.DFA.StateTokenMap
        keys = self.keys

        Tofile.write("\n\n"+IND+"# DFA state declarations.\n")
        for state in range(1, maxState+1):
            Tofile.write(IND+VarName+".DFA.States["+`state`+"] = ")
            Tofile.write('['+`TRANSFLAG`+']\n')
        Tofile.write(IND+VarName+".DFA.maxState = "+`maxState`+"\n")

        Tofile.write("\n\n"+IND+"# DFA transition declarations.\n")
        for key in keys:
            (fromState, TokenRep) = key
            TokenIndex = tokenToInt[TokenRep]
            TokenArg = VarName+".IndexToToken["+`TokenIndex`+"]"
            TMap = StateTokenMap[key]
            TMaptype = TMap[0][0]
            if TMaptype == REDUCEFLAG:
                # reduction
                rulenum = TMap[0][1]
                Args = "("+`fromState`+","+TokenArg+","+`rulenum`+")"
                Tofile.write(IND+VarName+".DFA.SetReduction"+Args+"\n")
            elif TMaptype == MOVETOFLAG:
                # MoveTo
                Args = "("+`fromState`+","+TokenArg+","+`TMap[0][1]`+")"
                Tofile.write(IND+VarName+".DFA.SetMap"+Args+"\n")
            else:
                raise FlowError, "unexpected else (2)"
    #enddef

    def Cleanup(self):
        Tofile = self.File
        RuleL = self.Gram.RuleL
        tokens = self.tokens
        VarName = self.Var
        IND = self.I
        FName = self.FName

        Tofile.write("\n\n"+IND+"# Clean up the grammar.\n")
        Tofile.write(IND+VarName+".CleanUp()\n")

        # if the Fname was given return the grammar as function result
        if FName != None:
            Tofile.write("\n\n"+IND+"# return the grammar.\n")
            Tofile.write(IND+"return "+VarName+"\n")

        Tofile.write("\n\n"+IND+"# WARNINGS ****************************** \n")
        Tofile.write(IND+"# You must bind the following rule names \n")
        Tofile.write(IND+"# to reduction interpretation functions \n")
        for R in RuleL:
            Tofile.write(IND+"# "+VarName+".Bind("+`R.Name`+", ??function??)\n")
        Tofile.write(IND+"#(last rule)\n")

        Tofile.write("\n\n"+IND+"# WARNINGS ****************************** \n")
        Tofile.write(IND+"# You must bind the following terminals \n")
        Tofile.write(IND+"# to regular expressions and interpretation functions \n")
        warningPrinted = 0
        for tok in tokens:
            (kind, name) = tok
            if kind == TERMFLAG and tok != ENDOFFILETOKEN:
                Tofile.write(IND+"# "+VarName+\
                  ".Addterm("+`name`+", ??regularExp??, ??function??)\n")
                warningPrinted = 1
        if not warningPrinted:
            Tofile.write(IND+"#  ***NONE** \n")
        Tofile.write(IND+"#(last terminal)\n")
        Tofile.write(IND+"# ******************************END RECONSTRUCTION\n")
    #enddef
#endclass


class marshalReconstruct(Reconstruct):
    ''' Reconstruction using marshalling to a file encodes internal structures
        for grammar using marshal-able objects. Final marshalling to the file
        is done at CleanUp() storing one big list.
    '''
    def __init__(self, Grammar, Tofile):
        self.Gram = Grammar
        self.File = Tofile
        # should archive self.tokens structure
        self.MakeTokenArchives()
        # archive this
        self.CaseSensitivity = Grammar.LexD.isCaseSensitive()

    def PutLex(self):
        LexD = self.Gram.LexD
        # archive these
        self.punct = LexD.punctuationlist
        self.comments = LexD.commentstrings

    def PutRules(self):
        # archive this
        self.Root = self.Gram.DFA.root_nonTerminal
        # make a list of tuples that can be used with
        # rule = apply(ParseRule, tuple[1])
        # rule.Name = tuple[0]
        Rules = self.Gram.RuleL
        nrules = len(Rules)
        RuleTuples = [None] * nrules
        for i in range(nrules):
            rule = Rules[i]
            RuleTuples[i] = (rule.Name, rule.components())
        #archive this
        self.RuleTups = RuleTuples

    def PutTransitions(self):
        keys = self.keys
        tokenToInt = self.tokInt
        StateTokenMap = self.Gram.DFA.StateTokenMap

        # archive this
        self.MaxStates = self.Gram.DFA.maxState

        # create two lists,
        #   one for reductions with contents (fromState, tokennumber, rulenum)
        #   one for movetos with contents (fromstate, tokennumber, tostate)
        #      (note: token number not token itself to allow sharing)
        # to allow arbitrary growing, first use dicts:
        reductDict = {}
        nreducts = 0
        moveToDict = {}
        nmoveTos = 0
        for key in self.keys:
            (fromState, TokenRep) = key
            TokenIndex  = tokenToInt[TokenRep]
            TMap = StateTokenMap[key]
            TMaptype = TMap[0][0]
            if TMaptype == REDUCEFLAG:
                rulenum = TMap[0][1]
                reductDict[nreducts] = (fromState, TokenIndex, rulenum)
                nreducts = nreducts + 1
            elif TMaptype == MOVETOFLAG:
                ToState = TMap[0][1]
                moveToDict[nmoveTos] = (fromState, TokenIndex, ToState)
                nmoveTos = nmoveTos + 1
            else:
                raise FlowError, "unexpected else"
        #endfor
        # translate dicts to lists
        reducts = [None] * nreducts
        for i in range(nreducts):
            reducts[i] = reductDict[i]
        moveTos = [None] * nmoveTos
        for i in range(nmoveTos):
            moveTos[i] = moveToDict[i]

        # archive these
        self.reducts = reducts
        self.moveTos = moveTos

    # TODO: document this new marshalling method in the docco!
    def Cleanup(self):
        ''' this is the function that does the marshalling
        '''
        # dump the info
        self.File.write('tokens = %s\n'%`self.tokens`)
        self.File.write('punct = %s\n'%`self.punct`)
        self.File.write('comments = %s\n'%`self.comments`)
        self.File.write('RuleTups = %s\n'%`self.RuleTups`)
        self.File.write('MaxStates = %s\n'%`self.MaxStates`)
        self.File.write('reducts = %s\n'%`self.reducts`)
        self.File.write('moveTos = %s\n'%`self.moveTos`)
        self.File.write('Root = %s\n'%`self.Root`)
        self.File.write('CaseSensitivity = %s\n'%`self.CaseSensitivity`)

#
# $Log: kjParseBuild.py,v $
# Revision 1.1  2005/06/05 05:51:05  jhorman
# initial checkin
#
# Revision 1.6  2002/05/11 02:59:04  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
# Revision 1.5  2002/05/08 00:49:00  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.4  2002/05/07 07:06:11  richard
# Cleaned up sql grammar compilation some more.
# Split up the BigList into its components too.
#
# Revision 1.3  2002/05/07 04:03:14  richard
# . major cleanup of test_gadfly
#
# Revision 1.2  2002/05/06 23:27:09  richard
# . made the installation docco easier to find
# . fixed a "select *" test - column ordering is different for py 2.2
# . some cleanup in gadfly/kjParseBuild.py
# . made the test modules runnable (remembering that run_tests can take a
#   name argument to run a single module)
# . fixed the module name in gadfly/kjParser.py
#
# Revision 1.1.1.1  2002/05/06 07:31:09  richard
#
#
#
