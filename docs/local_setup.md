# Run the dashboard entirely in VS Code

No GCP account, external API, deployment or external browser is required for this workflow.

## Start and preview

1. Open the biptya project folder in VS Code.
2. Open **Run and Debug**.
3. Select **FMCG: Local dashboard in VS Code** and press **F5**.

The prelaunch task checks the existing .venv, installed local dependencies and current master-validation scope. The app starts in the integrated terminal on http://127.0.0.1:8501. The installed server-ready action opens the dashboard in VS Code's integrated browser when its URL appears. The Python/Python Debugger extensions were found installed.

Keep VS Code open while using the app. Use **Shift+F5** to stop the debug session. Streamlit is headless and does not start a separate browser.

Microsoft's references: [Python debugging](https://code.visualstudio.com/docs/python/debugging), [integrated browser](https://code.visualstudio.com/docs/debugtest/integrated-browser), [debug configuration](https://code.visualstudio.com/docs/debugtest/debugging-configuration). The openIntegratedBrowser action was also confirmed in your installed server-ready extension.

## Other local tasks

Use **Ctrl+Shift+P → Tasks: Run Task**:

- **FMCG: Check local setup** checks without starting a server.
- **FMCG: Start local dashboard (terminal)** runs in a VS Code terminal.
- **FMCG: Run tests** runs all unit tests.
- **FMCG: Validate dashboard on real data** exercises actual analytics and chat UI.

If using the terminal task, select the localhost URL to open it inside VS Code, or use **Browser: Open Integrated Browser** and enter http://127.0.0.1:8501. The **FMCG: Preview running dashboard** debug profile previews a server already running. It does not start another server.

In VS Code's integrated terminal, the equivalent commands are:

```powershell
.\.venv\Scripts\python.exe scripts/run_local.py --check
.\.venv\Scripts\python.exe scripts/run_local.py
```

## Use the assistant

Try **How can we improve sales?**. Ask **Give me a short answer**, **Explain in detail** or **What should I do next?** afterward. Short replies, full explanations, next steps, charts and copy/download remain available. Supported local requests resolve to checked Python analytics; no external model is called.

The sidebar week filters control analysis scope. Full saved model/category/recommendation/diagnosis views require the approved weeks 19-102. Suggestions remain proposals for human review.

## Troubleshooting

**Port 8501 already in use:** stop the previous app terminal with Ctrl+C or its debug session with Shift+F5. Then restart F5. The launcher does not kill unrelated processes.

**No integrated preview:** use **Browser: Open Integrated Browser** and enter the local URL. Inspect the F5 terminal for startup errors. The installed editor supports this browser action; no external browser extension is needed.

**Wrong interpreter:** choose .venv/Scripts/python.exe with **Python: Select Interpreter**. The workspace and debug profile already select it. Current Python is 3.14.4; the original 3.11 target is not installed.

**Missing files/dependencies:** the prelaunch check names missing items. Local dependencies are in requirements.txt. Raw files and validated processed/model artifacts must remain on this computer. No cloud upload or storage is needed.

The old cloud workflow is retired and blocked by LOCAL_ONLY_MODE. Its previous setup guide is historical, not a prerequisite.
