# coding: utf-8
import re
from datetime import date

REPL = ((u'ä', u'ae'), (u'ö', u'oe'), (u'ü', u'ue'), 
        (u'ß', u'ss'), 
       )
rl = re.compile('[^a-z0-9]')

def str2id(s):
    s = unicode(s).lower()
    for i, o in REPL:
        s = s.replace(i, o)
    return rl.sub('_', s).strip('_')

def str2date(s):
    res = s.split('.')
    res.reverse()
    return date(*[int(n) for n in res])

def prettyFloat(f):
    s = unicode(f)
    return s.endswith(u'.0') and s[:-2] or s
