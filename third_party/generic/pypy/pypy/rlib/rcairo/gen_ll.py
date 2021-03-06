#!/usr/bin/env python

import sys
import ctypes
from pypy.rpython.tool import mkrffi

def proc_module(mod):
    src = mkrffi.RffiSource(includes=['cairo.h'], libraries=['cairo'], 
        include_dirs=['/usr/local/include/cairo'])
    ns = mod.__dict__
    src.proc_namespace(ns)
    f = open('output.py', 'w')
    print >>f, "#"
    print >>f, "# WARNING: THIS CODE AUTO GENERATED BY %s"%sys.argv[0]
    print >>f, "#"
    print >>f, "from pypy.rpython.lltypesystem import rffi"
    print >>f, "from pypy.rpython.lltypesystem import lltype"
    print >>f, str(src)

def big_test():
    import _cairo
    proc_module(_cairo)



if __name__=="__main__":
    big_test()


