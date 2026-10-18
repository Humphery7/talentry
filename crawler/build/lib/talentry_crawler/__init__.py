"""Talentry crawler — background worker that fills the jobs database.

Layers (see ARCHITECTURE.md):
  models     shared shapes (Board, Job, Company)
  config     read data/*.csv
  ats        fetch jobs from Greenhouse / Ashby / Lever
  labeling   add seniority / occupation / technologies to a job
  storage    save to the database
  pipeline   runs the layers above, in order
  cli        how a human starts it
"""

__version__ = "0.1.0"
