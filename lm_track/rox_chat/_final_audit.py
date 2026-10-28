import sys
sys.path.insert(0, ".")
from project import Project, Auditor
from project.journal import Journal

p = Project.open("task-manager")
p.scan()
arch = p.architecture(refresh=True)
print("=== FINAL PROJECT STRUCTURE ===")
for mo in arch["modules"]:
    print("  " + mo["path"] + ": " +
          ", ".join(s["name"] for s in mo["symbols"]))
rep = Auditor(p).audit()
print("=== AUDIT ===", rep["counts"] or "CLEAN")
print("=== JOURNAL ===")
print(Journal(p).summary(30))
p.close()