# Clearstep owner interface

A buildless, dependency-free frontend served by FastAPI. No npm installation or separate
frontend server is required.

From the repository root:

```bash
cd backend
../.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The existing root `.env` supplies the OpenAI key.
Starting the server does not call OpenAI. Clicking **Help me work it out** uploads
the selected files and starts a paid live analysis.

1. Choose a folder, or individual CSV, XLSX, TXT, and text-based PDF files.
2. Ask a supplier-comparison or promotional-event question.
3. Review extracted values or enter corrections. Percentages are entered as 0–100.
4. Read the calculated result, scenarios, inputs, and limitations; optionally save a text copy.

Unsupported/hidden files are listed as skipped. Upload failures stop analysis until
they are corrected or the affected file is removed. For multi-sheet Excel workbooks,
enter the worksheet name requested by the upload message and retry. Folder selection
depends on browser support; individual file selection is provided as an alternative.
The interface uses the backend's current USD financial contracts.

The current run ID is saved in browser local storage so refresh can reopen it; file
contents and API keys are not stored there. Browser storage is not an account or a
history system. The backend still stores uploaded records and analyses locally.
This remains the existing single-user local app, not a production multi-user service.

Run frontend logic tests without installing packages:

```bash
node --test frontend/tests/logic.test.js
```
