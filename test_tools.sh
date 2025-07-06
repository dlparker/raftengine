#!/bin/bash
set -x
export PYTHONBREAKPOINT=ipdb.set_trace
#export PYTHONPATH="`pwd`:$(dirname `pwd`)"
export PYTHONPATH=.

if [ -z ${VIRTUAL_ENV+x} ]; then
   source .venv/bin/activate
fi    
if [[ `which pytest` != $VIRTUAL_ENV/bin/pytest ]]; then
   source .venv/bin/activate
fi
if [ $# -eq 0 ]; then
    pytest --verbose  --cov-config=cover_tools.cfg  --cov-report=html --cov-report=term -x --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb -s --cov=dev_tools tests dev_tools/tests
else
    pytest --verbose  --cov-config=cover_tools.cfg --cov-report=html --cov-report=term -x --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb -s  --cov=dev_tools  $@
fi
