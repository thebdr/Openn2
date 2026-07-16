"""The folder-based Project Manager. A project ROOT is a folder carrying
`config_project/project_params.yaml` (+ its Database/ and Output/); `config.use_project(root)`
points every loader at it.

WHERE TO LOOK:
  project_manager.py  create/open/close/backup a project; scaffolding + config completeness;
                      the project meta (types, multi_system, versions)
  app_state.py        the persisted per-user app state (recents, last-opened)
"""
