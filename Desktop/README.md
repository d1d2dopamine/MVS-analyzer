# Archived Windows desktop

The Windows desktop interface is frozen at MVS 1.4.0. It is kept in the repository so the archived release can be inspected and reproduced, but it is no longer part of active development.

From the 1.5.0 line onward:

- desktop projects are excluded from the active solution;
- CI does not compile or test WinForms code;
- release automation does not publish Windows desktop binaries;
- new features target the headless CLI and Python API.

Do not add new statistical behavior only to this directory. Scientific changes belong in `MvsAnalyzer.Core`, with public access through the CLI/Python stack.
