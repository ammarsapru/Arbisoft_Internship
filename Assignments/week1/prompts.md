# Prompts Log

Record of questions and prompts used during development of this project.

---

## Environment Setup

**Prompt:** Is this line correct to install uv onto my system from the VS Code terminal, or should I run it in PowerShell?
`curl -LsSf https://astral.sh/uv/install.sh | sh`
**Resolution:** That command is Unix-only. Windows equivalent:
`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

---

**Prompt:** Update the rest of the uv commands to Windows under the correct labels.
**Resolution:** Updated `uv_commands.txt` — replaced `source ~/.bashrc` with the PowerShell PATH reload, fixed `uv installing` typo to `uv init`.

---

**Prompt:** `uv add numpy pandas sickit-learn` — error saying package not found.
**Resolution:** Typo — `sickit-learn` should be `scikit-learn`.

---

## Data Loading

**Prompt:** Why is loading the dataset taking so long — I thought uv was supposed to be fast?
**Resolution:** uv speed applies to package installs only, not code execution. The delay was a network request to UCI's server. Fix: download the file once with `urllib.request.urlretrieve` and read locally.

**Prompt:** The kernel was stuck — even after interrupting it was still going.
**Resolution:** Kernel was frozen. Used `Get-Process python | Stop-Process -Force` to kill it, then restarted the kernel in VS Code.

**Prompt:** `ModuleNotFoundError: No module named 'xlrd'`
**Resolution:** `uv add xlrd` — required to read `.xls` format files.

---

## Notebook Display

**Prompt:** `concrete_data.head()` did not display as a table — showed plain text.
**Resolution:** `print()` bypasses Jupyter's HTML rendering. Changed to `display()`, then split into a dedicated cell with just `concrete_data.head()` as the last expression.

---

## Code Explanations

**Prompt:** How does `[-1, :-1]` work?
**Resolution:** 2D indexing — `-1` selects last row, `:-1` selects all columns except the last.

**Prompt:** What did the confusion matrix do to the data? (referring to correlation matrix)
**Resolution:** Clarified: this is a correlation matrix, not a confusion matrix. It transforms data into correlation coefficients (-1 to 1). `iloc[-1, :-1]` selects the target variable's row and drops its self-correlation.

**Prompt:** What does `random_state` mean? What does 42 decide?
**Resolution:** Seed for the random number generator — determines which specific rows land in train vs test. Any fixed number works equally well. 42 is a cultural reference. Danger is seed fishing (trying many seeds to find a flattering result).

**Prompt:** Is `.2f` two factorial or 2 decimal places?
**Resolution:** 2 decimal places. `f` = float, `.2` = precision of 2 digits after the decimal.

---

## Bugs Fixed

**Prompt:** `plt.xlabel = ('Cement (kg/m3)')` — why is there still an error in cell 7?
**Resolution:** Cell 2 used `=` (assignment) instead of `()` (function call), permanently overwriting `plt.xlabel` with a string for the kernel session. Also had typo `plt.ylable`. Fixed to `plt.xlabel(...)` and `plt.ylabel(...)`.

---

## Classification Metrics

**Prompt:** Report accuracy, precision, recall and a confusion matrix.
**Resolution:** Added two cells — one reporting metrics via `RandomForestClassifier` on strength binned into Low/Medium/High classes, one plotting the confusion matrix with matplotlib.

---

## Testing & Tooling

**Prompt:** Setup unit tests file, pytest explanation, prompts log, and linting setup.
**Resolution:** Created `data_prep.py` (utility functions), `test_data_prep.py` (7 pytest tests), `pytest_explained.txt` (fundamentals to usage), `prompts.md` (this file), `linting_setup.txt` (ruff/flake8 instructions).
