# Week 1 Assignment — Concrete Compressive Strength

## Assignment Checklist

| Requirement | Details | Status | Reference |
|---|---|:---:|---|
| Load and explore the dataset | Read `.xls` via `pd.read_excel`; check shape and missing values | ✅ | `cement_classification.ipynb` — Cells 1–2 |
| Visualise raw data | Scatter plot: cement amount vs compressive strength | ✅ | `cement_classification.ipynb` — Cell 3 |
| Correlation analysis | Full correlation matrix; ranked correlation with target variable | ✅ | `cement_classification.ipynb` — Cell 4 |
| Prepare features and split data | Convert to NumPy arrays; 80/20 stratified train-test split | ✅ | `cement_classification.ipynb` — Cell 5 |
| Train regression models | Linear Regression and Random Forest Regressor | ✅ | `cement_classification.ipynb` — Cell 6 |
| Report regression metrics (MSE, R²) | MSE and R² reported for both models | ✅ | `cement_classification.ipynb` — Cell 6 |
| Feature engineering | Cement/water ratio added as domain feature; Gradient Boosting model | ✅ | `cement_classification.ipynb` — Cell 8 |
| Report evaluation metrics (accuracy, precision, recall) | Strength binned Low/Medium/High; RandomForestClassifier | ✅ | `cement_classification.ipynb` — Cell 9 |
| Confusion matrix | Heatmap of predicted vs actual strength class | ✅ | `cement_classification.ipynb` — Cell 10 |
| Write 3+ pytest unit tests for data-prep utility functions | 7 tests covering missing values, binning, feature shape | ✅ | `test_data_prep.py` |
| Maintain a prompts.md log | Full log of all questions and resolutions during development | ✅ | `prompts.md` |
| Configure ruff / flake8; commit a clean lint pass | | | `linting_setup.txt` |

---

## Project Overview

This project applies regression and classification machine learning techniques to the [UCI Concrete Compressive Strength dataset](https://archive.ics.uci.edu/ml/machine-learning-databases/concrete/compressive/Concrete_Data.xls). The dataset contains 1030 samples with 8 ingredient features (cement, water, slag, fly ash, superplasticizer, coarse aggregate, fine aggregate, age) and one continuous target: compressive strength in MPa.

The work covers the full ML pipeline — data loading, exploration, preprocessing, model training, evaluation, and testing.

---

## Models Used

| Model | Type | Purpose |
|---|---|---|
| Linear Regression | Regression | Baseline strength prediction |
| Random Forest Regressor | Regression | Improved strength prediction |
| Gradient Boosting Regressor | Regression | Prediction with engineered features |
| Random Forest Classifier | Classification | Classify strength as Low / Medium / High |

---

## Strength Classes (for classification)

| Class | Range |
|---|---|
| Low | < 30 MPa |
| Medium | 30 – 50 MPa |
| High | > 50 MPa |

---

## File Structure

```
Assignments/week1/
├── cement_classification.ipynb   # main notebook — full ML pipeline
├── data_prep.py                  # reusable data preparation functions
├── test_data_prep.py             # 7 pytest unit tests
├── requirements.txt              # dependencies
├── prompts.md                    # log of prompts used during development
├── linting_setup.txt             # ruff / flake8 setup instructions
├── uv_commands.txt               # uv package manager reference (Windows)
├── mse_explained.txt             # MSE concept explained with visuals
├── r2_explained.txt              # R² score explained with visuals
├── random_state_explained.txt    # random_state explained in depth
└── pytest_explained.txt          # pytest fundamentals and usage guide
```

---

## Setup

```powershell
# Install uv (Windows PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Initialise project and install dependencies
uv init
uv add numpy pandas scikit-learn matplotlib xlrd ipykernel pytest

# Run unit tests
pytest test_data_prep.py -v
```

---

## Repository Context

This assignment is part of the [Arbisoft Internship](https://github.com/ammarsapru/Arbisoft_Internship) — a programme covering AI/ML fundamentals, data structures and algorithms, and data manipulation.

| Folder | Contents |
|---|---|
| `DSA_PRACTISE/` | Sorting, linked lists, trees, graph algorithms, Dijkstra |
| `numpy_pandas_relationships/` | NumPy arrays, Pandas DataFrames, SQL schema design |
| `Assignments/week1/` | This project — concrete strength ML pipeline |
