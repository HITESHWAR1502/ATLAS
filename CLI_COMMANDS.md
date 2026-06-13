# ATLAS CLI Commands

ATLAS provides a command-line interface to interact with the test case generation pipeline.

## Base Command

```bash
atlas [OPTIONS] COMMAND [ARGS]...
```

**Global Options:**
- `--version`: Show the version of ATLAS and exit.
- `--log-level TEXT`: Set the logging level. Available options are `DEBUG`, `INFO`, `WARNING`, `ERROR`. (Default: `INFO`)
- `--help`: Show the help message and exit.

---

## Available Commands

### `run`

Run the ATLAS pipeline interactively. This command will open an interactive prompt asking for the target file or repository path and the test layers to generate.

```bash
atlas run [OPTIONS]
```

**Options:**
- `--env PATH`: Specify the path to a custom `.env` file containing your configuration and API keys. If not provided, it looks for `.env` in the current directory.
- `--help`: Show the help message for the run command.

---

### Example Workflow

1. **Start the pipeline:**
   ```bash
   atlas run
   ```

2. **Interactive Prompts:**
   - **Target Path:** `Enter the target file path or repository path:` (Default is `./`)
   - **Select Layers:** `Select testing layers:` Use the `Space` bar to select layers and `Enter` to confirm. Options are:
     - `UNIT` (Unit testing)
     - `INTEGRATION` (Integration testing)
     - `FUNCTIONAL` (Functional testing)
     - `PERFORMANCE` (Performance testing)
     - `SECURITY` (Security testing)

3. **Execution:**
   ATLAS will read your configuration, initialize the agents, and begin the sequential execution loop to generate test cases for the selected layers.
