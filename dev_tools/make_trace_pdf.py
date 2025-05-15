#!/usr/bin/env python
import sys
import os
import shutil
from pathlib import Path
import subprocess
from subprocess import Popen

this_dir = Path(__file__).parent.resolve()
root_dir = this_dir.parent.resolve()
tool_path = Path(this_dir, 'roam2doc').resolve()
legend_path = Path(this_dir, 'table_legend.org')
trace_root = Path(root_dir, "state_traces")
part_dir = Path(trace_root, "part_org_digest")

def make_combined():
    
    with open(legend_path) as f:
        legend = f.read()

    files = []
    for filepath in part_dir.glob("*.org"):
        files.append(filepath.parts[-1])

    out_file = Path(trace_root, "combined.org")
    with open(out_file, 'w') as f:
        for ppath in files:
            f.write("#+BEGIN_FILE_INCLUDE\n")
            f.write(f"part_org_digest/{ppath}\n")
            f.write("#+END_FILE_INCLUDE\n")
        f.write(legend)
    return out_file

def make_one_trace(source_file):
    
    out_file = Path(source_file.stem + "_plus_l.org")
    with open(source_file) as f:
        buff = f.read()
         
    with open(legend_path) as f:
        legend = f.read()

    with open(out_file, 'w') as f:
        f.write(buff)
        f.write(legend)
    return out_file

if __name__=="__main__":
    if len(sys.argv) == 1:
        run_dir = os.getcwd()
        os.chdir("/tmp")
        source_file = make_combined()
        out_file = Path("/tmp/combined.pdf")
    else:
        selection = Path(sys.argv[1]).resolve()
        run_dir = os.getcwd()
        os.chdir("/tmp")
        source_file = make_one_trace(selection)
        out_file = Path('/tmp', source_file.stem + ".pdf")

    command = [str(tool_path), str(source_file), "--doc_type", "pdf", "--wk_pdf", "--output", str(out_file), "--overwrite"]
    print(command)
    print(os.getcwd())
    x = Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    res,error = x.communicate()
    if error:
        print(error)
    shutil.copy(out_file, run_dir)
    os.chdir(run_dir)
