#!/usr/bin/env python
from pathlib import Path

root_dir = Path('.').parent
legend_path = Path(root_dir, 'dev_tools', 'table_legend.org')
trace_root = Path(root_dir, "state_traces")
part_dir = Path(trace_root, "part_org_digest")
list_file = Path(part_dir, "include.lst")
with open(list_file) as f:
    buff = f.read()

with open(legend_path) as f:
    legend = f.read()


out_file = Path(trace_root, "combined.org")
with open(out_file, 'w') as f:
    for ppath in buff.split('\n'):
        if ppath.strip()  == '':
            continue
        f.write("#+BEGIN_FILE_INCLUDE\n")
        f.write(f"part_org_digest/{ppath}\n")
        f.write("#+END_FILE_INCLUDE\n")
    f.write(legend)
