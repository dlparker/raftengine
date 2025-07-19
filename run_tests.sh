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

# Check for debug flag and remove it from arguments
CAPTURE_OPT=""
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--debug" ]]; then
        CAPTURE_OPT="--show-capture=no"
    else
        ARGS+=("$arg")
    fi
done

if [ ${#ARGS[@]} -eq 0 ]; then
    pytest --verbose  --cov-config=coverage.cfg  --cov-report=html --cov-report=term -x --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb -s $CAPTURE_OPT --cov=raftengine tests
else
    pytest --verbose  --cov-config=coverage.cfg --cov-report=html --cov-report=term -x --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb -s $CAPTURE_OPT --cov=raftengine "${ARGS[@]}"
fi
