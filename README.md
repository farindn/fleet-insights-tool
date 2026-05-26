# Fleet Insights Tool

A tool that connects to MyGeotab, analyzes your fleet's data, and generates a report with AI-powered insights — covering utilization, idling costs, safety scores, and vehicle faults.

---

## Before You Start

You'll need:
- A Windows or Mac computer
- **Python 3.13 or newer** (instructions below)
- Your **MyGeotab login details** (username, password, and server name)
- A **Geotab GenAI Gateway API key** — contact the tool administrator to obtain this

---

## Step 1 — Install Python

> If you already have Python 3.13 or newer, skip this step.

**Windows:**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **Download Python** button
3. Run the installer — on the very first screen, check the box that says **"Add Python to PATH"** before clicking Install

**Mac:**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download and run the `.pkg` installer, then follow the prompts

**Verify it worked** — open Terminal (Mac) or Command Prompt (Windows) and run:
```
python --version
```
You should see something like `Python 3.13.x`.

---

## Step 2 — Download the Project

1. On this GitHub page, click the green **Code** button
2. Select **Download ZIP**
3. Extract the ZIP file somewhere easy to find, like your Desktop or Documents folder

---

## Step 3 — Open a Terminal in the Project Folder

**Windows:**
1. Open the extracted project folder in File Explorer
2. Click on the address bar at the top of the window (where the folder path is shown)
3. Type `cmd` and press Enter — a Command Prompt window will open

**Mac:**
1. Open the extracted project folder in Finder
2. Right-click the folder and select **New Terminal at Folder**

---

## Step 4 — Set Up Your Configuration

The tool uses a settings file called `.env` to store a few private values.

1. In the project folder, find the file named **`.env.example`**
2. Make a copy of it and rename the copy to **`.env`** (remove the `.example` part)

   > **Windows tip:** If you can't see file extensions, open File Explorer, go to **View → Show → File name extensions**, and turn that on.

3. Open your new `.env` file with **Notepad** (Windows) or **TextEdit** (Mac)
4. Fill in the two values below:

### `SESSION_SECRET`

This is a private security key that protects your session. To generate one, run this command in your terminal:

```
python -c "import secrets; print(secrets.token_hex(16))"
```

Copy the output (a random mix of letters and numbers) and paste it next to `SESSION_SECRET=`:

```
SESSION_SECRET=paste-your-generated-string-here
```

### `GENAI_API_KEY`

This is your Geotab GenAI Gateway API key. Contact the tool administrator to obtain this, then paste it in:

```
GENAI_API_KEY=your-key-here
```

### Leave everything else as-is

The `GENAI_GATEWAY_URL` and `GENAI_MODEL` values are already set to the right defaults — don't change them.

Your finished `.env` file should look like this:

```
SESSION_SECRET=a3f8c2d1e4b7f09a2c5d8e1f4b7c0d3a
GENAI_API_KEY=your-key-here
GENAI_GATEWAY_URL=https://genai-us.geotab.com/api/v2
GENAI_MODEL=gemini-2.5-flash-lite
```

---

## Step 5 — Install Required Packages

In your terminal, run:

```
pip install -r requirements.txt
```

This downloads everything the tool needs to run. It may take a minute or two.

---

## Step 6 — Start the Tool

In your terminal, run:

```
python -m uvicorn app.main:app --reload
```

Some text will appear — that's normal. When you see this line, the tool is ready:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## Step 7 — Open in Your Browser

Open any web browser (Chrome, Edge, or Safari) and go to:

**http://localhost:8000**

You should see the Fleet Insights login screen.

---

## Using the Tool

1. **Log in** with your MyGeotab username, password, and server name
   > Your server name is the part of your MyGeotab URL after `my.geotab.com/` — for example `my744` or `my3`. If you're not sure, ask your fleet admin.
2. **Select** your fleet group and the date range you want to analyze
3. Click **Generate Report**
4. Wait 1–3 minutes while the report is built — you'll see a live progress bar
5. **Download** the HTML report file and open it in any browser to view the results

---

## Stopping the Tool

When you're done, go back to your terminal window and press **Ctrl + C**.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` is not recognized (Windows) | Re-run the Python installer and check **"Add Python to PATH"** |
| `No module named uvicorn` | Run `pip install -r requirements.txt` again |
| The page doesn't load | Make sure the terminal is still running; also try `http://127.0.0.1:8000` |
| "Authentication failed" | Double-check your MyGeotab username, password, and server name |

---

## Need Help?

Contact the tool administrator via Geotab Chat.
