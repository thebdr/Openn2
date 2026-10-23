"""Close SYCON.net without saving, refresh the scratch copy of the base project, launch it and log in.

Usage:  python -I scripts/sycon_restart.py [project.spj]   (default: the scratch copy of the base project)
"""
import os, sys, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import close_sycon_no_save, launch_sycon, login_default, project_tree, iter_items

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # Sycon5App/spike
APP = os.path.dirname(HERE)                                                  # Sycon5App
SRC = os.path.join(APP, "SyconProjects")
SCRATCH = os.path.join(HERE, "scratch")
PROJ = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCRATCH, "AutomateSyconProj_BaseProj.spj")

print("close:", close_sycon_no_save())
if PROJ.startswith(SCRATCH):
    shutil.rmtree(SCRATCH, ignore_errors=True)
    shutil.copytree(SRC, SCRATCH)
    print("scratch copy refreshed from", SRC)
pid = launch_sycon(PROJ)
print("launched, pid", pid, "- login dialog up")
main = login_default()
print("main:", main.window_text())
for i in iter_items(project_tree(main)):
    print("  ", i.window_text())
