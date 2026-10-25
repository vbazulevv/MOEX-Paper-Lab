# Publish from macOS — step by step

The downloadable ZIP includes an existing `.git` folder with **AI-attributed commits and a genuine test/fix history**. Don't delete `.git` unless you intentionally want to start a new repository and lose that history.

## 1. Download and unzip

Unzip `moex-paper-lab.zip` in your Downloads folder. The folder should be named `moex-paper-lab`.

Open **Terminal**, then:

```bash
cd ~/Downloads/moex-paper-lab
python3 --version
python3 main.py
```

Try options `1` (portfolio), `4` (risk) and `6` (exit).

## 2. Verify the tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected result for the provided draft: `Ran 14 tests` and `OK`. If Python 3 is not available, install a supported Python version first. Do not include passwords or tokens in screenshots.

## 3. Inspect your Git history

```bash
git log --oneline --max-count=8
git status
```

The first commits are attributed to the assistant, not you. They show the generated code, automated tests, the failing-date test and its actual fix.

## 4. Make a real student-authored change

For example: adjust the README after you personally test the CLI, add a test case, improve a console label, or document what you learned in `docs/AI_USAGE.md`. Set your Git identity if needed:

```bash
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

Then commit only changes you actually made:

```bash
git add README.md docs/AI_USAGE.md
git commit -m "docs: record my Mac verification and reflections"
```

If you haven't changed those files, Git will correctly say there is nothing to commit. Don't manufacture commits.

## 5. Create a public repository on GitHub

Go to https://github.com/new, sign in, choose repository name `moex-paper-lab`, select **Public**, and **do not initialize it with a README, .gitignore or license** because the local folder already has those files.

Once GitHub shows the new repository page, run in Terminal, replacing `YOUR-USERNAME`:

```bash
git remote add origin https://github.com/YOUR-USERNAME/moex-paper-lab.git
git push -u origin main
```

GitHub may prompt you to authenticate using a browser or your existing Git credential manager. **Do not send passwords or personal access tokens through this chat.** If `origin` already exists, check `git remote -v` rather than adding it twice.

If you prefer, the connected GitHub app in ChatGPT may be able to help publish changes once you authorize it.

## 6. Verify and submit

Open the repository URL in a private/incognito browser window to confirm that it is public. Check its `Actions` tab; the unit-test workflow should run after a push. Then submit the **root repository URL** to Blackboard, rather than a link to `main.py`.

The assignment screenshot shows a deadline of **16 October 2026** and a possible late penalty, so don't postpone submission to add optional features.
