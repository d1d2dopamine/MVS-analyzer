# Windows visual and interaction acceptance checklist

Status: **not executed during source preparation**. These are manual acceptance tasks, not checked-off results. No simulated screenshot is supplied as evidence.

- [ ] Windows 10/11, 100%, 125%, 150%, 200% DPI; move between monitors with different scaling.
- [ ] Minimum allowed window and maximized: sidebar can scroll to Scientific models, Help and settings; labels/buttons remain reachable.
- [ ] English/Russian and light/dark themes: readable foregrounds, selected grid rows, numeric inputs, tabs and progress dialog.
- [ ] Results summary wraps without overlapping labels; all result/calibration columns are reachable through the grid's own horizontal scrollbar.
- [ ] Legacy cards at narrow widths expose overflow through their own scrollbars; no hidden controls block a workflow.
- [ ] Calibration cancellation leaves no reusable stale half/result. Changed filtering requires re-import; changed scientific settings require recalibration.
- [ ] Saved calibration JSON can be restored only with matching original input and processing.
- [ ] Scientific models: choose output parent, cancel, rerun, inspect numerical warning/failure and successful export. “Completed” is not confused with valid inference.
- [ ] Repeated IDs: independent-group confirmation is explicit; MELSM preserves global subjects.
- [ ] File save failure/journal lock failure is visible and does not falsely claim every artifact was saved.
- [ ] Existing icons, logos, badges and image assets are unchanged; original static screenshots are not represented as screenshots of new views.
- [ ] Keyboard/tab access, Ctrl+navigation, long group/file names, large tables and non-Latin identifiers.

Fix issues discovered on a real Windows render before signing off the desktop release.
